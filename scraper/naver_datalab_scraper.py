"""
네이버 데이터랩 쇼핑인사이트 - 패션의류(여성의류) / 패션잡화 TOP40 인기검색어 스크래퍼.

주의:
- 공식 API는 이 랭킹 데이터를 제공하지 않는다 (지정 키워드의 클릭 추이만 제공). 그래서 웹 화면을
  직접 렌더링해서 파싱한다.
- 저빈도 원칙: 이 스크립트는 사용자가 대시보드에서 "새로고침" 버튼을 눌렀을 때만 1회 실행되어야 한다.
  cron 등으로 반복 스케줄링하지 않는다.
- 셀렉터는 2026-07-24 실제 페이지 HTML을 직접 덤프해 확인한 구조 기준으로 작성됨:
  카테고리는 `.set_period.category` 안의 첫 번째(대분류)/두 번째(2분류) `.select` 드롭다운에서 클릭.
  기간(일간/1개월)은 페이지 기본값이 요구사항과 동일해 별도 조작 불필요.
- 패션잡화는 2분류(서브카테고리)를 지정하지 않고 대분류 전체로 조회한다 (사용자 확인, 2026-07-24).
"""

import argparse
import csv
import sys
from datetime import datetime, date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://datalab.naver.com/shoppingInsight/sCategory.naver"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "naver_top10"
TARGET_COUNT = 40
ITEMS_PER_PAGE = 20  # 네이버 인기검색어 리스트 1페이지당 노출 개수 (TOP500 / 25페이지 기준)

CATEGORIES = [
    {"slug": "fashion_women", "level1": "패션의류", "level2": "여성의류", "label": "네이버 패션의류"},
    {"slug": "fashion_accessories", "level1": "패션잡화", "level2": None, "label": "네이버 패션잡화"},
]


def scrape_category(page, level1: str, level2: str | None) -> list[dict]:
    page.goto(URL, wait_until="networkidle", timeout=30000)

    category_selects = page.locator(".set_period.category .select")
    category_selects.nth(0).locator(".select_btn").click(timeout=10000)
    category_selects.nth(0).locator(f".select_list .option:has-text('{level1}')").click(timeout=10000)

    if level2:
        category_selects.nth(1).locator(".select_btn").click(timeout=10000)
        category_selects.nth(1).locator(f".select_list .option:has-text('{level2}')").click(timeout=10000)

    page.click("a.btn_submit", timeout=10000)
    page.wait_for_timeout(1500)
    page.wait_for_selector(".rank_top1000_list li", timeout=15000)

    results = []
    seen_ranks = set()
    pages_clicked = 0
    max_pages = (TARGET_COUNT + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    while len(results) < TARGET_COUNT and pages_clicked < max_pages:
        rows = page.query_selector_all(".rank_top1000_list li")
        for row in rows:
            num_el = row.query_selector(".rank_top1000_num")
            if not num_el:
                continue
            rank = int(num_el.inner_text().strip())
            if rank in seen_ranks or rank > TARGET_COUNT:
                continue
            text = row.inner_text().strip()
            keyword = text.lstrip("0123456789. \n").strip()
            results.append({"rank": rank, "keyword": keyword})
            seen_ranks.add(rank)

        pages_clicked += 1
        if len(results) < TARGET_COUNT:
            next_btn = page.query_selector(".btn_page_next")
            if not next_btn:
                break
            next_btn.click()
            page.wait_for_timeout(1000)

    results.sort(key=lambda r: r["rank"])
    return results


def scrape(debug: bool = False) -> dict[str, list[dict]]:
    all_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        page = browser.new_page()
        try:
            for cat in CATEGORIES:
                all_results[cat["slug"]] = scrape_category(page, cat["level1"], cat["level2"])
                if debug:
                    (DATA_DIR / f"_debug_{cat['slug']}.png").parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(DATA_DIR / f"_debug_{cat['slug']}.png"), full_page=True)
        finally:
            browser.close()
    return all_results


def save_csv(slug: str, category_label: str, results: list[dict], target_date: date) -> Path:
    out_dir = DATA_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date.isoformat()}.csv"
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["rank", "keyword", "category", "collected_at"])
        writer.writeheader()
        collected_at = datetime.now().isoformat(timespec="seconds")
        for row in results:
            writer.writerow({
                "rank": row["rank"],
                "keyword": row["keyword"],
                "category": category_label,
                "collected_at": collected_at,
            })
    return out_path


def main():
    # Windows 콘솔 기본 코드페이지(cp949)로는 일부 출력(특히 Playwright 에러 메시지에 섞여 나오는
    # 특수기호)이 UnicodeEncodeError로 죽어서 실제 성공 여부와 무관하게 "실패"로 보이는 문제가 있었다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="스크린샷 저장, 브라우저 창 표시")
    args = parser.parse_args()

    try:
        all_results = scrape(debug=args.debug)
    except PlaywrightTimeoutError as e:
        print(f"스크래핑 실패: 페이지 요소를 찾지 못했습니다 (사이트 구조가 바뀌었을 수 있음). "
              f"--debug 옵션으로 재실행해 스크린샷을 확인하세요.\n원본 에러: {e}", file=sys.stderr)
        sys.exit(1)

    had_failure = False
    for cat in CATEGORIES:
        results = all_results.get(cat["slug"], [])
        if not results:
            print(f"스크래핑 실패: {cat['label']} 랭킹을 파싱했지만 결과가 비어 있습니다.", file=sys.stderr)
            had_failure = True
            continue
        category_label = cat["level1"] if not cat["level2"] else f"{cat['level1']}>{cat['level2']}"
        out_path = save_csv(cat["slug"], category_label, results, date.today())
        print(f"저장 완료: {out_path} ({len(results)}건)")

    if had_failure:
        sys.exit(1)


if __name__ == "__main__":
    main()
