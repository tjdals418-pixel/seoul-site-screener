from __future__ import annotations

"""S2: filter — keep Seoul (ex. excluded gu) + dedupe by location."""

from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger
from naver_crawler.transforms import dedupe_by_address_min_price, filter_seoul
from naver_crawler.utils.io import read_json, write_json_atomic

log = get_logger(__name__)


def run(cfg: AppConfig) -> None:
    section = cfg.section("seoul_filter")
    payload = read_json(cfg.path("collected_json"))
    articles = payload.get("articles", [])
    log.info("input: %d", len(articles))

    # boundedArticles entries are wrapped in `representativeArticleInfo` —
    # filter_seoul reads that nested address, so flatten just the addr layer.
    rebased = [a.get("representativeArticleInfo", {}) | {"_envelope": a} for a in articles]
    rebased = filter_seoul(
        rebased,
        required_si=section["required_si"],
        excluded_gu=section["excluded_gu"],
    )
    log.info("after geo filter: %d", len(rebased))

    deduped = dedupe_by_address_min_price(rebased)
    log.info("after dedupe: %d", len(deduped))

    out_articles = [item.pop("_envelope") for item in deduped]
    out = cfg.path("filtered_json")
    write_json_atomic(out, {"count": len(out_articles), "articles": out_articles})
    log.info("saved → %s", out)
