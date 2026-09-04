"""
스크래핑 직후 최신 데이터를 GitHub에 반영해, Streamlit Cloud에 배포된 대시보드도 함께
최신화되도록 한다 (배포된 앱은 로컬 data/ 폴더가 아니라 GitHub 저장소 내용을 그대로 읽는다).

경쟁사 이미지 폴더(data/competitor_monitor/images/)에는 스크래핑 과정에서 생기는
미참조 후보 이미지(예: 콘텐츠 사진 판별 실패로 버려진 후보, 같은 실행 중 덮어써진 이전 소재)가
계속 쌓이므로, 폴더 전체가 아니라 competitor_monitor.csv에 실제로 참조된 파일만 커밋한다.
그렇지 않으면 커밋할 때마다 저장소 용량이 무한정 불어난다.
"""

import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def referenced_image_paths() -> list[str]:
    csv_path = ROOT / "data" / "competitor_monitor" / "competitor_monitor.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False)
    return [f"data/competitor_monitor/images/{f}" for f in df["image_file"].unique() if f]


PUSH_RETRY_ATTEMPTS = 3


def sync_paths(paths: list[str], commit_message: str, log: list) -> None:
    """주어진 경로들만 골라 커밋+푸시한다 (범용). 폴더 전체를 add하지 않고 파일 단위로 골라야
    스크래핑 중 생기는 미참조 파일(예: 경쟁사 이미지 후보)이 저장소에 계속 쌓이는 걸 막을 수 있다.

    푸시가 실패하면(다른 워크플로/사용자가 그 사이 먼저 푸시한 경우 등) `git pull --rebase`로
    받아온 뒤 재시도한다 (최대 PUSH_RETRY_ATTEMPTS번). 이걸 안 하면 특히 원격 새로고침처럼 여러
    GitHub Actions 실행이 겹칠 수 있는 흐름에서, 이번 실행이 남긴 "신호 파일 삭제" 커밋이 끝내
    원격에 반영되지 못한 채로 남는다 — 그러면 다음 실행이 신호 파일을 다시 "대기 중"으로 보고
    같은 요청을 계속 재처리하는 무한 재시도가 생긴다 (2026-09-04 발견: app_search/naver 원격
    새로고침이 이 버그로 몇 주간 수백 번 중복 처리됨, robots.txt로 막힌 사이트에 저빈도 원칙보다
    훨씬 잦은 요청이 감)."""
    existing = [p for p in paths if (ROOT / p).exists()]
    if not existing:
        log.append("[SKIP] GitHub에 반영할 데이터 파일이 없음")
        return
    try:
        subprocess.run(
            ["git", "add", *existing], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8"
        )
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
        if diff.returncode == 0:
            log.append("[INFO] GitHub에 반영할 변경 사항 없음 (데이터 동일)")
            return
        subprocess.run(
            ["git", "commit", "-m", commit_message], cwd=ROOT, check=True, capture_output=True, text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as e:
        log.append(f"[FAIL] GitHub 반영 실패 (add/commit): {e.stderr}")
        return

    last_error = None
    for attempt in range(1, PUSH_RETRY_ATTEMPTS + 1):
        try:
            subprocess.run(
                ["git", "push", "origin", "master"], cwd=ROOT, check=True, capture_output=True, text=True,
                encoding="utf-8",
            )
            log.append("[OK] GitHub에 최신 데이터 반영 완료 (배포된 대시보드도 곧 갱신됩니다)")
            return
        except subprocess.CalledProcessError as e:
            last_error = e.stderr
            if attempt == PUSH_RETRY_ATTEMPTS:
                break
            rebase = subprocess.run(
                ["git", "pull", "--rebase", "origin", "master"], cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8",
            )
            if rebase.returncode != 0:
                last_error = rebase.stderr
                break

    log.append(f"[FAIL] GitHub 반영 실패 (push, {PUSH_RETRY_ATTEMPTS}회 재시도 후): {last_error}")


def sync_to_github(commit_message: str, log: list) -> None:
    """경쟁사 모니터링 전용 (weekly_archive.py에서 사용)."""
    paths = [
        "data/competitor_monitor/competitor_monitor.csv",
        "data/competitor_monitor/archive_weeks.csv",
        "data/competitor_monitor/comments.csv",
        "data/competitor_monitor/keywords.csv",
    ] + referenced_image_paths()
    sync_paths(paths, commit_message, log)
