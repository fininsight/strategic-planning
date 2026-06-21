# FI Strategic Planning

나라장터 공고를 수집, 필터링, 분석하고 프론트엔드 대시보드에서 확인하기 위한 Python + TypeScript 통합 프로젝트입니다.

- 대시보드: 공고 목록, 필터링, 정렬, 페이지네이션
- 모니터링: 공고 첨부파일 다운로드, PDF/HWP 뷰어, AI 요약
- 분석: 공고 원문 기반 제출서류 체크리스트, 공고정보, 배점표 분석

## 폴더 구조

```text
.
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── api/        # HTTP API 엔드포인트
│       └── services/
│           ├── scanner/      # 나라장터 공고 수집, 필터링, 스코어링, 엑셀/JSON 생성
│           └── analyzer/     # 첨부파일 다운로드, PDF 변환, 텍스트 추출, AI/룰 기반 분석
├── frontend/
│   ├── public/data/
│   │   ├── notices.json      # 대시보드 공고 목록
│   │   └── analyses/         # 공고별 분석 JSON 캐시
│   └── src/                  # React + TypeScript 화면 코드
├── scripts/
│   ├── download-g2b-attachments.mjs
│   └── start-analysis-server.sh
├── reports/                  # 로컬/Actions 엑셀 산출물, gitignore 대상
└── logs/                     # 로컬 실행 로그, gitignore 대상
```

## 실행

```bash
# 공고 스캔 및 엑셀/대시보드 JSON 생성
PYTHONPATH=backend python -m app.services.scanner

# 분석 API 서버
bash scripts/start-analysis-server.sh

# 프론트엔드
cd frontend
npm install
npm run dev
```

분석 API 서버는 기본적으로 `http://127.0.0.1:8787`에서 실행됩니다.

## 데이터 흐름

- GitHub Actions는 매주 월요일 09:00 KST에 `develop` 브랜치에서 공고 스캔을 실행합니다.
- 공고 목록은 `frontend/public/data/notices.json`으로 생성됩니다.
- Actions에서는 상위 공고의 분석 JSON을 `frontend/public/data/analyses/*.json`에 생성할 수 있습니다.
- 실제 첨부파일 원본/PDF/HWP는 git에 올리지 않고 로컬 캐시에 저장합니다.
- 상세 화면에서 공고를 처음 열면 나라장터 딥링크에 접속해 첨부파일을 다운로드합니다.
- 첨부파일은 나라장터 원본 파일명 그대로 `.cache/opportunity_analyzer/attachments/{공고번호}-{차수}/`에 저장합니다.
- HWP/HWPX는 가능한 경우 PDF로 변환해 뷰어에 표시하고, 원본 파일도 함께 보관합니다.
- 동일 공고를 다시 열면 로컬 첨부파일 캐시와 `frontend/public/data/analyses/*.json`을 우선 사용합니다.

## 주요 산출물

```text
frontend/public/data/notices.json
frontend/public/data/analyses/{bidNtceNo}-{bidNtceOrd}.json
reports/*.xlsx
logs/scanner.log
.cache/opportunity_analyzer/attachments/{bidNtceNo}-{bidNtceOrd}/
```

## 캐시 초기화

첨부파일이나 분석 JSON을 새 구조로 다시 생성하고 싶으면 아래처럼 초기화합니다.

```bash
rm -rf .cache/opportunity_analyzer/attachments
rm -f frontend/public/data/analyses/*.json
```

그 다음 분석 API 서버를 재시작하고 상세 화면에서 공고를 다시 열면 첨부파일과 분석 JSON이 다시 생성됩니다.

## GitHub Actions

워크플로우는 `.github/workflows/weekly-g2b-scan.yml`에 있습니다.

- 실행 브랜치: `develop`
- 실행 시간: 매주 월요일 09:00 KST
- 수동 실행: GitHub Actions의 `Weekly G2B Opportunity Scan`에서 `Run workflow`
- 필요 Secret: `G2B_API_KEY`
- 커밋 대상: `frontend/public/data/notices.json`, `frontend/public/data/analyses/*.json`
- artifact: `reports/*.xlsx`, `logs/scanner.log`
