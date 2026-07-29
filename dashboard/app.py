"""바바더닷컴 패션 트렌드 대시보드. 새 날짜 데이터가 추가되면 새로고침 버튼으로 다시 스캔한다."""

import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
NAVER_DIR = ROOT / "data" / "naver_top10"
APP_SEARCH_DIR = ROOT / "data" / "app_search"
COMPETITOR_DIR = ROOT / "data" / "competitor_monitor"
COMPETITOR_IMG_DIR = COMPETITOR_DIR / "images"
COMPETITOR_CSV = COMPETITOR_DIR / "competitor_monitor.csv"
COMPETITOR_KEYWORDS_CSV = COMPETITOR_DIR / "keywords.csv"
COMPETITOR_COMMENTS_CSV = COMPETITOR_DIR / "comments.csv"
SCRAPER_SCRIPT = ROOT / "scraper" / "naver_datalab_scraper.py"
APP_SEARCH_SCRAPER_SCRIPT = ROOT / "scraper" / "app_search_scraper.py"
COMPETITOR_SCRAPER_SCRIPT = ROOT / "scraper" / "competitor_monitor_scraper.py"

APP_CHANNELS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]
COMPETITOR_BRANDS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]
COMPETITOR_SLOTS = ["브랜드검색 PC", "브랜드검색 MO", "메타소재 1", "메타소재 2"]
NAV_ITEMS = ["경쟁사 모니터링", "실시간 인기 검색어"]

# 새로고침(Playwright 스크래핑)은 사용자 PC(Windows)에서만 동작한다 — Streamlit Cloud(Linux)에는
# 브라우저 바이너리가 없어서 실행하면 항상 실패한다. 배포된 대시보드에서는 버튼 자체를 숨기고
# "로컬 예약 작업으로 자동 갱신됩니다" 안내만 보여준다 (실패 트레이스백을 노출하지 않기 위함).
IS_LOCAL = sys.platform == "win32"

