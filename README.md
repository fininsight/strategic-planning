# FI Strategic Planning

나라장터 공고를 수집, 필터링, 분석하고 프론트엔드 대시보드에서 확인하기 위한 Python + TypeScript 통합 프로젝트입니다.

## 폴더 구조

```text
.
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── api/        # HTTP API 엔드포인트
│       └── services/
│           ├── scanner/   # 나라장터 공고 수집, 필터링, 스코어링, 엑셀/JSON 생성
│           └── analyzer/  # 첨부파일 다운로드, PDF 변환, 텍스트 추출, LLM 분석
├── frontend/              # React + TypeScript 대시보드/모니터링/분석 화면
├── scripts/               # 브라우저 자동화 등 공용 실행 스크립트
├── reports/               # 로컬/Actions 엑셀 산출물, gitignore 대상
└── logs/                  # 로컬 실행 로그, gitignore 대상
```

## 실행

```bash
# 공고 스캔
PYTHONPATH=backend python -m app.services.scanner

# 분석 API 서버
PYTHONPATH=backend python -m app.api.analysis_server

# 프론트엔드
cd frontend
npm install
npm run dev
```

## 데이터 흐름

- GitHub Actions는 매주 월요일 09:00 KST에 `develop` 브랜치에서 공고 스캔을 실행합니다.
- 공고 목록은 `frontend/public/data/notices.json`으로 생성됩니다.
- 상위 공고의 첨부파일 분석 결과는 `frontend/public/data/analyses/*.json`으로 생성됩니다.
- 실제 첨부파일 원본/PDF는 저장소에 커밋하지 않고, 추후 S3 또는 DB 기반 저장소로 이전하는 것을 권장합니다.
