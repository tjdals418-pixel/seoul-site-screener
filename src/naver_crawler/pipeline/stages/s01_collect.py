from __future__ import annotations

"""S1: collect — fin.land /article/boundedArticles with auto bbox tiling.

Each seed bbox in config is recursively quad-split until each subtile has
fewer than `max_per_tile` articles, then that subtile is paginated.
"""

from naver_crawler.clients.naver_finland import (
    ArticleFilter,
    BoundingBox,
    FinlandClient,
)
from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger
from naver_crawler.utils.io import write_json_atomic

log = get_logger(__name__)


def run(cfg: AppConfig) -> None:
    section = cfg.section("collect")
    # cookie is optional — FinlandClient auto-acquires fresh cookies by
    # navigating fin.land/map at session start. Override via .env if needed.
    cookie = cfg.secrets.naver_cookie

    filter_ = ArticleFilter(
        trade_types=section["trade_types"],
        real_estate_types=section["real_estate_types"],
    )

    seed_bboxes = section.get("seed_bboxes") or section.get("tiles", [])
    if not seed_bboxes:
        raise RuntimeError("collect.seed_bboxes is empty — define at least one bbox in config.")

    auto_split = section.get("auto_split", True)
    max_per_tile = section.get("max_per_tile", 3000)
    min_tile_deg = section.get("min_tile_deg", 0.005)
    max_depth = section.get("max_depth", 8)
    page_size = section.get("page_size", 30)

    all_articles: list[dict] = []
    seen_ids: set[str] = set()

    with FinlandClient(
        cookie,
        headless=section.get("headless", True),
        pace_sec=section.get("pace_sec", 0.4),
    ) as client:
        for tile in seed_bboxes:
            bbox = BoundingBox(**tile)
            log.info("seed bbox=%s (auto_split=%s)", tile, auto_split)

            iterator = (
                client.iter_bounded_articles_auto(
                    bbox, filter_,
                    max_per_tile=max_per_tile,
                    min_tile_deg=min_tile_deg,
                    max_depth=max_depth,
                    page_size=page_size,
                )
                if auto_split
                else client.iter_bounded_articles(bbox, filter_, page_size=page_size)
            )

            for entry in iterator:
                rep = entry.get("representativeArticleInfo") or {}
                aid = rep.get("articleNumber")
                if not aid or aid in seen_ids:
                    continue
                seen_ids.add(aid)
                all_articles.append(entry)

    out = cfg.path("collected_json")
    write_json_atomic(out, {"count": len(all_articles), "articles": all_articles})
    log.info("collected %d unique articles → %s", len(all_articles), out)
