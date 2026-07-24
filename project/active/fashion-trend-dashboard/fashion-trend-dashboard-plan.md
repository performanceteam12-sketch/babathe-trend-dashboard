# 바바더닷컴 패션 트렌드 대시보드 — 승인된 계획

## Context
바바더닷컴 마케터가 매주 소재 기획(레퍼런스 서치, 키워드 쿼리량, 레이아웃/문안 트렌드 확인)에 드는 시간을 줄이기 위해, 패션 트렌드를 한 눈에 보는 Streamlit 대시보드를 만든다.

조사 결과 4개 요청 항목 중 자동 수집이 가능한 것은 제한적이었다:
- **네이버 데이터랩 쇼핑인사이트 TOP10**: 공식 API는 "지정 키워드의 클릭 추이"만 제공하고 TOP10 순위 자체는 API에 없음 → 웹 화면 저빈도(1일 1회) 스크래핑으로 진행 (사용자 승인됨)
- **더한섬닷컴 / SSG(신세계몰) / W컨셉 앱 실시간 검색어**: 3곳 모두 API 없음, robots.txt가 일반 크롤러 차단, 모바일웹 미노출 → 자동 수집 불가 확정. **반자동 입력 폼**으로 사용자가 앱을 보고 매일 직접 입력 (사용자 승인됨)
- **기술 스택**: 기존 성과 대시보드와 동일하게 Streamlit (사용자 승인됨)

## 디렉토리 구조
```
바바더닷컴 트렌드 대시보드/
├── CLAUDE.md
├── requirements.txt
├── project/active/fashion-trend-dashboard/
│   ├── fashion-trend-dashboard-plan.md
│   ├── fashion-trend-dashboard-context.md
│   └── fashion-trend-dashboard-tasks.md
├── data/
│   ├── naver_top10/                   # {YYYY-MM-DD}.csv
│   └── app_search/                    # {YYYY-MM-DD}.csv
├── scraper/
│   └── naver_datalab_scraper.py
└── dashboard/
    └── app.py
```

## 데이터 계약
- `data/naver_top10/{date}.csv`: `rank, keyword, category, collected_at` — 출처: 스크래핑 (정확도: 추정)
- `data/app_search/{date}.csv`: `channel, rank, keyword, input_by, input_at` — 출처: 수동 입력 (정확도: 사용자 입력값 그대로)
- 스크래핑 실패 시 "오늘자 데이터 없음"을 명확히 표시, 이전 날짜로 조용히 대체하지 않음

## Streamlit 대시보드 구성
1. 네이버 데이터랩 TOP10 탭 — 최신 테이블, 새로고침 버튼(스크래퍼 실행), 순위 추이 라인차트
2. 앱 실시간 검색어 탭 — 더한섬/SSG/W컨셉 서브탭, 수동 입력 폼 + 이력 테이블
3. 소재 기획 참고 확장 섹션 — 외부 레퍼런스 링크 카드, 향후 확장 후보 기록 (무신사/29CM, 자사 성과 연동 등은 이번 범위 밖)

## 구현 단계
1. 프로젝트 문서 생성
2. CLAUDE.md 작성
3. 스크래퍼 작성
4. 대시보드 작성
5. requirements.txt 작성
6. 로컬 실행 및 검증 (스크린샷 증명)

## 검증
- `streamlit run dashboard/app.py` 로컬 실행, 3개 탭 스크린샷 확인
- 네이버 스크래핑 새로고침 버튼 실제 클릭 테스트
- 앱 검색어 수동 입력 폼 저장/이력 반영 테스트
