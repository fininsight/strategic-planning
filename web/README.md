# 사업제안 에이전트 웹 화면

나라장터 공고 모니터링 결과를 보여주는 React + TypeScript 대시보드 프로토타입입니다.

## 구조

```text
web/
  index.html
  package.json
  public/
    data/
      notices.json  # 스캐너가 생성하는 대시보드 데이터
  src/
    App.tsx
    main.tsx
    styles.css
```

## 실행

```bash
npm install
npm run dev
```

## 데이터 연동

프론트는 `data/notices.json`을 읽어서 공고 목록을 렌더링합니다.

스캐너를 실행하면 웹 화면용 최신 데이터가 아래 위치에 생성됩니다.

```text
web/public/data/notices.json
```

`web/public/data/notices.json`은 Vite 개발 서버에서 `data/notices.json`으로 제공됩니다.
