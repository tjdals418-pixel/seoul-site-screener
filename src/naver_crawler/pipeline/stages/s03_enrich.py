from __future__ import annotations

"""S3: enrich — for each filtered article, look up:

  (a) VWorld reverse geocode → cortarNo + 본번/부번 → 19-digit PNU
  (b) fin.land /complex/buildingRegistration?pnu=… → 용도지역, 용적률, 건폐율,
      구조, 사용승인일, 주차대수
  (c) fin.land /article/agent?articleNumber=… → 중개업소 전화번호 (옵션)
  (d) fin.land /development?type=article&itemId=… → 지구단위계획구역 +
      미래 역세권 (옵션)
  (e) (fallback) VWorld /ned/data/getLandCharacteristics → 용도지역
       — fin.land buildingRegistration이 빈 응답이거나 광역 카테고리만
         줄 때만 호출 (예: "도시지역", "주거지역")

Then flatten into a row dict via `flatten_article`. Output is the input list to
the export stage.
"""

import time

from naver_crawler.clients.naver_finland import FinlandClient
from naver_crawler.clients.vworld import VWorldClient
from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger
from naver_crawler.transforms import FAR_BY_ZONING, flatten_article, lookup_far
from naver_crawler.utils.io import read_json, write_json_atomic
from tqdm import tqdm

log = get_logger(__name__)


def _zoning_needs_fallback(zoning: str | None) -> bool:
    """fin.land가 준 zoning이 None이거나 FAR 매핑 안 되는 경우 → fallback 필요."""
    if not zoning:
        return True
    return zoning not in FAR_BY_ZONING


def run(cfg: AppConfig) -> None:
    enrich_cfg = cfg.section("enrich")
    payload = read_json(cfg.path("filtered_json"))
    articles = payload.get("articles", [])
    log.info("enriching %d articles", len(articles))

    vworld = VWorldClient(
        cfg.secrets.vworld_api_key,
        timeout_sec=cfg.section("geocode")["timeout_sec"],
        domain=cfg.secrets.vworld_domain or "localhost",
    )

    fetch_agent = enrich_cfg.get("fetch_agent", True)
    pace_sec = enrich_cfg.get("pace_sec", 0.4)

    fetch_development = enrich_cfg.get("fetch_development", True)

    rows: list[dict] = []
    pnu_filled = building_filled = agent_filled = vworld_zoning_filled = 0
    development_filled = 0

    with FinlandClient(
        cfg.secrets.naver_cookie,
        headless=enrich_cfg.get("headless", True),
        pace_sec=pace_sec,
    ) as client:
        for entry in tqdm(articles, desc="enrich"):
            rep = entry.get("representativeArticleInfo") or {}
            article_no = rep.get("articleNumber")
            real_estate_type = rep.get("realEstateType", "")
            coord = (rep.get("address") or {}).get("coordinates") or {}
            lat = coord.get("yCoordinate")
            lon = coord.get("xCoordinate")

            # (a) PNU via VWorld
            pnu = None
            if lat is not None and lon is not None:
                geo = vworld.reverse_geocode(float(lat), float(lon))
                if geo:
                    pnu = geo.assemble_pnu()
                    if pnu:
                        pnu_filled += 1

            # (b) buildingRegistration
            building = None
            if pnu and real_estate_type:
                building = client.get_building_registration(pnu, real_estate_type)
                if building:
                    building_filled += 1

            # (c) agent (optional)
            agent = None
            if fetch_agent and article_no:
                agent = client.get_article_agent(article_no)
                if agent:
                    agent_filled += 1

            # (d) development (optional) — 지구단위계획 + 미래 역세권
            development = None
            if fetch_development and article_no:
                development = client.get_development_info(article_no)
                if development and (development.get("jiguList") or development.get("railList")):
                    development_filled += 1

            row = flatten_article(
                entry, pnu=pnu, building=building, agent=agent, development=development,
            )

            # (d) zoning fallback — fin.land이 zoning 안 줬거나 매핑 안 되는 경우
            if pnu and _zoning_needs_fallback(row.get("regZoning")):
                vw_zoning = vworld.get_zoning_by_pnu(pnu)
                if vw_zoning:
                    row["regZoning"] = vw_zoning
                    row["maxFar"], row["maxFarSeoulCore"] = lookup_far(vw_zoning)
                    vworld_zoning_filled += 1

            rows.append(row)
            time.sleep(0)  # FinlandClient already paces; VWorld is fast

    log.info(
        "enrichment: pnu=%d/%d  building=%d/%d  agent=%d/%d  development=%d/%d  vworld_zoning_fb=%d",
        pnu_filled, len(articles),
        building_filled, len(articles),
        agent_filled, len(articles),
        development_filled, len(articles),
        vworld_zoning_filled,
    )

    out = cfg.path("enriched_json")
    write_json_atomic(out, {"count": len(rows), "articles": rows})
    log.info("saved → %s", out)
