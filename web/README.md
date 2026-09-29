# web — Next.js + Mapbox 프론트엔드

```bash
cp .env.example .env.local   # NEXT_PUBLIC_MAPBOX_TOKEN 입력
npm install
npm run dev                  # http://localhost:3000 (API는 127.0.0.1:8000으로 프록시)
```

| 경로 | 역할 |
|---|---|
| `src/app/page.tsx` | 레이아웃 (좌 순위·조건 / 지도 / 우 상세, 모바일은 드로어 + 하단 시트) |
| `src/lib/articles-context.tsx` | 용도·가정값별 목록을 한 번 받아 두고 필터는 클라이언트에서 적용 |
| `src/lib/dev-class.ts` | 용도·등급 목록, 취득 Cap 구간 색 |
| `src/components/Map.tsx` | Mapbox GL — 마커, 필지 경계, 합필 연결선, 자치구, 지하철 |
| `src/components/DetailPanel.tsx` | 매물 상세, 호텔/오피스 비교, DCF |
| `src/components/SimForm.tsx` | 시뮬 가정값 (초기값은 `/api/meta/sim-defaults`) |
