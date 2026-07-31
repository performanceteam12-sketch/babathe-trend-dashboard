"""
경쟁사 모니터링 자동 캡처 — 브랜드검색(PC/MO) + 메타 광고 라이브러리 운영 소재 2종.

주의:
- search.naver.com과 facebook.com(Meta 광고 라이브러리)은 robots.txt/이용약관상 자동 수집을
  명시적으로 금지한다. 사용자 요청으로 저빈도(주 1회) 실행을 전제로 진행하되, 대량/고빈도 호출은
  절대 하지 않는다. 이 스크립트를 cron 등으로 하루에 여러 번 돌리지 말 것.
- Meta 광고 라이브러리는 브랜드명으로 키워드 검색하면 관련 없는 광고가 섞여 나온다. 검색창에 계정명을
  타이핑하면 뜨는 자동완성(광고주 정확 일치)의 view_all_page_id로 그 계정 전용 목록에 바로 들어가는
  방식으로 전환했다 (PAGE_ID_MAP, 2026-07-29). 소재는 카드 스크린샷이 아니라 실제 이미지 URL을 찾아
  다운로드하고, 패션 키워드에 맞는 소재를 우선 선택한다 (없으면 최신순 최상단 2개).
- 두 사이트 모두 마크업이 자주 바뀌는 편이라, 실패 시 조용히 넘어가지 말고 어떤 브랜드/슬롯이
  실패했는지 명확히 출력한다.
"""

import argparse
import re
import sys
import urllib.parse
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "data" / "competitor_monitor" / "images"
CSV_PATH = ROOT / "data" / "competitor_monitor" / "competitor_monitor.csv"
KEYWORDS_CSV_PATH = ROOT / "data" / "competitor_monitor" / "keywords.csv"

BRANDS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]

# 2026-07-24 기준 확인된 각 브랜드의 실제 메타 광고 라이브러리 계정명 (아바타 이미지 alt 텍스트 필터링용)
ACCOUNT_MAP = {
    "더한섬닷컴": "한섬",
    "신세계V": "VERY SHINSEGAE",
    "W컨셉": "W컨셉",
    "바바더닷컴": "바바더닷컴",
}

# 2026-07-29 확인: 검색창에 브랜드 계정명을 한 글자씩 타이핑하면 뜨는 자동완성(광고주 정확 일치)을
# 클릭해 얻은 view_all_page_id. 이 값으로 바로 그 페이지 전용 광고 목록에 들어가면 키워드 검색과
# 달리 무관한 광고가 섞이지 않는다.
PAGE_ID_MAP = {
    "더한섬닷컴": "724882231232775",
    "신세계V": "256002414775220",
    "W컨셉": "189176731145096",
    "바바더닷컴": "451533041676254",
}

# 브랜드별로 항상 나오는 상시 캠페인이라 다양성이 떨어지는 키워드 — 메타소재 선택 시 후순위로
# 미룬다(완전히 제외하지는 않음, 다른 소재가 정말 없으면 최대 1개까지는 허용). 사용자 요청, 2026-07-31.
DEPRIORITIZE_KEYWORDS = {
    "바바더닷컴": ["바바데이"],
}

# 패션(의류·잡화) 소재인지 대략 판단하는 1순위 키워드. 신발은 사용자 요청에 따라 2순위(뷰티/라이프)로
# 뺐다. 완벽할 수 없으니 "패션 소재 우선, 없으면 뷰티/라이프/신발" 지침에 따라 필터가 아니라
# 우선순위로만 쓴다 (2026-07-29).
FASHION_KEYWORDS = [
    "원피스", "팬츠", "자켓", "재킷", "니트", "코트", "셔츠", "블라우스", "스커트", "청바지",
    "가디건", "후드", "맨투맨", "슬랙스", "아우터", "조끼", "점퍼", "트렌치코트",
    "가방", "백팩", "지갑", "벨트", "목도리", "스카프", "모자", "의류", "패션",
    "탑", "크롭", "베스트", "점프수트", "레깅스", "잠옷", "파자마", "수영복", "래시가드", "룩북",
]

