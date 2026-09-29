# api — FastAPI 백엔드

파이프라인이 만든 매물 데이터에 호텔·오피스 개발 시뮬레이션과 DCF를 적용해 제공합니다.

```bash
# 프로젝트 루트에서
.venv/Scripts/python -m uvicorn app.main:app --app-dir api --port 8000 --reload
```

http://127.0.0.1:8000/docs 에서 Swagger 문서를 볼 수 있습니다.

## 데이터 소스

1. `data/interim/simulated.json` — 로컬에서 파이프라인을 돌렸을 때
2. `data/public/articles.json.gz` — 저장소에 포함된 공개용 데이터 (`scripts/export_public.py` 산출, 중개사 정보 제거)

기본 가정값은 `config/default.yaml`의 `dev_simulation` 섹션입니다.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스체크, 데이터 기준일, 매물 수 |
| GET | `/api/articles?use=best` | 매물 목록 (use = best / hotel / office, 필터 query 지원) |
| GET | `/api/articles/{id}?use=` | 매물 상세 |
| POST | `/api/simulate` | 가정값(+ `use`)으로 전체 재계산 — 결과는 가정값별로 캐시 |
| POST | `/api/articles/{id}/feasibility` | DCF (IRR / NPV / 회수기간). body에 DCF 가정, `sim`, `use` |
| GET | `/api/meta/gu-options` | 자치구·용도지역 목록, 가격 범위, 데이터 기준일 |
| GET | `/api/meta/sim-defaults` | 현재 적용 중인 시뮬 가정값 |
| GET | `/api/meta/gu-boundaries` · `subway-lines` · `subway-stations` | 지도 레이어 GeoJSON |
| GET | `/api/meta/data-quality` | 후보 수, 결측·지오메트리 오류 통계 |

## 모듈

| 파일 | 역할 |
|---|---|
| `app/data.py` | 데이터 로드(개인정보 제거), 가정값 병합, 통합그룹 인접성(Shapely STRtree), 재계산 |
| `app/feasibility.py` | DCF — 호텔은 GOP→NOI, 오피스는 lease-up 반영, unlevered/levered 현금흐름 |
| `app/filters.py` | 목록 필터 (프론트 `applyFilterClient`와 같은 규칙) |
| `app/schemas.py` | 응답 스키마 — 선언된 필드만 내보냄 |
