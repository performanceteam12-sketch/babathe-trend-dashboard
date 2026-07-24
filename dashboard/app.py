"""바바더닷컴 패션 트렌드 대시보드. 새 날짜 데이터가 추가되면 새로고침 버튼으로 다시 스캔한다."""

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
AD_REF_DIR = ROOT / "data" / "ad_reference"
AD_REF_IMG_DIR = AD_REF_DIR / "images"
AD_REF_CSV = AD_REF_DIR / "ad_reference.csv"
COMPETITOR_DIR = ROOT / "data" / "competitor_monitor"
COMPETITOR_IMG_DIR = COMPETITOR_DIR / "images"
COMPETITOR_CSV = COMPETITOR_DIR / "competitor_monitor.csv"
SCRAPER_SCRIPT = ROOT / "scraper" / "naver_datalab_scraper.py"
APP_SEARCH_SCRAPER_SCRIPT = ROOT / "scraper" / "app_search_scraper.py"

APP_CHANNELS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]
COMPETITOR_BRANDS = ["더한섬닷컴", "신세계V", "W컨셉", "바바더닷컴"]
COMPETITOR_SLOTS = ["브랜드검색 PC", "브랜드검색 MO", "메타소재 1", "메타소재 2"]
NAV_ITEMS = ["이번 주 인기 검색어", "광고 소재 레퍼런스", "경쟁사 모니터링"]

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

        .block-container { padding: 2.5rem 3rem 3rem; max-width: 1240px; }

        h1, h2, h3, h4 { letter-spacing: -0.01em; color: #18181B; }

        /* 사이드바 */
        section[data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: 1px solid #E4E4E7;
        }
        section[data-testid="stSidebar"] .block-container { padding: 1.75rem 1rem; }

        .brand-mark {
            display: flex; align-items: center; gap: 10px;
            padding: 0 0.5rem 1.25rem; margin-bottom: 0.5rem;
            border-bottom: 1px solid #F0F0F1;
        }
        .brand-mark .logo {
            width: 32px; height: 32px; border-radius: 9px;
            background: #2563EB; color: white; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
            font-size: 15px; flex-shrink: 0;
        }
        .brand-mark .name { font-weight: 700; font-size: 15px; color: #18181B; }
        .brand-mark .sub { font-size: 11px; color: #9CA3AF; margin-top: 1px; }

        /* 네비게이션 라디오 -> 리스트 형태로 재구성 */
        section[data-testid="stSidebar"] div[role="radiogroup"] {
            display: flex; flex-direction: column; gap: 2px; padding: 0 0.5rem;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            padding: 10px 12px; border-radius: 10px; color: #52525B;
            font-weight: 500; font-size: 14px; transition: background .12s ease;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: #F4F4F5; }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
            background: #EFF4FF; color: #2563EB; font-weight: 600;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none; }

        /* 공통 카드 */
        .stat-row { display: flex; gap: 14px; margin: 0.25rem 0 1.75rem; flex-wrap: wrap; }
        .stat-card {
            flex: 1; min-width: 160px; background: #FFFFFF; border: 1px solid #E4E4E7;
            border-radius: 16px; padding: 18px 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }
        .stat-card .label { font-size: 12.5px; color: #9CA3AF; font-weight: 500; }
        .stat-card .value { font-size: 26px; font-weight: 700; color: #18181B; margin-top: 4px; letter-spacing: -0.02em; }

        .section-desc { color: #71717A; font-size: 14px; margin-bottom: 1.25rem; }

        .tag-pill {
            display: inline-block; background: #F4F4F5; color: #52525B;
            font-size: 11.5px; font-weight: 500; padding: 3px 9px; border-radius: 999px;
            margin: 0 4px 4px 0;
        }

        .ref-card {
            background: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 14px;
            padding: 14px; margin-bottom: 14px;
        }
        .ref-card .title { font-weight: 600; font-size: 14px; color: #18181B; margin: 8px 0 4px; }
        .ref-card .meta { font-size: 11.5px; color: #A1A1AA; }

        .brand-block {
            border: 1px solid #E4E4E7; border-radius: 16px; padding: 18px 20px 8px;
            margin-bottom: 18px; background: #FFFFFF;
        }
        .brand-block .brand-title { font-weight: 700; font-size: 15px; color: #18181B; margin-bottom: 12px; }
        .slot-label { font-size: 12px; color: #9CA3AF; margin-top: 6px; text-align: center; }
        .slot-empty {
            aspect-ratio: 3/4; background: #FAFAFA; border: 1px dashed #D4D4D8; border-radius: 10px;
            display: flex; align-items: center; justify-content: center; color: #BDBDC2; font-size: 12px;
        }

        /* 랭킹 카드 (이번 주 인기 검색어) */
        .rank-card {
            background: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 20px;
            padding: 20px 22px 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }
        .rank-card-head { display: flex; justify-content: space-between; align-items: flex-start; }
        .rank-card-title { font-weight: 700; font-size: 16px; color: #18181B; }
        .rank-card-badge {
            background: #EFF4FF; color: #2563EB; font-size: 12px; font-weight: 700;
            padding: 3px 11px; border-radius: 999px; flex-shrink: 0;
        }
        .rank-card-meta {
            display: flex; justify-content: space-between; align-items: baseline;
            font-size: 12px; color: #9CA3AF; margin: 3px 0 12px;
        }
        .rank-card-meta a { color: #9CA3AF; text-decoration: none; }
        .rank-card-meta a:hover { color: #2563EB; }
        .rank-list { max-height: 460px; overflow-y: auto; }
        .rank-item {
            display: flex; align-items: center; gap: 12px; padding: 8.5px 2px;
            border-bottom: 1px solid #F4F4F5; font-size: 14px;
        }
        .rank-item:last-child { border-bottom: none; }
        .rank-item .num { width: 18px; text-align: center; font-weight: 700; color: #A1A1AA; font-size: 13px; }
        .rank-item.top .num { color: #2563EB; }
        .rank-item .kw { color: #27272A; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def stat_row(items: list[tuple[str, str]]):
    html = '<div class="stat-row">' + "".join(
        f'<div class="stat-card"><div class="label">{label}</div><div class="value">{value}</div></div>'
        for label, value in items
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 이번 주 인기 검색어
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


def run_naver_scraper() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(SCRAPER_SCRIPT)],
        capture_output=True, text=True, timeout=90,
    )
    ok = result.returncode == 0
    log = (result.stdout or "") + (result.stderr or "")
    return ok, log


def section_naver():
    st.markdown("#### 네이버 데이터랩")
    st.markdown(
        '<div class="section-desc">정확도: 순위만 제공 (검색량 수치는 네이버 데이터랩 API 미제공, 표시 안 함) · '
        "저빈도 원칙에 따라 새로고침 버튼을 눌렀을 때만 수집합니다.</div>",
        unsafe_allow_html=True,
    )

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


def latest_channel_df(channel: str, dates: list[date]) -> tuple[pd.DataFrame | None, date | None]:
    for d in dates:
        day_df = pd.read_csv(APP_SEARCH_DIR / f"{d.isoformat()}.csv", encoding="utf-8-sig")
        sub = day_df[day_df["channel"] == channel]
        if not sub.empty:
            return sub[["rank", "keyword"]], d
    return None, None


def section_app_search():
    st.markdown("#### 앱 실시간 검색어")
    st.markdown(
        '<div class="section-desc">공식 API·자동 수집이 불가능해(robots.txt 차단, 앱 전용) 사용자가 앱을 직접 보고 입력합니다. '
        "검색량 수치는 제공되지 않아 순위만 기록합니다.</div>",
        unsafe_allow_html=True,
    )

    hist_dates = load_app_search_dates()
    cols = st.columns(len(APP_CHANNELS))
    for channel, col in zip(APP_CHANNELS, cols):
        df_latest, d = latest_channel_df(channel, hist_dates)
        meta = f"실시간 검색어 · {d.isoformat()} 입력" if d else "실시간 검색어 (수동 입력)"
        with col:
            render_rank_card(channel, meta, df_latest, empty_msg="아직 입력된 데이터가 없습니다. 아래에서 입력하세요.")

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
    st.markdown("### 이번 주 인기 검색어")
    naver_dates = sorted(
        {d for cat in NAVER_CATEGORIES for d in load_category_dates(cat["slug"])}, reverse=True
    )
    app_dates = load_app_search_dates()
    stat_row([
        ("네이버 데이터랩 최신 기준일", naver_dates[0].isoformat() if naver_dates else "미수집"),
        ("앱 검색어 입력 채널 수", f"{len(APP_CHANNELS)}개"),
        ("앱 검색어 최근 입력일", app_dates[0].isoformat() if app_dates else "미입력"),
    ])
    section_naver()
    st.divider()
    section_app_search()


# ---------------------------------------------------------------------------
# 광고 소재 레퍼런스
# ---------------------------------------------------------------------------
def load_ad_reference() -> pd.DataFrame:
    if not AD_REF_CSV.exists():
        return pd.DataFrame(columns=["id", "title", "tags", "image_file", "link", "uploaded_at"])
    return pd.read_csv(AD_REF_CSV, encoding="utf-8-sig", keep_default_na=False)


def save_ad_reference_row(row: dict):
    AD_REF_DIR.mkdir(parents=True, exist_ok=True)
    df = load_ad_reference()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(AD_REF_CSV, index=False, encoding="utf-8-sig")


def page_ad_reference():
    st.markdown("### 광고 소재 레퍼런스")
    df = load_ad_reference()
    all_tags = sorted({t for tags in df["tags"].dropna() for t in tags.split(",") if t})
    stat_row([
        ("등록된 레퍼런스", f"{len(df)}건"),
        ("태그 종류", f"{len(all_tags)}개"),
    ])

    with st.expander("+ 새 레퍼런스 등록", expanded=len(df) == 0):
        with st.form("ad_reference_form", clear_on_submit=True):
            title = st.text_input("제목")
            tags = st.text_input("태그 (쉼표로 구분, 예: 시즌오프·프로모션·레이아웃)")
            link = st.text_input("참고 링크 (선택)")
            image = st.file_uploader("이미지 (선택)", type=["png", "jpg", "jpeg", "webp"])
            submitted = st.form_submit_button("등록")
        if submitted:
            if not title.strip():
                st.error("제목을 입력하세요.")
            else:
                image_file = ""
                if image is not None:
                    AD_REF_IMG_DIR.mkdir(parents=True, exist_ok=True)
                    ext = Path(image.name).suffix or ".png"
                    image_file = f"{uuid.uuid4().hex}{ext}"
                    (AD_REF_IMG_DIR / image_file).write_bytes(image.getvalue())
                save_ad_reference_row({
                    "id": uuid.uuid4().hex[:8],
                    "title": title.strip(),
                    "tags": tags.strip(),
                    "image_file": image_file,
                    "link": link.strip(),
                    "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                })
                st.success("등록 완료")
                st.rerun()

    df = load_ad_reference()
    if df.empty:
        st.info("아직 등록된 레퍼런스가 없습니다. 위에서 첫 레퍼런스를 등록하세요.")
    else:
        picked_tags = st.multiselect("태그 필터", all_tags)
        view = df
        if picked_tags:
            view = view[view["tags"].fillna("").apply(lambda t: any(tag in t.split(",") for tag in picked_tags))]

        cols = st.columns(3)
        for i, (_, row) in enumerate(view[::-1].iterrows()):
            with cols[i % 3]:
                st.markdown('<div class="ref-card">', unsafe_allow_html=True)
                if row.get("image_file") and (AD_REF_IMG_DIR / row["image_file"]).exists():
                    st.image(str(AD_REF_IMG_DIR / row["image_file"]), use_container_width=True)
                st.markdown(f'<div class="title">{row["title"]}</div>', unsafe_allow_html=True)
                if row.get("tags"):
                    st.markdown(
                        "".join(f'<span class="tag-pill">{t}</span>' for t in str(row["tags"]).split(",") if t),
                        unsafe_allow_html=True,
                    )
                if row.get("link"):
                    st.markdown(f'<a href="{row["link"]}" target="_blank">참고 링크 열기</a>', unsafe_allow_html=True)
                st.markdown(f'<div class="meta">{row["uploaded_at"]}</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("외부 레퍼런스 링크 (참고용, 자동 수집 아님)"):
        st.markdown("""
- [WGSN](https://www.wgsn.com/) — 글로벌 컬러/스타일 트렌드
- [Pantone Color of the Year](https://www.pantone.com/color-of-the-year) — 시즌 컬러 트렌드
- [무신사 랭킹](https://www.musinsa.com/ranking) — 국내 패션 판매 랭킹
- [29CM](https://www.29cm.co.kr/) — 큐레이션 트렌드 상품
""")


# ---------------------------------------------------------------------------
# 경쟁사 모니터링
# ---------------------------------------------------------------------------
def load_competitor() -> pd.DataFrame:
    if not COMPETITOR_CSV.exists():
        return pd.DataFrame(columns=["date", "brand", "slot", "image_file", "uploaded_at"])
    return pd.read_csv(COMPETITOR_CSV, encoding="utf-8-sig", keep_default_na=False)


def save_competitor_row(row: dict):
    COMPETITOR_DIR.mkdir(parents=True, exist_ok=True)
    df = load_competitor()
    df = df[~((df["date"] == row["date"]) & (df["brand"] == row["brand"]) & (df["slot"] == row["slot"]))]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(COMPETITOR_CSV, index=False, encoding="utf-8-sig")


def page_competitor():
    st.markdown("### 경쟁사 모니터링")
    st.markdown(
        '<div class="section-desc">브랜드별 브랜드검색 PC/모바일 노출 화면과 메타 광고관리자 운영 소재 2종을 '
        "직접 캡처해 업로드합니다 (경쟁사 API·크롤링 불가로 반자동 방식).</div>",
        unsafe_allow_html=True,
    )

    df = load_competitor()
    view_date = st.date_input("조회 날짜", value=date.today(), key="competitor_view_date")
    day_df = df[df["date"] == view_date.isoformat()] if not df.empty else df

    stat_row([
        ("모니터링 브랜드", f"{len(COMPETITOR_BRANDS)}개"),
        (f"{view_date.isoformat()} 등록된 이미지", f"{len(day_df)} / {len(COMPETITOR_BRANDS) * len(COMPETITOR_SLOTS)}"),
    ])

    for brand in COMPETITOR_BRANDS:
        st.markdown(f'<div class="brand-block"><div class="brand-title">{brand}</div>', unsafe_allow_html=True)
        cols = st.columns(len(COMPETITOR_SLOTS))
        brand_df = day_df[day_df["brand"] == brand] if not day_df.empty else day_df
        for slot, col in zip(COMPETITOR_SLOTS, cols):
            with col:
                match = brand_df[brand_df["slot"] == slot] if not brand_df.empty else brand_df
                if not match.empty and (COMPETITOR_IMG_DIR / match.iloc[0]["image_file"]).exists():
                    st.image(str(COMPETITOR_IMG_DIR / match.iloc[0]["image_file"]), use_container_width=True)
                else:
                    st.markdown('<div class="slot-empty">미등록</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="slot-label">{slot}</div>', unsafe_allow_html=True)

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

    if page == "이번 주 인기 검색어":
        page_keywords()
    elif page == "광고 소재 레퍼런스":
        page_ad_reference()
    else:
        page_competitor()


if __name__ == "__main__":
    main()
