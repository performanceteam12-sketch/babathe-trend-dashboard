"""
브랜드 자사 사이트 실시간/인기 검색어 자동 캡처 — 더한섬닷컴 / 신세계V / W컨셉 / 바바더닷컴.

주의:
- 2026-07-24 최초 조사 당시에는 이 데이터가 앱 전용이라 자동 수집이 불가능하다고 결론 냈으나,
  실제로는 각 사이트 PC 웹의 검색창을 클릭하면 나오는 오버레이에 노출되는 것을 사용자가 직접
  확인해줘서 정정함. 검색창을 열어야 렌더링되는 내용이라 정적 페이지 로드만으로는 보이지 않았음.
- robots.txt 확인 결과(2026-07-24):
    - shinsegaev.com, babathe.com(자사): User-agent: * Allow: / — 일반 크롤러 허용, 문제 없음
    - thehandsome.com, display.wconcept.co.kr: User-agent: * Disallow: / (화이트리스트 방식) —
      일반 자동화는 차단 대상. 사용자가 저빈도(주 1회) 실행 조건으로 진행을 명시적으로 승인함
      (2026-07-24). 실행 빈도를 늘리지 말 것.
- 셀렉터는 검색창 클릭 좌표 기반이라 사이트 리뉴얼 시 깨지기 쉽다. 브랜드별로 독립적으로
  실패를 잡아 어떤 브랜드가 실패했는지 명확히 보고한다 (한 브랜드 실패가 나머지를 막지 않음).
"""

import argparse
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
APP_SEARCH_DIR = ROOT / "data" / "app_search"
TARGET_COUNT = 10


def capture_thehandsome(browser) -> list[str]:
    # 페이지에 "인기 검색어"/"급상승 검색어" 두 개의 word-list 캐러셀이 있는데, "인기 검색어" 쪽은
    # 무한 루프용 빈 슬롯(li는 있지만 .word가 없음)이 섞여 있어 그대로 쓰면 개수가 맞지 않는다.
    # 그래서 여러 search-swiper-box 중 앞부분 항목이 전부 채워진(=빈 슬롯이 없는) 쪽을
    # "급상승 검색어"로 판단해서 그걸 사용한다.
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        page.goto("https://www.thehandsome.com/", wait_until="load", timeout=45000)
        page.wait_for_timeout(1500)
        page.mouse.click(1197, 36)  # 검색 아이콘
        page.wait_for_timeout(1500)
        page.wait_for_selector(".search-swiper-box ul.word-list li", timeout=10000)

        boxes = page.query_selector_all(".search-swiper-box")
        for box in boxes:
            word_list = box.query_selector("ul.word-list")
            if not word_list:
                continue
            items = word_list.query_selector_all("li")
            words = []
            for item in items[:TARGET_COUNT]:
                word_el = item.query_selector(".word")
                words.append(word_el.inner_text().strip() if word_el else None)
            if len(words) >= TARGET_COUNT and all(words):
                return words
        return []
    finally:
        page.close()


def capture_shinsegaev(browser) -> list[str]:
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        page.goto("https://www.shinsegaev.com/", wait_until="load", timeout=45000)
        page.wait_for_timeout(2000)
        try:
            page.click("text=오늘 하루 보지 않기", timeout=3000)
        except Exception:
            pass
        page.mouse.click(1114, 38)  # 검색 아이콘
        page.wait_for_timeout(1500)
        page.wait_for_selector("#popular_search_keyword_list li", timeout=10000)
        items = page.query_selector_all("#popular_search_keyword_list li")
        keywords = []
        for item in items[:TARGET_COUNT]:
            word_el = item.query_selector(".v-rank-item__keyword")
            if word_el:
                keywords.append(word_el.inner_text().strip())
        return keywords
    finally:
        page.close()


def capture_wconcept(browser) -> list[str]:
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        page.goto("https://display.wconcept.co.kr/", wait_until="load", timeout=45000)
        page.wait_for_timeout(2000)
        try:
            page.click("text=닫기", timeout=3000)
        except Exception:
            pass
        page.mouse.click(1200, 84)  # 검색창
        page.wait_for_timeout(1500)
        page.wait_for_selector("li.rank-text-item", timeout=10000)
        items = page.query_selector_all("li.rank-text-item")
        keywords = []
        for item in items[:TARGET_COUNT]:
            word_el = item.query_selector(".word")
            if word_el:
                keywords.append(word_el.inner_text().strip())
        return keywords
    finally:
        page.close()


def capture_babathe(browser) -> list[str]:
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        page.goto("https://www.babathe.com/", wait_until="load", timeout=45000)
        page.wait_for_timeout(2000)
        try:
            page.click("text=팝업닫기", timeout=3000)
        except Exception:
            pass
        page.mouse.click(1213, 57)  # 검색 아이콘
        page.wait_for_timeout(1500)
        page.wait_for_selector("#realKeyword li", timeout=10000)
        items = page.query_selector_all("#realKeyword li")
        keywords = []
        for item in items[:TARGET_COUNT]:
            word_el = item.query_selector(".text")
            if word_el:
                keywords.append(word_el.inner_text().strip())
        return keywords
    finally:
        page.close()


CHANNELS = [
    {"name": "더한섬닷컴", "fn": capture_thehandsome},
    {"name": "신세계V", "fn": capture_shinsegaev},
    {"name": "W컨셉", "fn": capture_wconcept},
    {"name": "바바더닷컴", "fn": capture_babathe},
]


def save_channel(channel: str, keywords: list[str], target_date: date):
    APP_SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    out_path = APP_SEARCH_DIR / f"{target_date.isoformat()}.csv"
    existing = pd.read_csv(out_path, encoding="utf-8-sig") if out_path.exists() else pd.DataFrame(
        columns=["channel", "rank", "keyword", "input_by", "input_at"]
    )
    existing = existing[existing["channel"] != channel]
    new_rows = pd.DataFrame([
        {
            "channel": channel,
            "rank": i + 1,
            "keyword": kw,
            "input_by": "auto",
            "input_at": datetime.now().isoformat(timespec="seconds"),
        }
        for i, kw in enumerate(keywords)
    ])
    pd.concat([existing, new_rows], ignore_index=True).to_csv(out_path, index=False, encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", nargs="*", help="캡처할 브랜드만 지정 (기본: 전체 4개)")
    args = parser.parse_args()

    targets = CHANNELS
    if args.channels:
        targets = [c for c in CHANNELS if c["name"] in args.channels]

    log = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for ch in targets:
            try:
                keywords = ch["fn"](browser)
                if not keywords:
                    log.append(f"[FAIL] {ch['name']} — 검색어를 파싱했지만 결과가 비어 있습니다.")
                    continue
                save_channel(ch["name"], keywords, date.today())
                log.append(f"[OK] {ch['name']} ({len(keywords)}건)")
            except Exception as e:
                log.append(f"[FAIL] {ch['name']} — {e}")
        browser.close()

    for line in log:
        print(line)

    if any(line.startswith("[FAIL]") for line in log):
        sys.exit(1)


if __name__ == "__main__":
    main()
