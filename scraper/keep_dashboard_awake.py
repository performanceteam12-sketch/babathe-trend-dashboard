"""
대시보드 깨어있게 유지 — Streamlit Community Cloud 무료 플랜은 일정 기간 방문자가 없으면
앱을 "잠자기 모드"로 전환한다(방문 시 "Zzzz... Yes, get this app back up!" 화면이 뜸).

단순 HTTP GET만으로는 부족하다 — Streamlit 앱은 WebSocket으로 실제 세션이 열려야 "방문"으로
잡히고, 잠자기 화면이 떠 있을 땐 "Yes, get this app back up!" 버튼을 실제로 눌러야 깨어난다.
그래서 Playwright로 실제 브라우저 방문을 재현한다 (scraper의 다른 스크립트들과 동일한 방식).

.streamlit/secrets.toml의 dashboard_url 키를 그대로 재사용한다 (scraper/monday_update.py와 동일 패턴).
"""

import sys
import tomllib
from pathlib import Path

from playwright.sync_api import sync_playwright

SECRETS_PATH = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def load_dashboard_url() -> str | None:
    if not SECRETS_PATH.exists():
        return None
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f).get("dashboard_url")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    url = load_dashboard_url()
    if not url:
        print("[SKIP] dashboard_url이 .streamlit/secrets.toml에 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            wake_button = page.get_by_text("Yes, get this app back up!")
            if wake_button.count() > 0:
                wake_button.click()
                page.wait_for_timeout(15000)
                print("[OK] 잠자기 모드에서 깨움")
            else:
                print("[OK] 대시보드 정상 접속 (이미 깨어있음)")
            browser.close()
    except Exception as e:  # noqa: BLE001 — 실패해도 다음 스케줄에 재시도되면 되므로 크래시시키지 않는다
        print(f"[FAIL] 대시보드 접속 실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
