"""Seoul Hotel & Office Site Screener API — FastAPI 백엔드.

파이프라인 산출 매물에 호텔/오피스 개발 시뮬레이션과 DCF를 적용해 REST로 노출.
Next.js + Mapbox 프론트엔드가 호출.

실행 (저장소 루트에서):
    pip install -e ".[dev]"
    uvicorn server:app --reload --port 8000

배포: 루트 vercel.json의 api 서비스 (DEPLOYMENT.md 참고).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# api/app/main.py → 프로젝트 루트의 src/ 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from app.data import (
    build_assumptions,
    data_as_of,
    get_geo_stats,
    load_gu_boundaries,
    load_previous_snapshot,
    load_raw_articles,
    load_subway_lines,
    load_subway_stations,
    resim_articles,
)
from app.feasibility import FeasibilityAssumptions, compute_feasibility
from app.filters import filter_articles
from app.schemas import (
    Article,
    ArticleList,
    FeasibilityAssumptionsModel,
    FeasibilityResponse,
    FilterParams,
    SimAssumptions,
)

log = logging.getLogger("naver_crawler.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """startup: 기본 시뮬 결과를 백그라운드에서 미리 계산.

    계산(필지 인접성 + 전체 시뮬)이 수 초 걸려도 서버 기동과 헬스체크는 막지 않는다.
    그 사이 들어온 요청은 _DEFAULT_CACHE_LOCK에서 계산이 끝날 때까지 기다린다.
    """
    import asyncio

    async def _warmup():
        try:
            # 동기 무거운 작업을 thread로 offload (event loop 차단 방지)
            await asyncio.to_thread(_get_default_articles)
            log.info("[startup] default cache ready (%d articles)",
                     len(_DEFAULT_ARTICLES_CACHE or []))
        except Exception:  # noqa: BLE001
            log.exception("[startup] warmup failed")

    log.info("[startup] scheduling background warmup...")
    task = asyncio.create_task(_warmup())
    yield
    # shutdown: warmup task가 아직 돌고 있으면 취소
    if not task.done():
        task.cancel()


app = FastAPI(
    title="Seoul Hotel & Office Site Screener API",
    description="서울 매물 호텔·오피스 개발 사업성 시뮬레이션 API",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS — 기본은 next.config.ts rewrites(same-origin)라 불필요. 프론트를 별도
# 도메인에서 직접 호출할 때만 CORS_ORIGINS(콤마 구분)에 등록.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",") if o.strip()
]

# 매물 목록 JSON(~1MB)은 gzip으로 ~10배 줄어듦
app.add_middleware(GZipMiddleware, minimum_size=2048)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# 기본 시뮬 결과 in-memory cache
_DEFAULT_ARTICLES_CACHE: list[dict] | None = None
_DEFAULT_CACHE_LOCK = threading.Lock()


def _get_default_articles() -> list[dict]:
    """default 시뮬 가정값으로 처리된 매물. 첫 호출 시 1회만 계산.

    threading.Lock으로 double-check locking — startup lifespan에서 미리 빌드되지만
    그 전에 health probe 등이 들어올 수 있어 lock으로 보호.
    """
    global _DEFAULT_ARTICLES_CACHE
    if _DEFAULT_ARTICLES_CACHE is None:
        with _DEFAULT_CACHE_LOCK:
            if _DEFAULT_ARTICLES_CACHE is None:
                _DEFAULT_ARTICLES_CACHE = resim_articles(None, DEFAULT_USE)
    return _DEFAULT_ARTICLES_CACHE


DEFAULT_USE = "best"
UseParam = Literal["hotel", "office", "best"]


def _sim_key(assumptions: SimAssumptions | None, use: str = DEFAULT_USE) -> str:
    d = assumptions.model_dump(exclude_none=True, exclude={"use"}) if assumptions else {}
    if not d and use == DEFAULT_USE:
        return ""
    return json.dumps({"sim": d, "use": use}, sort_keys=True)


@lru_cache(maxsize=16)
def _simulate_cached(key: str) -> list[dict]:
    """시뮬 결과 캐시 — 같은 가정값·용도 재요청 시 전체 재계산 방지."""
    if not key:
        return _get_default_articles()
    k = json.loads(key)
    return resim_articles(k["sim"] or None, k["use"])


def _find_article(article_id: str, key: str = "") -> dict | None:
    for a in _simulate_cached(key):
        if str(a.get("articleNo")) == article_id:
            return a
    return None


# ── routes ────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/api/health")   # 배포 환경에서는 /api/* 만 이 서비스로 오므로 같은 헬스체크를 노출
def root():
    raw = load_raw_articles()
    return {
        "status": "ok",
        "service": "site-screener-api",
        "data_as_of": data_as_of(),
        "raw_articles": len(raw),
        "sim_articles": len(_get_default_articles()),
    }


@app.get("/api/articles", response_model=ArticleList)
def list_articles(
    use: UseParam = Query(default=DEFAULT_USE),
    gu: list[str] = Query(default=[]),
    categories: list[str] = Query(default=[]),
    grades: list[str] = Query(default=[]),
    price_min_M: float | None = Query(default=None),
    price_max_M: float | None = Query(default=None),
    land_min: float | None = Query(default=None),
    land_max: float | None = Query(default=None),
    cap_min: float | None = Query(default=None),
    cap_max: float | None = Query(default=None),
    zonings: list[str] = Query(default=[]),
    only_with_rail: bool = Query(default=False),
    only_with_jigu: bool = Query(default=False),
    hotel_zone_only: bool = Query(default=False),
    outliers_only: bool = Query(default=False),
) -> ArticleList:
    """필터된 매물 list. 기본 시뮬 가정값 + 선택 용도 기준."""
    params = FilterParams(
        gu=gu, categories=categories, grades=grades,
        price_min_M=price_min_M, price_max_M=price_max_M,
        land_min=land_min, land_max=land_max,
        cap_min=cap_min, cap_max=cap_max,
        zonings=zonings,
        only_with_rail=only_with_rail,
        only_with_jigu=only_with_jigu,
        hotel_zone_only=hotel_zone_only,
        outliers_only=outliers_only,
    )
    articles = _simulate_cached(_sim_key(None, use))
    filtered = filter_articles(articles, params)
    return ArticleList(
        count=len(filtered),
        articles=[Article(**a) for a in filtered],
    )


@app.get("/api/articles/{article_id}", response_model=Article)
def get_article(article_id: str, use: UseParam = Query(default=DEFAULT_USE)) -> Article:
    """개별 매물 디테일 (기본 가정값 기준)."""
    a = _find_article(article_id, _sim_key(None, use))
    if a is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    return Article(**a)


@app.post("/api/simulate", response_model=ArticleList)
def simulate(assumptions: SimAssumptions) -> ArticleList:
    """시뮬 가정값을 받아 매물 재계산 (결과는 가정값별로 캐시).

    프론트엔드에서 시뮬 슬라이더 변경 후 호출.
    """
    articles = _simulate_cached(_sim_key(assumptions, assumptions.use or DEFAULT_USE))
    return ArticleList(
        count=len(articles),
        articles=[Article(**a) for a in articles],
    )


@app.post("/api/articles/{article_id}/feasibility", response_model=FeasibilityResponse)
def article_feasibility(
    article_id: str,
    assumptions: FeasibilityAssumptionsModel | None = None,
) -> FeasibilityResponse:
    """단일 매물의 DCF 사업성 (IRR / NPV / Payback) — 선택 용도(호텔/오피스) 기준.

    Body로 DCF 가정값 override 가능 (모두 optional). `sim`을 함께 보내면 그
    시뮬 가정값으로 재계산된 매물 기준으로 DCF를 돌린다.
    """
    sim = assumptions.sim if assumptions else None
    use = (assumptions.use if assumptions else None) or DEFAULT_USE
    target = _find_article(article_id, _sim_key(sim, use))
    if target is None:
        raise HTTPException(404, f"Article {article_id} not found")

    # override만 dict로 collect
    a_dict = assumptions.model_dump(exclude_none=True, exclude={"sim", "use"}) if assumptions else {}
    if "ramp_up" in a_dict and isinstance(a_dict["ramp_up"], list):
        a_dict["ramp_up"] = tuple(a_dict["ramp_up"])
    # GOP→NOI 차감률 기본값은 현재 시뮬 가정값과 동일하게 (헤드라인 Cap Rate와 일치)
    dev = build_assumptions(sim.model_dump(exclude_none=True, exclude={"use"}) if sim else None)
    noi_defaults = {k: getattr(dev, k) for k in (
        "mgmt_fee_base", "mgmt_fee_incentive", "property_tax_rate", "ff_e_reserve",
    )}
    noi_defaults |= {"loan_rate": dev.interest_rate, "ltv": dev.ltv}
    fa = FeasibilityAssumptions(**{**noi_defaults, **a_dict})
    cy = fa.construction_years if fa.construction_years is not None else 2
    if fa.hold_years <= cy:
        raise HTTPException(422, "보유 기간은 공사 기간보다 길어야 합니다.")

    result = compute_feasibility(target, fa)
    if result is None:
        raise HTTPException(
            422,
            f"Article {article_id}는 시뮬 결과 없음 (costTotalM/noiAnnualM 미산출). "
            "통합그룹 멤버는 부모 그룹의 DCF를 보세요.",
        )
    return FeasibilityResponse(
        irr_unlevered=result.irr_unlevered,
        irr_levered=result.irr_levered,
        npv_M=result.npv_M,
        npv_dev_M=result.npv_dev_M,
        payback_year=result.payback_year,
        yoc_year3=result.yoc_year3,
        exit_value_M=result.exit_value_M,
        entry_cap=result.entry_cap,
        exit_cap_used=result.exit_cap_used,
        noi_to_gop=result.noi_to_gop,
        construction_years_used=result.construction_years_used,
        cash_flows_M=result.cash_flows_M,
        cash_flows_equity_M=result.cash_flows_equity_M,
        notes=result.notes,
    )


@app.get("/api/meta/gu-options")
def gu_options() -> dict:
    """필터 옵션 — 자치구 / 등급 / 용도지역 / 최대 가격."""
    articles = _get_default_articles()
    gus = sorted({a.get("divisionName") for a in articles if a.get("divisionName")})
    grades = ["5성급", "4성급", "3성급"]
    zonings = sorted({a.get("regZoning") for a in articles if a.get("regZoning")})
    price_max_M = max(
        ((a.get("dealPrice") or 0) / 100 for a in articles),
        default=10000,
    )
    prev_date, _ = load_previous_snapshot()
    return {
        "gu": gus,
        "grades": grades,
        "zonings": zonings,
        "price_max_M": int(price_max_M),
        "land_max_pyeong": int(build_assumptions().max_land_pyeong),
        "total_articles": len(articles),
        "data_as_of": data_as_of(),
        "prev_snapshot_date": prev_date,
    }


@app.get("/api/meta/sim-defaults")
def sim_defaults() -> dict:
    """현재 적용 중인 시뮬 기본 가정값 (config/default.yaml 기준) — SimForm 초기값."""
    return asdict(build_assumptions())


@app.get("/api/meta/gu-boundaries")
def gu_boundaries() -> dict:
    """서울 25개 자치구 경계 GeoJSON (지도 layer용)."""
    return load_gu_boundaries()


@app.get("/api/meta/subway-lines")
def subway_lines() -> dict:
    """서울 지하철 노선 GeoJSON (line layer용, 노선별 color 포함)."""
    return load_subway_lines()


@app.get("/api/meta/subway-stations")
def subway_stations() -> dict:
    """서울 지하철 역 GeoJSON (Point layer용)."""
    return load_subway_stations()


@app.get("/api/meta/data-quality")
def data_quality() -> dict:
    """데이터 품질 지표 — geo 변환 실패, 결측 가격/면적 등.

    매물 워크스루에서 silent skip 수치 추적용.
    """
    articles = _get_default_articles()
    geo = get_geo_stats()
    members = sum(1 for a in articles
                  if a.get("partOfGroup") and not a.get("isCombinedDevelopment"))
    price_missing = sum(1 for a in articles if a.get("dealPriceMissing"))
    land_missing = sum(1 for a in articles if a.get("landSpaceMissing"))
    no_cap = sum(
        1 for a in articles
        if not (a.get("partOfGroup") and not a.get("isCombinedDevelopment"))
        and a.get("capRate") is None
    )
    return {
        "total_articles": len(articles),
        "candidates": len(articles) - members,
        "group_members": members,
        "geo_skipped": geo.get("skipped", 0),
        "geo_total": geo.get("total", 0),
        "deal_price_missing": price_missing,
        "land_space_missing": land_missing,
        "no_cap_rate": no_cap,
    }
