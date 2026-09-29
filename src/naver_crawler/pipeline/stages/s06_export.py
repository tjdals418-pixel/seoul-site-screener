from __future__ import annotations

"""S6: export — Korean column rename + JSON/Excel output.

`parcelPolygon` 같이 큰 nested 필드는 export에서 제외 (Excel 한 셀에
거대한 GeoJSON 들어가면 가독성·용량 둘 다 NG).
"""

# Export에서 제외할 필드 (지도용 nested 데이터)
EXCLUDE_FIELDS = {"parcelPolygon", "groupMembersDetail"}

import pandas as pd

from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger
from naver_crawler.transforms import translate_keys
from naver_crawler.utils.excel import clean_dataframe
from naver_crawler.utils.io import read_json, write_json_atomic

log = get_logger(__name__)


def run(cfg: AppConfig) -> None:
    payload = read_json(cfg.path("simulated_json"))
    articles = payload.get("articles", [])

    # isShown=True인 매물만 export. (False는 등급외/이상치라 보고 가치 낮음)
    shown = [a for a in articles if a.get("isShown")]
    log.info("export filter: %d / %d articles (isShown=True)", len(shown), len(articles))

    # Export에서 제외할 필드 제거 (parcelPolygon 등 nested 데이터)
    cleaned = [{k: v for k, v in a.items() if k not in EXCLUDE_FIELDS} for a in shown]
    translated = [translate_keys(a) for a in cleaned]

    json_out = cfg.path("final_json")
    write_json_atomic(json_out, {"articles": translated})
    log.info("json → %s", json_out)

    df = pd.DataFrame(translated)
    df = clean_dataframe(df)
    xlsx_out = cfg.path("final_xlsx")
    df.to_excel(xlsx_out, index=False, engine="openpyxl")
    log.info("xlsx → %s (%d rows × %d cols)", xlsx_out, len(df), len(df.columns))
