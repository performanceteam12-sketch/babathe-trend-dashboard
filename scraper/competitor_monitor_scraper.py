"""
경쟁사 모니터링 자동 캡처 — 브랜드검색(PC/MO) + 메타 광고 라이브러리 운영 소재 2종.

주의:
- search.naver.com과 facebook.com(Meta 광고 라이브러리)은 robots.txt/이용약관상 자동 수집을
  명시적으로 금지한다. 사용자 요청으로 저빈도(주 1회) 실행을 전제로 진행하되, 대량/고빈도 호출은
  절대 하지 않는다. 이 스크립트를 cron 등으로 하루에 여러 번 돌리지 말 것.
- Meta 광고 라이브러리는 브랜드명으로 키워드 검색하면 관련 없는 광고가 섞여 나온다. 브랜드별
  실제 계정명을 ACCOUNT_MAP에 미리 확인해 넣어 정확히 필터링한다 (2026-07-24 확인).
- 두 사이트 모두 마크업이 자주 바뀌는 편이라, 실패 시 조용히 넘어가지 말고 어떤 브랜드/슬롯이
  실패했는지 명확히 출력한다.
"""

import argparse
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

BRANDS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]

# 2026-07-24 기준 확인된 각 브랜드의 실제 메타 광고 라이브러리 계정명 (키워드 검색 결과와 다를 수 있음)
ACCOUNT_MAP = {
    "더한섬닷컴": "한섬",
    "신세계V": "VERY SHINSEGAE",
    "W컨셉": "W컨셉",
    "바바더닷컴": "바바더닷컴",
}

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S911N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)


def save_row(rows: list, brand: str, slot: str, image_bytes: bytes, run_date: date):
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (IMG_DIR / filename).write_bytes(image_bytes)
    rows.append({
        "date": run_date.isoformat(),
        "brand": brand,
        "slot": slot,
        "image_file": filename,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    })


def capture_naver(page, brand: str, rows: list, run_date: date, log: list):
    q = urllib.parse.quote(brand)
    try:
        page.goto(f"https://search.naver.com/search.naver?query={q}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        clip = {"x": 145, "y": 145, "width": 690, "height": 395}
        img = page.screenshot(clip=clip)
        save_row(rows, brand, "브랜드검색 PC", img, run_date)
        log.append(f"[OK] {brand} · 브랜드검색 PC")
    except Exception as e:
        log.append(f"[FAIL] {brand} · 브랜드검색 PC — {e}")


def capture_naver_mobile(browser, brand: str, rows: list, run_date: date, log: list):
    q = urllib.parse.quote(brand)
    # 뷰포트를 넉넉히 크게 잡아 브랜드검색 박스 전체(썸네일 3~5개 등 가변 높이)가 항상 다 렌더링되게 한다.
    mpage = browser.new_page(viewport={"width": 390, "height": 2000}, user_agent=MOBILE_UA, is_mobile=True)
    try:
        mpage.goto(f"https://m.search.naver.com/search.naver?query={q}", wait_until="networkidle", timeout=30000)
        mpage.wait_for_timeout(1500)

        # "홈페이지" 링크를 앵커로 조상을 한 단계씩 올라가며 박스 높이를 측정한다. 너무 얕으면
        # 제목줄만 잡히고, 너무 깊으면 페이지 전체(수천px)가 잡히므로, 그 사이의 "합리적인 카드
        # 크기"(<1200px) 중 가장 큰 것을 브랜드검색 박스로 판단한다. 박스마다 썸네일 개수(3~5개)가
        # 달라 고정 높이/고정 hop 수로는 브랜드마다 다르게 잘리는 문제가 있었음.
        home_link = mpage.get_by_text("홈페이지", exact=True).first
        handle = home_link.element_handle()
        best_box = None
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
                    best_box = box
        if not best_box:
            raise RuntimeError("브랜드검색 박스 높이를 판단하지 못함")
        bottom = int(best_box["y"] + best_box["height"]) + 8

        # 일부 브랜드는 "브랜드 SNS 소식" 섹션이 브랜드검색 박스와 같은 상위 컨테이너에 묶여 있어
        # 위 로직만으로는 그 섹션까지 포함돼버린다. 해당 제목이 박스 범위 안에 있으면 그 바로 위에서
        # 잘라낸다 (원하는 건 브랜드검색 박스만, SNS 소식은 제외).
        sns_heading = mpage.get_by_text("브랜드 SNS 소식", exact=True)
        if sns_heading.count() > 0:
            sns_box = sns_heading.first.bounding_box()
            if sns_box and sns_box["y"] < bottom:
                bottom = int(sns_box["y"]) - 12
        img = mpage.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": bottom})
        save_row(rows, brand, "브랜드검색 MO", img, run_date)
        log.append(f"[OK] {brand} · 브랜드검색 MO")
    except Exception as e:
        log.append(f"[FAIL] {brand} · 브랜드검색 MO — {e}")
    finally:
        mpage.close()


def capture_meta(page, brand: str, rows: list, run_date: date, log: list):
    account_name = ACCOUNT_MAP.get(brand)
    if not account_name:
        log.append(f"[SKIP] {brand} · 메타소재 — ACCOUNT_MAP에 계정명 미등록")
        return
    q = urllib.parse.quote(brand)
    url = (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country=KR&media_type=all&q={q}"
    )
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2500)
        markers = page.locator("text=라이브러리 ID:")
        total = markers.count()
        found = 0
        for i in range(total):
            if found >= 2:
                break
            marker = markers.nth(i)
            handle = marker.element_handle()
            card = page.evaluate_handle(
                """(el) => {
                    let node = el;
                    for (let j = 0; j < 8 && node.parentElement; j++) node = node.parentElement;
                    return node;
                }""",
                handle,
            ).as_element()
            text = card.inner_text()
            lines = [l for l in text.split("\n") if l.strip()]
            name_line = ""
            for idx, l in enumerate(lines):
                if l.strip() == "광고" and idx > 0:
                    name_line = lines[idx - 1].strip()
                    break
            if name_line == account_name:
                found += 1
                img = card.screenshot()
                save_row(rows, brand, f"메타소재 {found}", img, run_date)
                log.append(f"[OK] {brand} · 메타소재 {found} (계정: {name_line})")
        if found == 0:
            log.append(f"[FAIL] {brand} · 메타소재 — '{account_name}' 계정의 운영 중인 광고를 찾지 못함 (총 {total}건 중)")
    except Exception as e:
        log.append(f"[FAIL] {brand} · 메타소재 — {e}")


def run(brands: list[str], run_date: date) -> list[str]:
    rows = []
    log = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        for brand in brands:
            capture_naver(page, brand, rows, run_date, log)
            capture_naver_mobile(browser, brand, rows, run_date, log)
            capture_meta(page, brand, rows, run_date, log)
        browser.close()

    if rows:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = pd.read_csv(CSV_PATH, encoding="utf-8-sig", keep_default_na=False) if CSV_PATH.exists() else pd.DataFrame(
            columns=["date", "brand", "slot", "image_file", "uploaded_at"]
        )
        new_df = pd.DataFrame(rows)
        key_cols = ["date", "brand", "slot"]
        existing = existing.merge(new_df[key_cols].drop_duplicates(), on=key_cols, how="left", indicator=True)
        existing = existing[existing["_merge"] == "left_only"].drop(columns=["_merge"])
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    return log


def main():
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