# 2순위: 패션 관련 소재가 없을 때 대신 고를 뷰티/라이프/신발 키워드 (사용자 요청, 2026-07-29).
BEAUTY_LIFE_SHOES_KEYWORDS = [
    "신발", "슈즈", "부츠", "스니커즈", "샌들",
    "뷰티", "스킨케어", "향수", "크림", "세럼", "로션", "헤어", "샴푸", "바디", "클렌징", "메이크업",
    "쿠션", "립스틱", "선크림", "토너", "에센스",
    "리빙", "인테리어", "침구", "가전", "주방", "조명", "캔들", "홈웨어", "가구",
]


def is_fashion_related(text: str) -> bool:
    return any(kw in text for kw in FASHION_KEYWORDS)


def is_beauty_life_shoes(text: str) -> bool:
    return any(kw in text for kw in BEAUTY_LIFE_SHOES_KEYWORDS)


PRICE_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})+원")
LIBRARY_ID_PATTERN = re.compile(r"라이브러리 ID:\s*(\d+)")
MEDIA_ID_PATTERN = re.compile(r"/(\d{10,})_")


def is_catalog_ad(text: str) -> bool:
    # 카탈로그(다이나믹 프로덕트) 광고는 낱개 상품마다 가격이 따로 붙어서 카드 안에 "00,000원" 형태
    # 가격 표기가 여러 번 반복된다. 컬렉션/이미지 광고는 보통 이런 개별 가격 표기가 없거나 1개뿐이라,
    # 광고 라이브러리 UI 자체에 "카탈로그/컬렉션/이미지" 형식 필터가 없어서 이 텍스트 패턴으로 대신
    # 구분한다 (사용자 요청, 2026-07-29).
    return len(PRICE_PATTERN.findall(text)) >= 2


def media_id_of(image_url: str) -> str:
    # Meta CDN URL의 파일명 앞자리 숫자(미디어 ID)로 동일 소재 재사용 여부를 판단한다. 같은 소재가
    # 여러 광고 항목(다른 타겟팅/캠페인)으로 중복 게재돼 있어도 이 ID는 같다 (사용자 요청 — 똑같은
    # 사진을 소재 1/2에 중복으로 넣지 않기, 2026-07-29).
    m = MEDIA_ID_PATTERN.search(image_url)
    return m.group(1) if m else image_url


CONTENT_STD_THRESHOLD = 28  # 아래 looks_like_content_photo 참고


