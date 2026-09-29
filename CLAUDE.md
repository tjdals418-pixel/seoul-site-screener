# CLAUDE.md

이 저장소에서 작업하는 사람(또는 AI 코딩 도구)이 빠르게 맥락을 잡기 위한 문서. 소개는 README 참고.

## 한 줄 요약

서울 빌딩·상가 매물 → 호텔/오피스 개발 시뮬 → **취득 Cap(NOI ÷ 총사업비)** 순위 → 지도 대시보드.
제품의 1순위는 "사업성 나오는 부지를 한눈에 찾기", 가정값 조정은 2순위.

## 구조

```
src/naver_crawler/        파이프라인 (python -m naver_crawler run [--from/--to STAGE])
  transforms.py           ★ 시뮬 핵심: compute_dev_metrics → _hotel_metrics / _office_metrics → select_use
  grouping.py             인접 매물 union-find (동·용도지역 같고 50m 이내)
  pipeline/stages/        collect → filter → enrich → simulate → parcels → export
api/app/                  FastAPI
  data.py                 로드(agent*/broker* 제거) · config 병합 · 그룹 인접성(STRtree 4m) · resim
  feasibility.py          DCF (호텔 GOP→NOI / 오피스 lease-up)
web/src/                  Next.js 16 + Mapbox GL (web/AGENTS.md: Next 16 API는 node_modules/next/dist/docs 확인)
config/default.yaml       모든 가정값 (API 기본값의 source)
data/public/              배포용 데이터 (scripts/export_public.py) — git 포함
data/interim, raw, snapshots  로컬 전용 (gitignore)
tests/                    pytest — 시뮬·DCF 공식
```

## 지표 정의 (바꿀 때 전부 같이)

- **취득 Cap** = 안정화 NOI ÷ 총사업비. 순위·지도 색·최적 용도 선택 모두 이것 하나.
- 총사업비 = 매입 + 공사(연면적 × 평당) + 부대 6% + 건설이자(LTV 60% × 5.5% × 2년)
- 호텔 NOI = GOP − 운영사 fee(매출 2% + GOP 8%) − FF&E 3% − 재산세 0.3%(총사업비)
- 오피스 NOI = 연면적 × 전용률 50% × 권역 NOC × 12 − 연면적 × 3만원/평/월 × 12
- 최적 용도(best) = 상업·준주거·준공업 지역에서 호텔/오피스 중 취득 Cap 높은 쪽
- 매각 Cap(exitCap)은 DCF에만 사용 (호텔: 자치구 Tier, 오피스: 권역)
- 순위 기준은 취득 Cap 하나로 고정 (스프레드·개발이익률은 쓰지 않음)

## 단위

- fin.land priceInfo는 **원** → flatten에서 만원으로 변환(`_won_to_10k`). 이후 dealPrice = 만원.
- `*_M` = 백만원, `*_10k` = 만원, 면적 `*Pyeong` = 평, `landSpace` = ㎡.

## 자주 쓰는 명령

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir api --port 8000 --reload
cd web && npm run dev
.venv/Scripts/python -m pytest
.venv/Scripts/python -m naver_crawler run --from simulate     # 가정값만 바꿨을 때
.venv/Scripts/python scripts/export_public.py                 # 배포 데이터 갱신
```

## 주의

- 중개사 이름·전화번호는 수집하지 않는다 (`enrich.fetch_agent: false`). API도 재귀 제거.
- `compute_dev_metrics`는 입력 dict를 수정하지 않는다 (API가 lru_cache 원본을 넘김).
- 그룹이 탈락하면 멤버의 partOfGroup을 지워 단일 매물로 되돌린다 (`resim_articles`).
- 필터 규칙은 `api/app/filters.py`와 `web/src/lib/api.ts:applyFilterClient` 두 곳 — 같이 수정.
- 크롤링은 수 시간 걸림 (enrich ≈ 1초/건). PC 절전 시 멈춤.