st.set_page_config(
    page_title="바바더닷컴 패션 트렌드 대시보드",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# 스타일
# ---------------------------------------------------------------------------
def inject_style():
    st.markdown(
        """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

        html, body, [class*="css"] { font-family: 'Pretendard', -apple-system, sans-serif; }

        /* 앱 배경: 사이드바·카드가 그 위에 떠 있는 느낌을 주는 옅은 라벤더 톤 */
        [data-testid="stAppViewContainer"] { background: #F4F1FC; }
        header[data-testid="stHeader"] { background: transparent; }

        .block-container { padding: 2.25rem 3rem 3rem; max-width: 1240px; }

        h1, h2, h3, h4 { letter-spacing: -0.01em; color: #211B36; }

        /* 사이드바: 앱 배경과 분리된 흰색 라운드 카드처럼 */
        section[data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: none;
            margin: 14px 0 14px 14px;
            border-radius: 22px;
            box-shadow: 0 4px 24px rgba(124, 58, 237, 0.08);
        }
        section[data-testid="stSidebar"] .block-container { padding: 1.75rem 1rem; }

        .brand-mark {
            display: flex; align-items: center; gap: 10px;
            padding: 0 0.5rem 1.25rem; margin-bottom: 0.75rem;
            border-bottom: 1px solid #F1EDFB;
        }
        .brand-mark .logo {
            width: 34px; height: 34px; border-radius: 11px;
            background: linear-gradient(135deg, #8B5CF6, #6D28D9); color: white; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px; flex-shrink: 0;
            box-shadow: 0 3px 10px rgba(109, 40, 217, 0.3);
        }
        .brand-mark .name { font-weight: 700; font-size: 15px; color: #211B36; }
        .brand-mark .sub { font-size: 11px; color: #A29BC2; margin-top: 1px; }

        /* 네비게이션 라디오 -> 리스트 형태로 재구성 */
        section[data-testid="stSidebar"] div[role="radiogroup"] {
            display: flex; flex-direction: column; gap: 2px; padding: 0 0.5rem;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            padding: 11px 12px; border-radius: 12px; color: #6B6483;
            font-weight: 500; font-size: 14px; transition: background .12s ease;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: #F7F4FD; }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
            background: linear-gradient(120deg, #8B5CF6, #7C3AED); color: #FFFFFF; font-weight: 600;
            box-shadow: 0 4px 12px rgba(124, 58, 237, 0.28);
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none; }

        /* 사이드바 내 버튼(주차별 아카이브 토글 + 주차 목록) - 테두리 없는 플랫 서브 네비 스타일 */
        section[data-testid="stSidebar"] div[data-testid="stButton"] button {
            background: transparent; border: none; box-shadow: none;
            color: #6B6483; font-weight: 500; font-size: 13px;
            text-align: left; justify-content: flex-start; padding: 7px 12px;
            border-radius: 10px; width: 100%;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
            background: #F7F4FD; color: #7C3AED;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button p { font-size: 13px; }

        /* 메인 화면의 액션 버튼(새로고침 등) — 기본 스트림릿 흰색 테두리 박스 대신 퍼플 필 버튼 */
        section[data-testid="stMain"] div[data-testid="stButton"] button {
            background: linear-gradient(120deg, #8B5CF6, #7C3AED); color: #FFFFFF; border: none;
            border-radius: 12px; font-weight: 700; padding: 10px 18px;
            box-shadow: 0 4px 12px rgba(124, 58, 237, 0.25);
        }
        section[data-testid="stMain"] div[data-testid="stButton"] button:hover {
            background: linear-gradient(120deg, #7C3AED, #6D28D9);
            box-shadow: 0 4px 16px rgba(124, 58, 237, 0.35);
        }
        section[data-testid="stMain"] div[data-testid="stButton"] button p { color: #FFFFFF; }
        section[data-testid="stMain"] div[data-testid="stFormSubmitButton"] button {
            background: linear-gradient(120deg, #8B5CF6, #7C3AED); color: #FFFFFF; border: none;
            border-radius: 12px; font-weight: 700; box-shadow: 0 4px 12px rgba(124, 58, 237, 0.25);
        }
        section[data-testid="stMain"] div[data-testid="stFormSubmitButton"] button p { color: #FFFFFF; }

        /* 페이지 공통 헤더 (제목 + 설명 + 최신 기준일 배지) */
        .page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 1.1rem; }
        .page-header .titles h3 { margin: 0 0 4px; font-size: 24px; }
        .page-header .titles .section-desc { margin-bottom: 0; }
        .page-header .badge {
            flex-shrink: 0; background: #EDE6FC; color: #7C3AED; font-weight: 700;
            font-size: 12.5px; padding: 7px 14px; border-radius: 999px; white-space: nowrap;
            margin-top: 2px;
        }

        /* 공통 카드 */
        .stat-row { display: flex; gap: 14px; margin: 0.25rem 0 1.75rem; flex-wrap: wrap; }
        .stat-card {
            flex: 1; min-width: 170px; border: none;
            border-radius: 20px; padding: 18px 20px;
            box-shadow: 0 2px 10px rgba(124, 58, 237, 0.06);
            display: flex; align-items: center; gap: 14px;
        }
        .stat-card .icon-chip {
            width: 40px; height: 40px; border-radius: 13px; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center; font-size: 19px;
            background: rgba(255,255,255,0.55);
        }
        .stat-card .label { font-size: 12.5px; color: #6B6483; font-weight: 500; opacity: 0.85; }
        .stat-card .value { font-size: 28px; font-weight: 700; color: #211B36; margin-top: 4px; letter-spacing: -0.02em; }
        .stat-card:nth-child(3n+1) { background: #EDE6FC; }
        .stat-card:nth-child(3n+2) { background: #DDF1FB; }
        .stat-card:nth-child(3n+3) { background: #FFE9D9; }

        .section-desc { color: #71717A; font-size: 14px; margin-bottom: 1.25rem; }

        /* 브랜드 요약 카드 (경쟁사 모니터링 상단 — 회의 시작할 때 스크롤 없이 한눈에) */
        .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.75rem; }
        .summary-card,
        .summary-card:link,
        .summary-card:visited,
        .summary-card:hover,
        .summary-card * {
            text-decoration: none !important;
        }
        .summary-card {
            background: #FFFFFF; border-radius: 16px; padding: 14px 16px;
            box-shadow: 0 2px 10px rgba(124, 58, 237, 0.06); display: block;
        }
        .summary-card:hover { box-shadow: 0 4px 16px rgba(124, 58, 237, 0.14); }
        .summary-card .summary-brand { font-weight: 700; font-size: 14.5px; color: #211B36; margin-bottom: 6px; }
        .summary-card .summary-comment {
            font-size: 12.5px; color: #6B6483; line-height: 1.45;
            display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
        }
        .summary-card .summary-empty { font-size: 12.5px; color: #C2B8E0; }

        .brand-block {
            border: none; border-radius: 20px; padding: 18px 20px 8px;
            margin-bottom: 22px; background: #FFFFFF; overflow: hidden;
            box-shadow: 0 2px 14px rgba(124, 58, 237, 0.07);
            scroll-margin-top: 20px;
        }
        .brand-header {
            background: linear-gradient(120deg, #8B5CF6, #6D28D9);
            margin: -18px -20px 16px; padding: 19px 22px;
        }
        .brand-header .brand-title {
            font-weight: 800; font-size: 22px; color: #FFFFFF; letter-spacing: -0.02em;
        }

        /* 랭킹 카드 (실시간 인기 검색어) */
        .rank-card {
            background: #FFFFFF; border: none; border-radius: 22px;
            padding: 20px 22px 8px; box-shadow: 0 2px 14px rgba(124, 58, 237, 0.07);
        }
        .rank-card-head { display: flex; justify-content: space-between; align-items: flex-start; }
        .rank-card-title { font-weight: 700; font-size: 17px; color: #211B36; }
        .rank-card-badge {
            background: #EDE6FC; color: #7C3AED; font-size: 12px; font-weight: 700;
            padding: 3px 11px; border-radius: 999px; flex-shrink: 0;
        }
        .rank-card-meta {
            display: flex; justify-content: space-between; align-items: baseline;
            font-size: 12px; color: #9992B3; margin: 3px 0 12px;
        }
        .rank-card-meta a { color: #9992B3; text-decoration: none; }
        .rank-card-meta a:hover { color: #7C3AED; }
        .rank-list { max-height: 460px; overflow-y: auto; }
        .rank-item {
            display: flex; align-items: center; gap: 12px; padding: 8.5px 2px;
            border-bottom: 1px solid #F5F2FB; font-size: 14px;
        }
        .rank-item:last-child { border-bottom: none; }
        .rank-item .num { width: 18px; text-align: center; font-weight: 700; color: #B3ABCF; font-size: 13px; }
        .rank-item.top .num { color: #7C3AED; }
        .rank-item .kw { color: #2E2748; }

        .media-empty {
            aspect-ratio: 4/3; background: #FAF8FE; border: 1px dashed #DDD3F5; border-radius: 12px;
            display: flex; align-items: center; justify-content: center; color: #C2B8E0; font-size: 13px;
        }
        /* 미디어 카드: 기존 경쟁사 동향 시트의 "이미지 아래 회색 캡션 바" 레이아웃 재현 */
        .rank-card.media-card { padding: 14px 14px 0; }
        .media-caption {
            display: flex; align-items: baseline; justify-content: center; gap: 8px;
            background: #F5F2FB; border-radius: 0 0 12px 12px; margin: 10px -14px -14px;
            padding: 9px 10px; text-align: center;
        }
        .media-caption-title { font-weight: 700; font-size: 13px; color: #4C4569; }
        .media-caption-meta { font-size: 11.5px; color: #9992B3; }

        /* 서브섹션 라벨(브랜드검색/메타 광고 소재)을 회색 바 형태로 — 기존 시트의 "1-2. 브랜드검색" 행 헤더 느낌 */
        .group-label {
            font-size: 13px; font-weight: 700; color: #4C4569; margin: 4px 0 10px;
            background: #F5F2FB; padding: 8px 14px; border-radius: 10px;
        }
        .keyword-pill {
            display: inline-block; background: #EDE6FC; color: #7C3AED; font-weight: 600;
            font-size: 12px; padding: 4px 11px; border-radius: 999px; margin: 0 6px 6px 0;
        }
        .keyword-empty { color: #C2B8E0; font-size: 13px; }

        .comment-box {
            background: #FFF8E8; border: 1px solid #FDE9BE; border-radius: 14px;
            padding: 12px 16px; margin: 10px 0 4px; font-size: 14.5px; color: #7A4E10;
            line-height: 1.55;
        }
        .comment-box .comment-label {
            display: inline-block; background: #F59E0B; color: #FFFFFF; font-size: 11px;
            font-weight: 800; padding: 2px 10px; border-radius: 999px; margin-right: 8px;
            vertical-align: middle;
        }

        /* 알림/상태 메시지(성공·실패·안내) 테마 통일 — 기본 스트림릿 회색/빨강 배너 대신 퍼플 팔레트 톤 */
        [data-testid="stAlert"] {
            border-radius: 14px; border: none; border-left: 4px solid transparent;
            padding: 12px 16px;
        }
        [data-testid="stAlertContainer"]:has(div[data-testid="stNotificationContentSuccess"]) {
            background: #EAFBF1; border-left-color: #22C55E;
        }
        [data-testid="stAlertContainer"]:has(div[data-testid="stNotificationContentError"]) {
            background: #FDECEC; border-left-color: #EF4444;
        }
        [data-testid="stAlertContainer"]:has(div[data-testid="stNotificationContentInfo"]) {
            background: #EDE6FC; border-left-color: #7C3AED;
        }
        [data-testid="stAlertContainer"]:has(div[data-testid="stNotificationContentWarning"]) {
            background: #FFF3DE; border-left-color: #F59E0B;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def stat_row(items: list[tuple[str, str, str]]):
    """items: (label, value, icon) 튜플 리스트. icon은 이모지 1개."""
    html = '<div class="stat-row">' + "".join(
        f'<div class="stat-card"><div class="icon-chip">{icon}</div>'
        f'<div><div class="label">{label}</div><div class="value">{value}</div></div></div>'
        for label, value, icon in items
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def page_header(title: str, desc: str, badge_text: str | None = None):
    badge_html = f'<div class="badge">{badge_text}</div>' if badge_text else ""
    st.markdown(
        f"""<div class="page-header">
            <div class="titles">
                <h3>{title}</h3>
                <div class="section-desc">{desc}</div>
            </div>
            {badge_html}
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 실시간 인기 검색어
# ---------------------------------------------------------------------------
NAVER_CATEGORIES = [
    {"slug": "fashion_women", "title": "네이버 패션의류", "meta": "패션의류 › 여성의류 · 일간 · 최근 1개월"},
    {"slug": "fashion_accessories", "title": "네이버 패션잡화", "meta": "패션잡화 · 일간 · 최근 1개월"},
]
NAVER_SOURCE_URL = "https://datalab.naver.com/shoppingInsight/sCategory.naver"


def load_category_dates(slug: str) -> list[date]:
    cat_dir = NAVER_DIR / slug
    if not cat_dir.exists():
        return []
    dates = []
    for f in cat_dir.glob("*.csv"):
        try:
            dates.append(date.fromisoformat(f.stem))
        except ValueError:
            continue
    return sorted(dates, reverse=True)


def render_rank_card(title: str, meta: str, df: pd.DataFrame | None, source_url: str | None = None, empty_msg: str = "데이터 없음"):
    import html as html_lib

    link_html = f'<a href="{source_url}" target="_blank">원본 →</a>' if source_url else ""

    if df is None or df.empty:
        st.markdown(
            f"""<div class="rank-card">
                <div class="rank-card-head">
                    <div class="rank-card-title">{html_lib.escape(title)}</div>
                </div>
                <div class="rank-card-meta"><span>{html_lib.escape(meta)}</span>{link_html}</div>
                <div style="padding:24px 0; color:#BDBDC2; font-size:13px;">{html_lib.escape(empty_msg)}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        return

    items_html = ""
    for _, row in df.sort_values("rank").iterrows():
        top_class = " top" if row["rank"] <= 3 else ""
        items_html += (
            f'<div class="rank-item{top_class}"><div class="num">{row["rank"]}</div>'
            f'<div class="kw">{html_lib.escape(str(row["keyword"]))}</div></div>'
        )

    st.markdown(
        f"""<div class="rank-card">
            <div class="rank-card-head">
                <div class="rank-card-title">{html_lib.escape(title)}</div>
                <div class="rank-card-badge">{len(df)}개</div>
            </div>
            <div class="rank-card-meta"><span>{html_lib.escape(meta)}</span>{link_html}</div>
            <div class="rank-list">{items_html}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def load_app_search_dates() -> list[date]:
    if not APP_SEARCH_DIR.exists():
        return []
    dates = []
    for f in APP_SEARCH_DIR.glob("*.csv"):
        try:
            dates.append(date.fromisoformat(f.stem))
        except ValueError:
            continue
    return sorted(dates, reverse=True)


def run_scraper_script(script_path: Path, timeout: int) -> tuple[bool, str]:
    # 자식 프로세스의 stdout/stderr 인코딩을 UTF-8로 강제한다. Windows 콘솔 기본 코드페이지(cp949)로는
    # 스크래퍼가 출력하는 일부 문자(예: 화살표, 특수 기호, Playwright 에러 메시지 내 문자)를 인코딩하지
    # 못해 UnicodeEncodeError로 죽고, 그게 비정상 종료 코드로 이어져 실제로는 정상 수집됐거나 다른
    # 이유로 실패했는데도 원인을 알 수 없는 "수집 실패"로만 보이는 문제가 있었다.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", env=env,
    )
    ok = result.returncode == 0
    log = (result.stdout or "") + (result.stderr or "")
    return ok, log


def run_naver_scraper() -> tuple[bool, str]:
    return run_scraper_script(SCRAPER_SCRIPT, timeout=90)


def run_app_search_scraper() -> tuple[bool, str]:
    return run_scraper_script(APP_SEARCH_SCRAPER_SCRIPT, timeout=120)


def run_competitor_scraper() -> tuple[bool, str]:
    # 브랜드검색 PC/MO + 메타 소재까지 4개 브랜드 전부 도는 데 시간이 걸려서 넉넉히 잡는다.
    return run_scraper_script(COMPETITOR_SCRAPER_SCRIPT, timeout=240)


GITHUB_REPO = "performanceteam12-sketch/babathe-trend-dashboard"
REFRESH_SIGNAL_PATH = "data/refresh_signal.json"


def request_remote_refresh(target: str) -> tuple[bool, str]:
    # 배포된(클라우드) 화면에는 Playwright가 없어 직접 스크래핑이 불가능하다. 대신 GitHub API로
    # 신호 파일을 기록해두면, 로컬 PC의 scraper/remote_refresh_watcher.py가 5분마다 확인해
    # 그때 실제로 스크래핑한다 (scraper/remote_refresh_watcher.py 참고).
    import base64
    import json
    from urllib import request as urllib_request

    token = st.secrets.get("github_token")
    if not token:
        return False, "github_token이 설정되어 있지 않습니다 (Streamlit Cloud 앱 설정 > Secrets 확인 필요)."

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{REFRESH_SIGNAL_PATH}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    sha = None
    try:
        with urllib_request.urlopen(urllib_request.Request(api_url, headers=headers), timeout=10) as resp:
            sha = json.loads(resp.read()).get("sha")
    except Exception:
        pass  # 파일이 아직 없으면 최초 생성 (sha 없이 진행)

    requested_at = datetime.now().isoformat(timespec="seconds")
    payload = {"requested_at": requested_at, "target": target}
    content_b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode()
    body = {"message": f"새로고침 요청: {target} ({requested_at})", "content": content_b64}
    if sha:
        body["sha"] = sha

    try:
        put_req = urllib_request.Request(
            api_url, data=json.dumps(body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"}, method="PUT",
        )
        urllib_request.urlopen(put_req, timeout=10)
        return True, requested_at
    except Exception as e:  # noqa: BLE001 — 네트워크/권한 오류를 사용자에게 그대로 보여주기 위해 넓게 캐치
        return False, str(e)


def remote_refresh_button(label: str, target: str, key: str):
    if st.button(label, key=key):
        ok, info = request_remote_refresh(target)
        if ok:
            st.success("요청 완료! 로컬 PC가 5분 내로 확인해 새로고침합니다.")
        else:
            st.error(f"요청 실패: {info}")
    st.caption("실제 반영까지 최대 5분 정도 걸릴 수 있습니다 (로컬 PC가 5분마다 확인).")


def section_naver():
    st.markdown("#### 네이버 데이터랩")
    st.markdown(
        '<div class="section-desc">정확도: 순위만 제공 (검색량 수치는 네이버 데이터랩 API 미제공, 표시 안 함) · '
        "저빈도 원칙에 따라 새로고침 버튼을 눌렀을 때만 수집합니다.</div>",
        unsafe_allow_html=True,
    )

    if IS_LOCAL:
        col1, _ = st.columns([1, 3])
        with col1:
            if st.button("새로고침 (네이버 스크래핑 1회 실행)"):
                with st.spinner("네이버 데이터랩에서 카테고리별 TOP40 조회 중..."):
                    ok, log = run_naver_scraper()
                if ok:
                    st.success("수집 완료")
                else:
                    st.error("수집 실패 — 사이트 구조가 바뀌었거나 접근이 차단되었을 수 있습니다.")
                    st.code(log)
    else:
        remote_refresh_button("새로고침 요청 보내기 (네이버 데이터랩)", "naver", key="remote_refresh_naver")

    cat_cols = st.columns(len(NAVER_CATEGORIES))
    for cat, col in zip(NAVER_CATEGORIES, cat_cols):
        dates = load_category_dates(cat["slug"])
        with col:
            if not dates:
                render_rank_card(cat["title"], cat["meta"], None, source_url=NAVER_SOURCE_URL,
                                  empty_msg="오늘자 데이터 없음. 새로고침으로 수집하세요.")
                continue
            latest = dates[0]
            if latest != date.today():
                st.caption(f"⚠ 오늘 데이터 없음 · 최신: {latest.isoformat()} 기준")
            df_latest = pd.read_csv(NAVER_DIR / cat["slug"] / f"{latest.isoformat()}.csv", encoding="utf-8-sig")
            render_rank_card(cat["title"], cat["meta"], df_latest, source_url=NAVER_SOURCE_URL)

    all_dates = sorted({d for cat in NAVER_CATEGORIES for d in load_category_dates(cat["slug"])}, reverse=True)
    if len(all_dates) > 1:
        st.markdown("###### 최근 순위 추이")
        pick_cat = st.selectbox("카테고리 선택", NAVER_CATEGORIES, format_func=lambda c: c["title"], key="trend_cat")
        cat_dates = load_category_dates(pick_cat["slug"])[:30]
        if len(cat_dates) > 1:
            frames = []
            for d in cat_dates:
                df = pd.read_csv(NAVER_DIR / pick_cat["slug"] / f"{d.isoformat()}.csv", encoding="utf-8-sig")
                df["date"] = d.isoformat()
                frames.append(df)
            history = pd.concat(frames, ignore_index=True)
            keywords = sorted(history["keyword"].unique())
            picked = st.multiselect("추이를 볼 키워드 선택", keywords, default=keywords[:3] if keywords else [], key="trend_kw")
            if picked:
                pivot = history[history["keyword"].isin(picked)].pivot_table(
                    index="date", columns="keyword", values="rank"
                ).sort_index()
                st.line_chart(pivot)
                st.caption("Y축은 순위이므로 숫자가 낮을수록(위쪽일수록) 인기 상승입니다.")
        else:
            st.caption("이 카테고리는 아직 날짜별 이력이 1건뿐이라 추이를 볼 수 없습니다.")


def latest_channel_df(channel: str, dates: list[date]) -> tuple[pd.DataFrame | None, date | None, str | None, str | None]:
    for d in dates:
        day_df = pd.read_csv(APP_SEARCH_DIR / f"{d.isoformat()}.csv", encoding="utf-8-sig")
        sub = day_df[day_df["channel"] == channel]
        if not sub.empty:
            input_by = sub.iloc[0].get("input_by")
            # input_at은 초 단위까지 저장돼 있지만(scraper/app_search_scraper.py) 카드에는
            # 분 단위까지만 노출한다 — 초 단위는 회의 화면에서 의미 없는 노이즈.
            input_at_raw = sub.iloc[0].get("input_at", "")
            input_time = input_at_raw[11:16] if isinstance(input_at_raw, str) and len(input_at_raw) >= 16 else None
            return sub[["rank", "keyword"]], d, input_by, input_time
    return None, None, None, None


def section_app_search():
    st.markdown("#### 앱 실시간 검색어")
    st.markdown(
        '<div class="section-desc">각 사이트 검색창을 열면 나오는 인기/급상승 검색어를 자동 캡처합니다 '
        "(더한섬닷컴·W컨셉은 robots.txt가 일반 크롤러를 막고 있어 저빈도로만 실행). "
        "검색량 수치는 제공되지 않아 순위만 기록합니다.</div>",
        unsafe_allow_html=True,
    )

    if IS_LOCAL:
        col1, _ = st.columns([1, 3])
        with col1:
            if st.button("새로고침 (4개 브랜드 검색어 1회 캡처)"):
                with st.spinner("각 사이트 검색창을 열어 인기 검색어 확인 중..."):
                    ok, log = run_app_search_scraper()
                if ok:
                    st.success("수집 완료")
                else:
                    st.error("일부 브랜드 수집 실패 — 사이트 구조가 바뀌었을 수 있습니다.")
                    st.code(log)
    else:
        remote_refresh_button("새로고침 요청 보내기 (앱 실시간 검색어)", "app_search", key="remote_refresh_app_search")

    hist_dates = load_app_search_dates()
    cols = st.columns(len(APP_CHANNELS))
    for channel, col in zip(APP_CHANNELS, cols):
        df_latest, d, input_by, input_time = latest_channel_df(channel, hist_dates)
        source_label = "수동 입력" if input_by == "user" else "자동 캡처" if input_by == "auto" else "수동 입력"
        time_suffix = f" {input_time}" if input_time else ""
        meta = f"{source_label} · {d.isoformat()}{time_suffix}" if d else "아직 데이터 없음"
        with col:
            render_rank_card(channel, meta, df_latest, empty_msg="아직 데이터가 없습니다. 새로고침하거나 아래에서 직접 입력하세요.")

    st.write("")
    with st.expander("검색어 입력 / 수정"):
        sub_tabs = st.tabs(APP_CHANNELS)
        for channel, sub_tab in zip(APP_CHANNELS, sub_tabs):
            with sub_tab:
                with st.form(key=f"form_{channel}"):
                    input_date = st.date_input("조회 날짜", value=date.today(), key=f"date_{channel}")
                    raw = st.text_area(
                        "검색어를 줄바꿈으로 구분해 순위 순서대로 붙여넣으세요 (1위부터)",
                        key=f"text_{channel}", height=160,
                    )
                    submitted = st.form_submit_button("저장")
                if submitted:
                    keywords = [line.strip() for line in raw.splitlines() if line.strip()]
                    if not keywords:
                        st.error("입력된 검색어가 없습니다.")
                    else:
                        APP_SEARCH_DIR.mkdir(parents=True, exist_ok=True)
                        out_path = APP_SEARCH_DIR / f"{input_date.isoformat()}.csv"
                        existing = pd.read_csv(out_path, encoding="utf-8-sig") if out_path.exists() else pd.DataFrame(
                            columns=["channel", "rank", "keyword", "input_by", "input_at"]
                        )
                        existing = existing[existing["channel"] != channel]
                        new_rows = pd.DataFrame([
                            {
                                "channel": channel,
                                "rank": i + 1,
                                "keyword": kw,
                                "input_by": "user",
                                "input_at": datetime.now().isoformat(timespec="seconds"),
                            }
                            for i, kw in enumerate(keywords)
                        ])
                        pd.concat([existing, new_rows], ignore_index=True).to_csv(
                            out_path, index=False, encoding="utf-8-sig"
                        )
                        st.success(f"{channel} — {input_date.isoformat()} 데이터 저장 완료 ({len(keywords)}건)")
                        st.rerun()

                st.markdown("###### 입력 이력")
                if not hist_dates:
                    st.info("아직 입력된 데이터가 없습니다.")
                    continue
                pick_date = st.selectbox("날짜 선택", hist_dates, format_func=lambda d: d.isoformat(), key=f"hist_{channel}")
                df = pd.read_csv(APP_SEARCH_DIR / f"{pick_date.isoformat()}.csv", encoding="utf-8-sig")
                df = df[df["channel"] == channel]
                if df.empty:
                    st.info(f"{pick_date.isoformat()}에는 {channel} 데이터가 없습니다.")
                else:
                    st.dataframe(df[["rank", "keyword", "input_at"]], hide_index=True, use_container_width=True)


def page_keywords():
    naver_dates = sorted(
        {d for cat in NAVER_CATEGORIES for d in load_category_dates(cat["slug"])}, reverse=True
    )
    app_dates = load_app_search_dates()
    latest_date = max([d for d in [naver_dates[0] if naver_dates else None, app_dates[0] if app_dates else None] if d], default=None)
    page_header(
        "실시간 인기 검색어",
        "네이버 데이터랩 쇼핑인사이트와 4개 채널 앱 검색창의 인기 검색어를 모아봅니다.",
        badge_text=f"최신 기준일 {latest_date.isoformat()}" if latest_date else "미수집",
    )
    stat_row([
        ("네이버 데이터랩 최신 기준일", naver_dates[0].isoformat() if naver_dates else "미수집", "🛍️"),
        ("앱 검색어 입력 채널 수", f"{len(APP_CHANNELS)}개", "📱"),
        ("앱 검색어 최근 입력일", app_dates[0].isoformat() if app_dates else "미입력", "🕐"),
    ])
    section_naver()
    st.divider()
    section_app_search()


# ---------------------------------------------------------------------------
# 경쟁사 모니터링
# ---------------------------------------------------------------------------
def render_media_card(title: str, meta: str, image_path: Path | None, empty_msg: str = "미등록", aspect_ratio: str | None = None):
    # 이미지 위에 제목을 얹는 대신, 기존 경쟁사 동향 스프레드시트처럼 이미지 "아래"에 회색 캡션 바
    # (예: "WEB_이벤트 페이지")로 라벨을 붙인다 — 시트에서 대시보드로 넘어와도 낯설지 않도록.
    import base64
    import html as html_lib

    st.markdown('<div class="rank-card media-card">', unsafe_allow_html=True)
    if image_path and image_path.exists():
        if aspect_ratio:
            # 브랜드마다 소재 이미지의 원본 가로세로 비율이 달라(정사각형/세로형 등) 그냥 넣으면
            # 카드 높이가 브랜드마다 들쭉날쭉해진다. 고정 비율 박스 안에 원본 비율 그대로(잘리지 않게)
            # 담아서 레이아웃 크기는 통일하고 이미지만 그 안에 맞춘다 (사용자 요청, 2026-07-29).
            mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            b64 = base64.b64encode(image_path.read_bytes()).decode()
            st.markdown(
                f'<div style="aspect-ratio:{aspect_ratio}; background:#FAFAFA; border-radius:12px; '
                'overflow:hidden; display:flex; align-items:center; justify-content:center;">'
                f'<img src="data:{mime};base64,{b64}" style="max-width:100%; max-height:100%; '
                'object-fit:contain;" />'
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.image(str(image_path), use_container_width=True)
    else:
        st.markdown(f'<div class="media-empty">{html_lib.escape(empty_msg)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="media-caption"><span class="media-caption-title">{html_lib.escape(title)}</span>'
        f'<span class="media-caption-meta">{html_lib.escape(meta)}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def load_competitor() -> pd.DataFrame:
    if not COMPETITOR_CSV.exists():
        return pd.DataFrame(columns=["date", "brand", "slot", "image_file", "uploaded_at"])
    return pd.read_csv(COMPETITOR_CSV, encoding="utf-8-sig", keep_default_na=False)


def latest_competitor_date() -> date | None:
    # 배포된 화면은 세션마다 session_state가 비어 있어 기본값이 항상 date.today()로 떨어진다.
    # 로컬 스크래핑은 특정 요일(금/월)에만 도니 "오늘" 데이터가 없는 날이 대부분이라, 그대로 두면
    # 방문할 때마다 화면이 텅 비어 보인다 — 데이터가 있는 가장 최근 날짜를 기본값으로 쓴다.
    df = load_competitor()
    if df.empty:
        return None
    dates = sorted({date.fromisoformat(d) for d in df["date"].unique() if d}, reverse=True)
    return dates[0] if dates else None


def save_competitor_row(row: dict):
    COMPETITOR_DIR.mkdir(parents=True, exist_ok=True)
    df = load_competitor()
    df = df[~((df["date"] == row["date"]) & (df["brand"] == row["brand"]) & (df["slot"] == row["slot"]))]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(COMPETITOR_CSV, index=False, encoding="utf-8-sig")


def load_keywords_for(brand: str, view_date: date) -> list[str]:
    # scraper/competitor_monitor_scraper.py가 브랜드검색 박스 썸네일 캡션에서 자동 추출해 저장한다.
    if not COMPETITOR_KEYWORDS_CSV.exists():
        return []
    df = pd.read_csv(COMPETITOR_KEYWORDS_CSV, encoding="utf-8-sig", keep_default_na=False)
    match = df[(df["date"] == view_date.isoformat()) & (df["brand"] == brand)]
    if match.empty or not match.iloc[0]["keywords"]:
        return []
    return [k for k in match.iloc[0]["keywords"].split(",") if k]


def load_comment_for(brand: str, view_date: date) -> str:
    if not COMPETITOR_COMMENTS_CSV.exists():
        return ""
    df = pd.read_csv(COMPETITOR_COMMENTS_CSV, encoding="utf-8-sig", keep_default_na=False)
    match = df[(df["date"] == view_date.isoformat()) & (df["brand"] == brand)]
    return match.iloc[0]["comment"] if not match.empty else ""


def save_comment_for(brand: str, view_date: date, comment: str):
    # 코멘트(소재 해석)는 사람 판단이 필요한 영역이라 자동 생성하지 않고 마케터가 직접 작성해 저장한다.
    COMPETITOR_DIR.mkdir(parents=True, exist_ok=True)
    df = (
        pd.read_csv(COMPETITOR_COMMENTS_CSV, encoding="utf-8-sig", keep_default_na=False)
        if COMPETITOR_COMMENTS_CSV.exists()
        else pd.DataFrame(columns=["date", "brand", "comment", "updated_at"])
    )
    df = df[~((df["date"] == view_date.isoformat()) & (df["brand"] == brand))]
    df = pd.concat([df, pd.DataFrame([{
        "date": view_date.isoformat(),
        "brand": brand,
        "comment": comment,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }])], ignore_index=True)
    df.to_csv(COMPETITOR_COMMENTS_CSV, index=False, encoding="utf-8-sig")


COMPETITOR_ARCHIVE_CSV = COMPETITOR_DIR / "archive_weeks.csv"


def week_of_month(d: date) -> int:
    # scraper/weekly_archive.py의 계산과 반드시 같은 로직이어야 한다 ("그 달의 몇 번째 월요일인가").
    count = 0
    for day in range(1, d.day + 1):
        if d.replace(day=day).weekday() == 0:
            count += 1
    return max(count, 1)


def week_label(d: date) -> str:
    return f"{d.year % 100}년 {d.month}월 {week_of_month(d)}주차"


def load_archive_weeks() -> pd.DataFrame:
    if not COMPETITOR_ARCHIVE_CSV.exists():
        return pd.DataFrame(columns=["week_label", "date", "archived_at"])
    return pd.read_csv(COMPETITOR_ARCHIVE_CSV, encoding="utf-8-sig", keep_default_na=False)


def page_competitor():
    default_view_date = latest_competitor_date() or date.today()
    view_date_for_badge = st.session_state.get("competitor_view_date", default_view_date)
    page_header(
        "경쟁사 모니터링",
        "브랜드별 브랜드검색 PC/모바일 노출 화면과 메타 광고 소재 2종을 자동 캡처합니다 (수동 업로드도 가능).",
        badge_text=week_label(view_date_for_badge),
    )

    st.markdown(
        f'<div class="section-desc" style="margin-top:-6px;">경쟁사 리스트 · {" · ".join(COMPETITOR_BRANDS)}</div>',
        unsafe_allow_html=True,
    )

    if IS_LOCAL:
        col1, _ = st.columns([1, 3])
        with col1:
            if st.button("새로고침 (4개 브랜드 브랜드검색+메타소재 전체 재수집)"):
                with st.spinner("브랜드검색·메타 소재를 순서대로 캡처 중... (몇 분 걸릴 수 있습니다)"):
                    ok, log = run_competitor_scraper()
                if ok:
                    st.success("수집 완료")
                else:
                    st.error("일부 브랜드/슬롯 수집 실패 — 사이트 구조가 바뀌었을 수 있습니다.")
                    st.code(log)
    else:
        st.info(
            "이 데이터는 로컬 PC 예약 작업(매주 금요일 10시 아카이브 · 매주 월요일 9시 30분 업데이트)으로 "
            "자동 갱신됩니다. 배포된 화면에서는 새로고침이 지원되지 않습니다."
        )

    # 주차 선택은 사이드바의 "경쟁사 모니터링 > 주차별 아카이브"에서 한다 (main()에서 session_state로 주입).
    view_date = st.session_state.get("competitor_view_date", default_view_date)
    st.caption(f"현재 보고 있는 주차: {week_label(view_date)} (매주 금요일 오전 10시 자동 아카이브 · 매주 월요일 오전 9시 30분 자동 업데이트+슬랙 알림)")
    with st.expander("직접 날짜 선택"):
        manual_date = st.date_input("조회 날짜", value=view_date, key="competitor_manual_date")
        if manual_date != view_date:
            st.session_state["competitor_view_date"] = manual_date
            st.rerun()

    df = load_competitor()
    day_df = df[df["date"] == view_date.isoformat()] if not df.empty else df

    stat_row([
        ("모니터링 브랜드", f"{len(COMPETITOR_BRANDS)}개", "🏷️"),
        (f"{view_date.isoformat()} 등록된 이미지", f"{len(day_df)} / {len(COMPETITOR_BRANDS) * len(COMPETITOR_SLOTS)}", "🖼️"),
    ])

    import html as html_lib

    brand_slugs = {brand: f"brand-{i}" for i, brand in enumerate(COMPETITOR_BRANDS)}

    st.markdown('<div class="group-label">이번 주 요약 — 브랜드를 클릭하면 아래 상세로 이동합니다</div>', unsafe_allow_html=True)
    summary_cards = ""
    for brand in COMPETITOR_BRANDS:
        comment = load_comment_for(brand, view_date)
        comment_html = (
            f'<div class="summary-comment">{html_lib.escape(comment)}</div>' if comment
            else '<div class="summary-empty">코멘트 미작성</div>'
        )
        summary_cards += (
            f'<a class="summary-card" href="#{brand_slugs[brand]}">'
            f'<div class="summary-brand">{html_lib.escape(brand)}</div>{comment_html}</a>'
        )
    st.markdown(f'<div class="summary-grid">{summary_cards}</div>', unsafe_allow_html=True)

    for i, brand in enumerate(COMPETITOR_BRANDS):
        st.markdown(
            f'<div class="brand-block" id="{brand_slugs[brand]}">'
            f'<div class="brand-header"><div class="brand-title">{i + 1}. {html_lib.escape(brand)}</div></div>',
            unsafe_allow_html=True,
        )
        brand_df = day_df[day_df["brand"] == brand] if not day_df.empty else day_df

        keywords = load_keywords_for(brand, view_date)
        st.markdown('<div class="group-label">주요 키워드</div>', unsafe_allow_html=True)
        if keywords:
            pills = "".join(f'<span class="keyword-pill">#{html_lib.escape(k)}</span>' for k in keywords)
            st.markdown(f"<div>{pills}</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="keyword-empty">아직 추출된 키워드가 없습니다 (새로고침 시 브랜드검색 소재에서 자동 추출됩니다).</div>',
                unsafe_allow_html=True,
            )

        current_comment = load_comment_for(brand, view_date)
        if current_comment:
            st.markdown(
                f'<div class="comment-box"><span class="comment-label">코멘트</span>{html_lib.escape(current_comment)}</div>',
                unsafe_allow_html=True,
            )
        with st.expander("코멘트 작성/수정", expanded=not bool(current_comment)):
            with st.form(key=f"comment_form_{brand}_{view_date}"):
                comment_input = st.text_area(
                    "이 브랜드의 이번 소재/기획전에 대한 해석·전략 메모 (예: 주요 기획전 컨셉, 톤앤매너 등)",
                    value=current_comment, height=90, key=f"comment_text_{brand}_{view_date}",
                )
                comment_submitted = st.form_submit_button("코멘트 저장")
            if comment_submitted:
                save_comment_for(brand, view_date, comment_input.strip())
                st.success("저장 완료")
                st.rerun()

        def slot_lookup(slot: str) -> tuple[Path | None, str]:
            match = brand_df[brand_df["slot"] == slot] if not brand_df.empty else brand_df
            if not match.empty:
                row = match.iloc[0]
                p = COMPETITOR_IMG_DIR / row["image_file"]
                if p.exists():
                    return p, f"{view_date.isoformat()} 등록"
            return None, "미등록"

        st.markdown(f'<div class="group-label">{i + 1}-1. 브랜드검색</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for slot, col in zip(["브랜드검색 PC", "브랜드검색 MO"], cols):
            with col:
                image_path, meta = slot_lookup(slot)
                render_media_card(slot, meta, image_path)

        st.markdown(f'<div class="group-label" style="margin-top:16px;">{i + 1}-2. 메타 광고 소재</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for slot, col in zip(["메타소재 1", "메타소재 2"], cols):
            with col:
                image_path, meta = slot_lookup(slot)
                render_media_card(slot, meta, image_path, aspect_ratio="4/5")

        with st.expander(f"{brand} 이미지 업로드/교체 — {view_date.isoformat()}"):
            for slot in COMPETITOR_SLOTS:
                file = st.file_uploader(slot, type=["png", "jpg", "jpeg", "webp"], key=f"{brand}_{slot}_{view_date}")
                if file is not None:
                    COMPETITOR_IMG_DIR.mkdir(parents=True, exist_ok=True)
                    ext = Path(file.name).suffix or ".png"
                    image_file = f"{uuid.uuid4().hex}{ext}"
                    (COMPETITOR_IMG_DIR / image_file).write_bytes(file.getvalue())
                    save_competitor_row({
                        "date": view_date.isoformat(),
                        "brand": brand,
                        "slot": slot,
                        "image_file": image_file,
                        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                    })
                    st.success(f"{brand} · {slot} 저장 완료")
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    inject_style()
    with st.sidebar:
        st.markdown(
            """
            <div class="brand-mark">
                <div class="logo">B</div>
                <div>
                    <div class="name">바바더닷컴</div>
                    <div class="sub">패션 트렌드 대시보드</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        page = st.radio("nav", NAV_ITEMS, label_visibility="collapsed")

        if page == "경쟁사 모니터링":
            if "archive_expanded" not in st.session_state:
                st.session_state["archive_expanded"] = False
            chevron = "▾" if st.session_state["archive_expanded"] else "▸"
            if st.button(f"{chevron}  주차별 아카이브", key="archive_toggle", use_container_width=True):
                st.session_state["archive_expanded"] = not st.session_state["archive_expanded"]
                st.rerun()

            if st.session_state["archive_expanded"]:
                archive_df = load_archive_weeks()
                if not archive_df.empty:
                    archive_df = archive_df.sort_values("date", ascending=False)
                if archive_df.empty:
                    st.caption("　아직 기록된 주차가 없습니다.")
                else:
                    current_date = st.session_state.get(
                        "competitor_view_date", latest_competitor_date() or date.today()
                    ).isoformat()
                    for _, row in archive_df.iterrows():
                        is_current = row["date"] == current_date
                        mark = "●" if is_current else "‧"
                        if st.button(
                            f"　{mark} {row['week_label']}",
                            key=f"archive_btn_{row['week_label']}",
                            use_container_width=True,
                        ):
                            st.session_state["competitor_view_date"] = date.fromisoformat(row["date"])
                            st.rerun()

    if page == "실시간 인기 검색어":
        page_keywords()
    else:
        page_competitor()


if __name__ == "__main__":
    main()
