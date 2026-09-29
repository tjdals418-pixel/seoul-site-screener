from __future__ import annotations

"""S5: parcels — isShown 매물의 필지 polygon (PNU 모양) 받기.

VWorld WFS API로 매물 좌표 주변 bbox 호출 → PNU 매칭하는 GeoJSON geometry
추출. PNU별 캐시(`data/interim/parcels_cache.json`)로 이미 받은 polygon은
재호출 안 함 (idempotent — 다음 weekly run은 새 매물만 호출).

출력:
  - simulated.json 업데이트 — isShown 매물에 `parcelPolygon` 필드 추가
    (GeoJSON geometry dict)
  - parcels_cache.json — PNU → geometry 매핑 캐시
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from naver_crawler.clients.vworld import VWorldClient
from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger
from naver_crawler.utils.io import read_json, write_json_atomic

log = get_logger(__name__)


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(cfg: AppConfig) -> None:
    section = cfg.raw.get("parcels") or {}
    if not section.get("enabled", True):
        log.info("parcels stage disabled (config.parcels.enabled=false) — skipping")
        return

    sim_path = cfg.path("simulated_json")
    # v2 캐시 — 값이 {pnu, geometry, area_m2, resnapped, reason} dict (re-snap 지원).
    # 구 parcels_cache.json은 raw geometry라 포맷 충돌 → 새 파일.
    cache_path = sim_path.parent / "parcels_cache_v2.json"

    payload = read_json(sim_path)
    articles = payload.get("articles", [])
    cache: dict[str, dict | None] = _load_cache(cache_path)

    # 대상: isShown 매물 + PNU 있고 좌표 있고 단일/통합 무관
    targets = [
        a for a in articles
        if a.get("isShown")
        and a.get("pnu")
        and a.get("latitude") is not None
        and a.get("longitude") is not None
        and not str(a.get("articleNo", "")).startswith("GROUP-")  # 통합 가상매물은 polygon X
    ]

    # 캐시 키 = 최초 assemble된 PNU (re-snap 후 pnu가 바뀌어도 idempotent)
    def orig_pnu(a):
        return a.get("pnuOriginal") or a["pnu"]

    to_fetch = [a for a in targets if orig_pnu(a) not in cache]
    log.info(
        "parcels: targets=%d, cache hit=%d, fetch=%d",
        len(targets), len(targets) - len(to_fetch), len(to_fetch),
    )

    # WFS 호출 (병렬) — get_best_parcel로 면적/근접 re-snap
    if to_fetch:
        max_workers = section.get("max_workers", 6)
        client = VWorldClient(
            cfg.secrets.vworld_api_key,
            domain=cfg.secrets.vworld_domain or "localhost",
            timeout_sec=section.get("timeout_sec", 10.0),
        )

        def fetch(art):
            rec = client.get_best_parcel(
                orig_pnu(art), art["latitude"], art["longitude"],
                art.get("landSpace"),
                delta_deg=section.get("bbox_delta_deg", 0.0004),
            )
            return orig_pnu(art), rec

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(fetch, a): orig_pnu(a) for a in to_fetch}
            for fut in tqdm(as_completed(futures), total=len(futures), desc="WFS parcels"):
                op, rec = fut.result()
                cache[op] = rec  # rec None이어도 저장 (재호출 방지)

        write_json_atomic(cache_path, cache)
        log.info("cache saved → %s (total entries: %d)", cache_path, len(cache))

    # simulated.json 매물에 parcelPolygon 첨부 + re-snap 반영
    filled = 0
    resnapped = 0
    for a in articles:
        a["parcelPolygon"] = None
        if not (a.get("pnu") and a.get("isShown")):
            continue
        rec = cache.get(orig_pnu(a))
        if not rec or not rec.get("geometry"):
            continue
        a["parcelPolygon"] = rec["geometry"]
        a["parcelAreaM2"] = rec.get("area_m2")
        filled += 1
        if rec.get("resnapped") and rec.get("pnu"):
            # 좌표가 옆 자투리 필지로 잘못 snap → 면적 맞는 필지로 교정
            a["pnuOriginal"] = orig_pnu(a)
            a["pnu"] = rec["pnu"]
            a["pnuResnapped"] = True
            resnapped += 1

    log.info("parcelPolygon filled: %d / %d (re-snapped: %d)", filled, len(targets), resnapped)
    write_json_atomic(sim_path, payload)
    log.info("simulated.json updated → %s", sim_path)
