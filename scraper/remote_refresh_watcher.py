"""
원격 새로고침 감시자 — 배포된 대시보드(Streamlit Cloud)는 Playwright가 없어 직접 스크래핑할 수
없다. 대신 배포된 화면의 "새로고침 요청" 버튼을 누르면 GitHub API로 data/refresh_signal.json에
요청을 기록하고, 이 스크립트가 로컬 PC에서 5분마다 그 파일을 확인해 실제 스크래핑을 수행한다.

이렇게 해도 실제 사이트 스크래핑 자체는 "사용자가 명시적으로 요청했을 때만" 실행된다 —
5분마다 도는 건 GitHub 저장소 확인(가벼운 git pull)일 뿐, 네이버/더한섬닷컴 등 대상 사이트에는
아무 요청도 가지 않는다. 즉 기존 저빈도·수동 트리거 원칙은 그대로 유지된다.

처리 후에는 신호 파일을 삭제해 같은 요청이 중복 처리되지 않게 한다.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNAL_PATH = ROOT / "data" / "refresh_signal.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_sync  # noqa: E402

SCRIPT_MAP = {
    "naver": (ROOT / "scraper" / "naver_datalab_scraper.py", ["data/naver_top10"]),
    "app_search": (ROOT / "scraper" / "app_search_scraper.py", ["data/app_search"]),
}


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def run_scraper(script_path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(script_path)], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    log_text = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, log_text


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    pull = git("pull", "origin", "master")
    if pull.returncode != 0:
        print(f"[FAIL] git pull 실패: {pull.stderr}", file=sys.stderr)
        sys.exit(1)

    if not SIGNAL_PATH.exists():
        print("[SKIP] 대기 중인 새로고침 요청 없음")
        return

    try:
        signal = json.loads(SIGNAL_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[FAIL] 신호 파일 파싱 실패, 삭제하고 종료: {e}", file=sys.stderr)
        SIGNAL_PATH.unlink(missing_ok=True)
        return

    target = signal.get("target")
    requested_at = signal.get("requested_at")
    print(f"[OK] 새로고침 요청 감지: target={target}, requested_at={requested_at}")

    entry = SCRIPT_MAP.get(target)
    log = []
    extra_paths = []
    if entry is None:
        log.append(f"[FAIL] 알 수 없는 target: {target}")
    else:
        script_path, extra_paths = entry
        ok, scrape_log = run_scraper(script_path)
        print(scrape_log)
        log.append(f"[OK] {target} 스크래핑 완료" if ok else f"[FAIL] {target} 스크래핑 실패")

    SIGNAL_PATH.unlink(missing_ok=True)

    today = date.today().isoformat()
    git_sync.sync_paths(
        extra_paths + ["data/refresh_signal.json"],
        f"원격 새로고침 처리: {target} ({today})",
        log,
    )
    for line in log:
        print(line)


if __name__ == "__main__":
    main()
