"""
원격 새로고침 감시자 — 배포된 대시보드(Streamlit Cloud)는 Playwright가 없어 직접 스크래핑할 수
없다. 대신 배포된 화면의 "새로고침 요청" 버튼을 누르면 GitHub API로 data/refresh_signal.json에
요청을 기록하고 곧바로 이 워크플로(.github/workflows/remote-refresh-watcher.yml)를
workflow_dispatch로 트리거해, 이 스크립트가 그 파일을 확인해 실제 스크래핑을 수행한다.

원래는 로컬 PC의 Windows 작업 스케줄러가 이 역할을 했으나, PC 화면이 잠긴 상태에서는 스케줄러가
Playwright를 실행하지 못하는 문제(오류 0x800710E0)가 있어 2026-08-06에 GitHub Actions로 옮겼다.
로컬 작업(BabaderRemoteRefreshWatcher)은 그 뒤로도 중복 실행되고 있다가 2026-09-04에 삭제됨.

**2026-09-04: 5분 주기 cron 폴링을 제거하고 workflow_dispatch 전용으로 전환.** 원래는 cron이
5분마다 신호 파일 존재 여부를 확인해 dispatch가 실패해도 백업 처리를 해줬는데, git_sync.py의
push에 재시도 로직이 없던 것과 겹쳐 "신호 삭제 커밋"의 푸시가 실패할 때마다 신호가 원격에
그대로 남아 다음 cron이 같은 요청을 또 처리하는 무한 재시도 버그가 있었다 — 실제 버튼 클릭은
14번뿐인데 naver/app_search 처리 커밋이 수백 건씩 쌓였다(robots.txt로 막힌 사이트에 저빈도
원칙보다 훨씬 잦은 요청이 감, 사용자 문의로 발견). git_sync.py는 push 실패 시 재시도하도록
고쳤지만(재발 방지), 애초에 상시 폴링 자체가 저빈도 원칙과 안 맞아 cron은 완전히 없앴다 —
이제 사용자가 새로고침 버튼을 눌렀을 때(workflow_dispatch)만 실행된다.

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
    "naver": (ROOT / "scraper" / "naver_datalab_scraper.py", lambda: ["data/naver_top10"]),
    "app_search": (ROOT / "scraper" / "app_search_scraper.py", lambda: ["data/app_search"]),
    # 경쟁사 모니터링은 images/ 폴더 전체가 아니라 competitor_monitor.csv에 실제로 참조된
    # 이미지만 동기화해야 해서(git_sync.py 참고) 고정 경로 리스트 대신 스크래핑 후에 평가되는
    # 함수로 넘긴다.
    "competitor_monitor": (
        ROOT / "scraper" / "competitor_monitor_scraper.py",
        lambda: [
            "data/competitor_monitor/competitor_monitor.csv",
            "data/competitor_monitor/keywords.csv",
        ] + git_sync.referenced_image_paths(),
    ),
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
        script_path, paths_fn = entry
        ok, scrape_log = run_scraper(script_path)
        print(scrape_log)
        log.append(f"[OK] {target} 스크래핑 완료" if ok else f"[FAIL] {target} 스크래핑 실패")
        extra_paths = paths_fn()  # 스크래핑 이후에 평가해야 갱신된 CSV 기준 참조 이미지가 잡힌다

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
