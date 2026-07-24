# 바바더닷컴 패션 트렌드 대시보드 프로젝트

## 프로젝트 개요
매주 소재(광고 크리에이티브) 기획 시 필요한 패션 트렌드(인기 검색어, 경쟁사 동향)를 한 눈에 확인하기 위한 대시보드. `dashboard/app.py` (Streamlit).
사이드바 2개 인덱스 구조: 이번 주 인기 검색어 / 경쟁사 모니터링.
("광고 소재 레퍼런스" 섹션은 2026-07-24에 사용자가 안 쓸 것 같다고 해서 삭제함 — 관련 코드/데이터 폴더 전부 제거됨.)

## 데이터 계약 (Data Contract)
- `data/naver_top10/{slug}/{YYYY-MM-DD}.csv`: `rank, keyword, category, collected_at` (slug: `fashion_women` = 패션의류>여성의류, `fashion_accessories` = 패션잡화 전체)
  - 출처: 네이버 데이터랩 쇼핑인사이트(일간, 최근1개월) 웹 화면 스크래핑, 카테고리별 TOP40
  - **정확도: 추정** — 사이트 구조가 바뀌면 스크래핑이 깨질 수 있음. 실패 시 조용히 넘어가지 말고 사용자에게 실패를 명확히 보고할 것.
  - 저빈도 원칙: 자동 폴링/스케줄러로 반복 호출하지 않는다. 사용자가 대시보드에서 "새로고침" 버튼을 눌렀을 때만 1회 실행.
  - 검색량(쿼리수) 수치는 API가 제공하지 않아 순위만 저장·표시한다. 임의로 추정치를 만들어 넣지 않는다.
  - 카테고리를 추가할 때는 `scraper/naver_datalab_scraper.py`의 `CATEGORIES` 리스트와 `dashboard/app.py`의 `NAVER_CATEGORIES`를 함께 갱신해야 한다 (양쪽 slug가 일치해야 함).
- `data/app_search/{YYYY-MM-DD}.csv`: `channel(더한섬닷컴/신세계V/W컨셉/바바더닷컴), rank, keyword, input_by(auto/user), input_at`
  - 출처: `scraper/app_search_scraper.py` 자동 캡처 (각 사이트 PC 웹 검색창을 클릭하면 뜨는 인기/급상승 검색어 오버레이) 또는 대시보드 수동 입력
  - **정정 (2026-07-24)**: 최초 조사 시 "앱 전용이라 자동 수집 불가"로 결론 냈으나 틀렸음 — 정적 페이지 로드만 확인하고 검색창을 클릭해보지 않아서 놓쳤다. 사용자가 실제 화면을 캡처해 보여줘서 검색창 클릭 시 나오는 오버레이임을 확인, 자동화로 전환함.
  - 브랜드별로 노출되는 리스트가 다름: 더한섬닷컴="급상승 검색어"(주의: "인기 검색어" 아님, 같은 화면에 둘 다 있으니 혼동 주의), 신세계V="급상승 검색어", W컨셉/바바더닷컴="인기 검색어"
  - **정확도: 자동 캡처는 화면 그대로, 셀렉터가 좌표 클릭 기반이라 사이트 리뉴얼 시 깨지기 쉬움**
  - **이용약관**: shinsegaev.com, babathe.com(자사)은 robots.txt가 일반 크롤러를 허용(`Allow: /`)해 문제 없음. thehandsome.com, display.wconcept.co.kr은 화이트리스트 방식으로 일반 크롤러를 차단하나, 사용자 승인 하에 저빈도(주 1회 목표)로 진행 중.
  - 채널 목록은 `dashboard/app.py`의 `APP_CHANNELS`와 `scraper/app_search_scraper.py`의 `CHANNELS`에서 관리 (양쪽 이름이 일치해야 함)
- `data/competitor_monitor/competitor_monitor.csv`: `date, brand, slot, image_file, uploaded_at` (+ 이미지 원본은 `data/competitor_monitor/images/`)
  - 대상 브랜드: 더한섬닷컴, 신세계V, W컨셉, 바바더닷컴 (고정 4개)
  - 슬롯: 브랜드검색 PC, 브랜드검색 MO, 메타소재 1, 메타소재 2 (브랜드당 4개)
  - 출처: `scraper/competitor_monitor_scraper.py` 자동 캡처 (search.naver.com 브랜드검색 영역 + Meta 광고 라이브러리) 또는 대시보드 수동 업로드
  - **정확도: 자동 캡처는 화면 스크린샷 그대로, 사이트 구조 변경 시 깨질 수 있음**. Meta 소재는 `ACCOUNT_MAP`(스크립트 상단)에 등록된 정확한 계정명으로 필터링 — 키워드 매칭이 아니므로 브랜드의 공식 계정명이 바뀌면 갱신 필요.
  - **이용약관 주의**: search.naver.com과 facebook.com(Meta 광고 라이브러리)은 robots.txt로 자동 수집을 명시적으로 금지한다. 사용자 승인 하에 저빈도(주 1회) 실행으로 진행 중 — 절대 하루에 여러 번 돌리거나 대량 브랜드로 확장하지 않는다.
  - CSV를 pandas로 읽을 때 `keep_default_na=False`를 유지할 것 (빈 문자열이 NaN으로 바뀌는 것 방지)

## 자동화 스케줄
- `BabaderCompetitorMonitor`: Windows 작업 스케줄러에 등록됨, 매주 목요일 17:00에 `competitor_monitor_scraper.py` 실행 (로컬 PC가 켜져 있고 로그인 상태여야 실행됨). 등록/변경은 `schtasks /change /tn "BabaderCompetitorMonitor" ...`로.
- 네이버 데이터랩 스크래퍼(`naver_datalab_scraper.py`)는 별도 스케줄 없이 대시보드 "새로고침" 버튼으로만 수동 실행 (저빈도·수동 트리거 원칙 유지).

## 작업 원칙
- 새로운 사이트를 자동 캡처/스크래핑 대상으로 추가하기 전에 반드시 공식 API 존재 여부 → robots.txt/이용약관 순으로 확인하고 사용자에게 결과를 보고한 뒤 진행 여부를 확인받는다.
  - **정적 페이지 로드만으로 "자동 수집 불가"라고 단정하지 말 것** — 검색창 클릭 등 사용자 상호작용으로만 렌더링되는 콘텐츠(예: 각 사이트 인기검색어 오버레이)가 있을 수 있다. 실제로 2026-07-24에 이걸 놓쳐서 사용자가 스크린샷으로 정정해준 사례가 있음.
  - 확인된 사이트별 robots.txt 상태: datalab.naver.com/search.naver.com/facebook.com/thehandsome.com/display.wconcept.co.kr → 일반 크롤러 차단(화이트리스트); shinsegaev.com/babathe.com(자사) → 일반 크롤러 허용. 차단된 사이트는 사용자 승인 하에 저빈도로만 진행 중.
- 스크래핑/캡처 실패(사이트 구조 변경, 접근 차단 등) 시 이전 날짜 데이터로 조용히 대체하지 말고 실패를 명확히 표시하거나 로그로 남긴다.
- 자동 캡처 빈도를 늘리거나(주 1회 → 매일 등) 새 브랜드를 추가할 때는 반드시 사용자에게 먼저 확인한다.
