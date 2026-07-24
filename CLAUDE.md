# 바바더닷컴 패션 트렌드 대시보드 프로젝트

## 프로젝트 개요
매주 소재(광고 크리에이티브) 기획 시 필요한 패션 트렌드(인기 검색어, 레퍼런스, 경쟁사 동향)를 한 눈에 확인하기 위한 대시보드. `dashboard/app.py` (Streamlit).
사이드바 3개 인덱스 구조: 이번 주 인기 검색어 / 광고 소재 레퍼런스 / 경쟁사 모니터링.

## 데이터 계약 (Data Contract)
- `data/naver_top10/{slug}/{YYYY-MM-DD}.csv`: `rank, keyword, category, collected_at` (slug: `fashion_women` = 패션의류>여성의류, `fashion_accessories` = 패션잡화 전체)
  - 출처: 네이버 데이터랩 쇼핑인사이트(일간, 최근1개월) 웹 화면 스크래핑, 카테고리별 TOP40
  - **정확도: 추정** — 사이트 구조가 바뀌면 스크래핑이 깨질 수 있음. 실패 시 조용히 넘어가지 말고 사용자에게 실패를 명확히 보고할 것.
  - 저빈도 원칙: 자동 폴링/스케줄러로 반복 호출하지 않는다. 사용자가 대시보드에서 "새로고침" 버튼을 눌렀을 때만 1회 실행.
  - 검색량(쿼리수) 수치는 API가 제공하지 않아 순위만 저장·표시한다. 임의로 추정치를 만들어 넣지 않는다.
  - 카테고리를 추가할 때는 `scraper/naver_datalab_scraper.py`의 `CATEGORIES` 리스트와 `dashboard/app.py`의 `NAVER_CATEGORIES`를 함께 갱신해야 한다 (양쪽 slug가 일치해야 함).
- `data/app_search/{YYYY-MM-DD}.csv`: `channel(더한섬닷컴/신세계V/W컨셉/바바더닷컴), rank, keyword, input_by, input_at`
  - 출처: 사용자가 각 앱을 직접 보고 대시보드 폼에 수동 입력 (자동 수집 불가 확인됨: API 없음, robots.txt 차단, 모바일웹 미노출)
  - **정확도: 사용자 입력값 그대로**, 별도 검증 로직 없음
  - 채널 목록은 `dashboard/app.py`의 `APP_CHANNELS`에서 관리 (2026-07-24부로 `SSG(신세계몰)` → `신세계V`로 변경, `바바더닷컴` 추가해 경쟁사 모니터링과 동일한 4개 브랜드로 통일)
- `data/ad_reference/ad_reference.csv`: `id, title, tags, image_file, link, uploaded_at` (+ 이미지 원본은 `data/ad_reference/images/`)
  - 출처: 마케터가 직접 큐레이션해 업로드하는 광고 소재 레퍼런스 갤러리 (수동 큐레이션, 자동 수집 아님)
  - CSV를 pandas로 읽을 때 빈 문자열이 NaN으로 바뀌는 문제를 피하려면 `keep_default_na=False`를 유지할 것 (링크/태그 빈 값 처리에 영향)
- `data/competitor_monitor/competitor_monitor.csv`: `date, brand, slot, image_file, uploaded_at` (+ 이미지 원본은 `data/competitor_monitor/images/`)
  - 대상 브랜드: 더한섬닷컴, 신세계V, W컨셉, 바바더닷컴 (고정 4개)
  - 슬롯: 브랜드검색 PC, 브랜드검색 MO, 메타소재 1, 메타소재 2 (브랜드당 4개)
  - 출처: `scraper/competitor_monitor_scraper.py` 자동 캡처 (search.naver.com 브랜드검색 영역 + Meta 광고 라이브러리) 또는 대시보드 수동 업로드
  - **정확도: 자동 캡처는 화면 스크린샷 그대로, 사이트 구조 변경 시 깨질 수 있음**. Meta 소재는 `ACCOUNT_MAP`(스크립트 상단)에 등록된 정확한 계정명으로 필터링 — 키워드 매칭이 아니므로 브랜드의 공식 계정명이 바뀌면 갱신 필요.
  - **이용약관 주의**: search.naver.com과 facebook.com(Meta 광고 라이브러리)은 robots.txt로 자동 수집을 명시적으로 금지한다. 사용자 승인 하에 저빈도(주 1회) 실행으로 진행 중 — 절대 하루에 여러 번 돌리거나 대량 브랜드로 확장하지 않는다.

## 자동화 스케줄
- `BabaderCompetitorMonitor`: Windows 작업 스케줄러에 등록됨, 매주 목요일 17:00에 `competitor_monitor_scraper.py` 실행 (로컬 PC가 켜져 있고 로그인 상태여야 실행됨). 등록/변경은 `schtasks /change /tn "BabaderCompetitorMonitor" ...`로.
- 네이버 데이터랩 스크래퍼(`naver_datalab_scraper.py`)는 별도 스케줄 없이 대시보드 "새로고침" 버튼으로만 수동 실행 (저빈도·수동 트리거 원칙 유지).

## 작업 원칙
- 새로운 사이트를 자동 캡처/스크래핑 대상으로 추가하기 전에 반드시 공식 API 존재 여부 → robots.txt/이용약관 순으로 확인하고 사용자에게 결과를 보고한 뒤 진행 여부를 확인받는다 (이미 확인된 사이트: datalab.naver.com, search.naver.com, facebook.com 모두 자동 수집 명시적 금지 — 사용자 승인 하에 저빈도로만 진행 중인 상태).
- 더한섬닷컴/SSG/W컨셉 자체 웹·앱은 robots.txt가 크롤링을 막고 있으므로 절대 브라우저 자동화로 우회 수집을 시도하지 않는다 (이건 여전히 수동 입력 유지).
- 스크래핑/캡처 실패(사이트 구조 변경, 접근 차단 등) 시 이전 날짜 데이터로 조용히 대체하지 말고 실패를 명확히 표시하거나 로그로 남긴다.
- 자동 캡처 빈도를 늘리거나(주 1회 → 매일 등) 새 브랜드를 추가할 때는 반드시 사용자에게 먼저 확인한다.