def looks_like_content_photo(image_bytes: bytes) -> bool:
    # 제품 단독 컷(흰 배경/단색 배경 위 상품 사진, 텍스트 배너)은 이미지 모서리·테두리 색상이
    # 거의 균일하다. 모델 착용컷/라이프스타일 사진처럼 "콘텐츠로 만들어진" 이미지는 배경이 다양해서
    # 테두리 색상 편차가 크다. 이 편차(표준편차)로 대략 구분한다 (사용자 요청, 2026-07-29).
    # 완벽한 판별은 아니라서 애매하면(이미지 파싱 실패 등) 배제하지 않고 통과시킨다.
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return True

    w, h = img.size
    if w < 20 or h < 20:
        return True

    patch = max(10, min(30, w // 8, h // 8))
    boxes = [
        (0, 0, patch, patch),
        (w - patch, 0, w, patch),
        (0, h - patch, patch, h),
        (w - patch, h - patch, w, h),
        (w // 2 - patch // 2, 0, w // 2 + patch // 2, patch),
        (w // 2 - patch // 2, h - patch, w // 2 + patch // 2, h),
        (0, h // 2 - patch // 2, patch, h // 2 + patch // 2),
        (w - patch, h // 2 - patch // 2, w, h // 2 + patch // 2),
    ]
    pixels = []
    for x0, y0, x1, y1 in boxes:
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        pixels.extend(img.crop((x0, y0, x1, y1)).getdata())
    if not pixels:
        return True

    import statistics

    std = (
        statistics.pstdev(p[0] for p in pixels)
        + statistics.pstdev(p[1] for p in pixels)
        + statistics.pstdev(p[2] for p in pixels)
    ) / 3
    return std >= CONTENT_STD_THRESHOLD

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S911N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)


def save_row(rows: list, brand: str, slot: str, image_bytes: bytes, run_date: date, ext: str = ".png"):
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (IMG_DIR / filename).write_bytes(image_bytes)
    rows.append({
        "date": run_date.isoformat(),
        "brand": brand,
        "slot": slot,
        "image_file": filename,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    })


def clear_slot(rows: list, brand: str, slot: str, run_date: date):
    # 조건에 맞는 소재가 1개뿐이라 2번째 슬롯을 못 채울 때, 예전 날짜의 이미지가 계속 남아있지 않도록
    # "오늘은 값이 없음"을 명시적으로 기록한다 (image_file="" -> 대시보드에서 "미등록"으로 표시됨).
    rows.append({
        "date": run_date.isoformat(),
        "brand": brand,
        "slot": slot,
        "image_file": "",
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    })


EXCLUDE_KEYWORD_LINES = {
    "이벤트", "광고", "홈페이지", "여성", "남성", "전체", "TOP 100", "신규", "쿠폰",
    "브랜드 SNS 소식",
}
PROMO_NUMBER_PATTERN = re.compile(r"\d")


def extract_keywords_from_box(box_element, brand: str) -> list[str]:
    # 브랜드검색 박스 안 썸네일 캡션(예: "FW 신상", "맨즈 썸머룩")을 짧은 키워드로 뽑는다. 정교한
    # 파싱이 아니라 "짧고(2~12자) 숫자/가격/할인율 문구가 아니고 브랜드명 자체도 아닌 줄"이라는 대략적인
    # 규칙이다 — 사용자가 수기로 관리하던 스프레드시트의 "주요 키워드(해시태그)" 항목을 자동화한 것
    # (2026-07-29). 완벽한 파싱이 아니므로 노이즈(카테고리 탭 등)가 섞일 수 있다.
    text = box_element.inner_text()
    account_name = ACCOUNT_MAP.get(brand, brand)
    exclude = EXCLUDE_KEYWORD_LINES | {brand, account_name}
    keywords, seen = [], set()
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or line in exclude:
            continue
        if len(line) < 2 or len(line) > 12:
            continue
        if PROMO_NUMBER_PATTERN.search(line):
            continue  # "최대 20%", "1만원 쿠폰" 같은 할인/가격 문구 제외
        if line in seen:
            continue
        seen.add(line)
        keywords.append(line)
    return keywords[:6]


def capture_naver(page, brand: str, rows: list, run_date: date, log: list, kw_map: dict):
    q = urllib.parse.quote(brand)
    try:
        page.goto(f"https://search.naver.com/search.naver?query={q}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        clip = {"x": 145, "y": 145, "width": 690, "height": 395}
        img = page.screenshot(clip=clip)
        save_row(rows, brand, "브랜드검색 PC", img, run_date)
        log.append(f"[OK] {brand} · 브랜드검색 PC")

        try:
            home_link = page.get_by_text("홈페이지", exact=True).first
            handle = home_link.element_handle()
            best_box_el, best_area = None, 0
            for hops in range(2, 14):
                node = handle.evaluate_handle(
                    """(el, hops) => {
                        let n = el;
                        for (let j = 0; j < hops && n.parentElement; j++) n = n.parentElement;
                        return n;
                    }""",
                    hops,
                ).as_element()
                box = node.bounding_box()
                if box and box["width"] >= 350 and box["height"] < 1200 and box["height"] > best_area:
                    best_box_el, best_area = node, box["height"]
            if best_box_el:
                kw_map.setdefault(brand, set()).update(extract_keywords_from_box(best_box_el, brand))
        except Exception:
            pass  # 키워드 추출은 부가 기능이라 실패해도 이미지 캡처 자체는 실패로 치지 않는다.
    except Exception as e:
        log.append(f"[FAIL] {brand} · 브랜드검색 PC — {e}")


def capture_naver_mobile(browser, brand: str, rows: list, run_date: date, log: list, kw_map: dict):
    q = urllib.parse.quote(brand)
    # 뷰포트 너비: 실제 폰 너비(390)로 찍으면 하단 썸네일 행이 가로 스크롤 캐러셀이라 3~4개만 보이고
    # 나머지가 잘린다. 모바일 페이지는 반응형이라 너비를 넉넉히(700) 주면 캐러셀 없이 5개가 한 줄에
    # 다 펼쳐져서 스크롤 없는 전체 이미지를 얻을 수 있다 (2026-07-29 확인, 사용자 피드백으로 발견).
    MOBILE_CAPTURE_WIDTH = 700
    mpage = browser.new_page(viewport={"width": MOBILE_CAPTURE_WIDTH, "height": 2000}, user_agent=MOBILE_UA, is_mobile=True)
    try:
        mpage.goto(f"https://m.search.naver.com/search.naver?query={q}", wait_until="networkidle", timeout=30000)
        mpage.wait_for_timeout(1500)

        # "홈페이지" 링크를 앵커로 조상을 한 단계씩 올라가며 박스 높이를 측정한다. 너무 얕으면
        # 제목줄만 잡히고, 너무 깊으면 페이지 전체(수천px)가 잡히므로, 그 사이의 "합리적인 카드
        # 크기"(<1200px) 중 가장 큰 것을 브랜드검색 박스로 판단한다. 박스마다 썸네일 개수(3~5개)가
        # 달라 고정 높이/고정 hop 수로는 브랜드마다 다르게 잘리는 문제가 있었음.
        home_link = mpage.get_by_text("홈페이지", exact=True).first
        handle = home_link.element_handle()
        best_box, best_box_el = None, None
        for hops in range(2, 14):
            node = handle.evaluate_handle(
                """(el, hops) => {
                    let n = el;
                    for (let j = 0; j < hops && n.parentElement; j++) n = n.parentElement;
                    return n;
                }""",
                hops,
            ).as_element()
            box = node.bounding_box()
            if box and box["width"] >= 350 and box["height"] < 1200:
                if not best_box or box["height"] > best_box["height"]:
                    best_box, best_box_el = box, node
        if not best_box:
            raise RuntimeError("브랜드검색 박스 높이를 판단하지 못함")
        top = max(0, int(best_box["y"]) - 4)
        bottom = int(best_box["y"] + best_box["height"]) + 8
        try:
            kw_map.setdefault(brand, set()).update(extract_keywords_from_box(best_box_el, brand))
        except Exception:
            pass

        # 일부 브랜드는 "브랜드 SNS 소식" 섹션이 브랜드검색 박스와 같은 상위 컨테이너에 묶여 있어
        # 위 로직만으로는 그 섹션까지 포함돼버린다. 해당 제목이 박스 범위 안에 있으면 그 바로 위에서
        # 잘라낸다 (원하는 건 브랜드검색 박스만, SNS 소식은 제외).
        sns_heading = mpage.get_by_text("브랜드 SNS 소식", exact=True)
        if sns_heading.count() > 0:
            sns_box = sns_heading.first.bounding_box()
            if sns_box and sns_box["y"] < bottom:
                bottom = int(sns_box["y"]) - 12
        # 검색창/탭 영역은 제외하고 브랜드검색 박스 자체만 크롭한다 (대시보드 카드 헤더와 중복되므로).
        img = mpage.screenshot(clip={"x": 0, "y": top, "width": MOBILE_CAPTURE_WIDTH, "height": bottom - top})
        save_row(rows, brand, "브랜드검색 MO", img, run_date)
        log.append(f"[OK] {brand} · 브랜드검색 MO")
    except Exception as e:
        log.append(f"[FAIL] {brand} · 브랜드검색 MO — {e}")
    finally:
        mpage.close()


def capture_meta(page, brand: str, rows: list, run_date: date, log: list):
    page_id = PAGE_ID_MAP.get(brand)
    account_name = ACCOUNT_MAP.get(brand, brand)
    if not page_id:
        log.append(f"[SKIP] {brand} · 메타소재 — PAGE_ID_MAP에 페이지ID 미등록")
        return
    # view_all_page_id로 그 계정 전용 광고 목록에 바로 들어간다 (키워드 검색과 달리 무관한 광고가
    # 섞이지 않는다). sort_data[mode]=relevancy_monthly_grouped 가 UI의 "최신순"(게재 시작일 기준)
    # 정렬에 해당한다 (2026-07-24 UI에서 "최신순" 클릭해 URL로 확인).
    url = (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country=KR&view_all_page_id={page_id}&search_type=page"
        "&sort_data[mode]=relevancy_monthly_grouped&sort_data[direction]=desc"
    )
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2500)
        markers = page.locator("text=라이브러리 ID:")
        total = markers.count()
        if total == 0:
            log.append(f"[FAIL] {brand} · 메타소재 — 게재 중인 광고를 찾지 못함")
            return

        candidates = []
        seen_media_ids = set()
        for i in range(min(total, 20)):
            marker = markers.nth(i)
            handle = marker.element_handle()
            card = handle.evaluate_handle(
                """(el) => {
                    let node = el;
                    for (let j = 0; j < 8 && node.parentElement; j++) node = node.parentElement;
                    return node;
                }"""
            ).as_element()
            text = card.inner_text()
            if is_catalog_ad(text):
                continue  # 카탈로그(다이나믹 프로덕트) 광고는 완전히 제외 (사용자 요청, 2026-07-29)

            # 카드 안 이미지 중 아바타(계정 프로필 사진, alt가 계정명과 같음)를 제외한 첫 이미지가
            # 실제 소재 이미지다. 비디오 소재 등 이미지가 없는 카드는 건너뛴다.
            image_url = None
            for img_el in card.query_selector_all("img"):
                alt = (img_el.get_attribute("alt") or "").strip()
                if alt == account_name:
                    continue
                src = img_el.get_attribute("src")
                if src:
                    image_url = src
                    break
            if not image_url:
                continue

            media_id = media_id_of(image_url)
            if media_id in seen_media_ids:
                continue  # 같은 소재가 여러 광고 항목에 중복 게재된 경우 — 한 번만 후보로 남김
            seen_media_ids.add(media_id)

            m = LIBRARY_ID_PATTERN.search(text)
            library_id = m.group(1) if m else "확인불가"

            resp = page.request.get(image_url)
            img_bytes = resp.body()
            is_content = looks_like_content_photo(img_bytes)
            candidates.append({
                "text": text,
                "image_url": image_url,
                "image_bytes": img_bytes,
                "library_id": library_id,
                "is_content": is_content,
                "tier": (
                    1 if is_fashion_related(text) else
                    2 if is_beauty_life_shoes(text) else
                    3
                ),
            })

        # 제품 단독 컷(흰/단색 배경 상품 사진, 텍스트 배너)은 쓰지 않는다 — 모델 착용·라이프스타일처럼
        # "콘텐츠로 만들어진" 사진만 후보로 남긴다 (사용자 요청, 2026-07-29).
        content_only = [c for c in candidates if c["is_content"]]
        excluded_product_only = len(candidates) - len(content_only)

        # 1순위 패션 → 2순위 뷰티/라이프/신발 → 3순위 그 외(콘텐츠 사진이기만 하면) 순으로,
        # 최신순 상단부터 채운다. 서로 다른 소재(media_id)만 있으므로 자연히 중복은 없다.
        content_only.sort(key=lambda c: c["tier"])

        deprioritize_terms = DEPRIORITIZE_KEYWORDS.get(brand, [])
        preferred = [c for c in content_only if not any(t in c["text"] for t in deprioritize_terms)]
        deprioritized = [c for c in content_only if any(t in c["text"] for t in deprioritize_terms)]

        chosen = preferred[:2]
        if len(chosen) < 2 and deprioritized:
            # 후순위 키워드(예: 상시 캠페인) 소재는 정말 다른 소재가 없을 때만, 그것도 최대 1개까지만 허용.
            chosen += deprioritized[: min(2 - len(chosen), 1)]

        if not chosen:
            log.append(
                f"[FAIL] {brand} · 메타소재 — 조건에 맞는 소재를 찾지 못함 "
                f"(총 {len(candidates)}건 중 콘텐츠 사진 {len(content_only)}건, "
                f"제품 단독컷 제외 {excluded_product_only}건)"
            )
            return

        for idx, c in enumerate(chosen, start=1):
            url_path = c["image_url"].split("?")[0]
            ext = Path(url_path).suffix or ".jpg"
            save_row(rows, brand, f"메타소재 {idx}", c["image_bytes"], run_date, ext=ext)
            tag = {1: "패션", 2: "뷰티/라이프/신발", 3: "일반"}[c["tier"]]
            start_line = next((l for l in c["text"].split("\n") if "게재 시작" in l), "").strip()
            log.append(
                f"[OK] {brand} · 메타소재 {idx} ({tag}, 라이브러리ID:{c['library_id']}, {start_line})"
            )

        # 조건에 맞는 소재가 1개뿐이면 2번째 슬롯은 비워둔다(예전 이미지가 남아있지 않도록 명시적으로
        # "미등록" 처리) — 없는데 억지로 중복/부적합 이미지를 채우지 않는다 (사용자 요청, 2026-07-29).
        if len(chosen) == 1:
            clear_slot(rows, brand, "메타소재 2", run_date)
            log.append(f"[INFO] {brand} · 메타소재 2 — 조건에 맞는 서로 다른 소재가 1개뿐이라 비워둠")
    except Exception as e:
        log.append(f"[FAIL] {brand} · 메타소재 — {e}")


def run(brands: list[str], run_date: date) -> list[str]:
    rows = []
    log = []
    kw_map: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        for brand in brands:
            capture_naver(page, brand, rows, run_date, log, kw_map)
            capture_naver_mobile(browser, brand, rows, run_date, log, kw_map)
            capture_meta(page, brand, rows, run_date, log)
        browser.close()

    if rows:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = pd.read_csv(CSV_PATH, encoding="utf-8-sig", keep_default_na=False) if CSV_PATH.exists() else pd.DataFrame(
            columns=["date", "brand", "slot", "image_file", "uploaded_at"]
        )
        new_df = pd.DataFrame(rows)
        # pandas merge 기반 dedup이 (date,brand,slot) 일치를 제대로 못 잡아 같은 슬롯이 계속 누적되는
        # 버그가 있었다. 순수 파이썬 튜플 집합 비교로 바꿔 확실하게 기존 행을 제거한다.
        new_keys = set(zip(new_df["date"], new_df["brand"], new_df["slot"]))
        if not existing.empty:
            existing = existing[[(d, b, s) not in new_keys for d, b, s in zip(existing["date"], existing["brand"], existing["slot"])]]
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    if kw_map:
        KEYWORDS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing_kw = pd.read_csv(KEYWORDS_CSV_PATH, encoding="utf-8-sig", keep_default_na=False) if KEYWORDS_CSV_PATH.exists() else pd.DataFrame(
            columns=["date", "brand", "keywords", "updated_at"]
        )
        kw_rows = [
            {
                "date": run_date.isoformat(),
                "brand": brand,
                "keywords": ",".join(sorted(kws)),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            for brand, kws in kw_map.items()
        ]
        kw_new_df = pd.DataFrame(kw_rows)
        kw_new_keys = set(zip(kw_new_df["date"], kw_new_df["brand"]))
        if not existing_kw.empty:
            existing_kw = existing_kw[[(d, b) not in kw_new_keys for d, b in zip(existing_kw["date"], existing_kw["brand"])]]
        kw_combined = pd.concat([existing_kw, kw_new_df], ignore_index=True)
        kw_combined.to_csv(KEYWORDS_CSV_PATH, index=False, encoding="utf-8-sig")
        for brand, kws in kw_map.items():
            log.append(f"[INFO] {brand} · 키워드 {len(kws)}개 추출: {', '.join(sorted(kws))}")

    return log


def main():
    # Windows 콘솔 기본 코드페이지(cp949)로는 이모지·특수기호가 포함된 출력이 UnicodeEncodeError로
    # 죽어서 실제 성공 여부와 무관하게 "실패"로 보이는 문제가 있었다. 호출 방식(터미널 직접 실행,
    # 대시보드 subprocess, 작업 스케줄러)과 무관하게 항상 안전하도록 여기서 강제한다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brands", nargs="*", default=BRANDS, help="캡처할 브랜드 목록 (기본: 전체 4개)")
    args = parser.parse_args()

    log = run(args.brands, date.today())
    for line in log:
        print(line)

    failures = [l for l in log if l.startswith("[FAIL]")]
    if failures:
        print(f"\n{len(failures)}건 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
