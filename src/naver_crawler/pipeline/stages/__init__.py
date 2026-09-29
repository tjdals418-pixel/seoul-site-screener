from naver_crawler.pipeline.runner import Stage

from . import (
    s01_collect,
    s02_filter,
    s03_enrich,
    s04_simulate,
    s05_parcels,
    s06_export,
)

# Order matters — each stage's output is the next stage's input.
ALL_STAGES: list[Stage] = [
    Stage("collect",  "fin.land /article/boundedArticles (bbox tiles)",  s01_collect.run),
    Stage("filter",   "Seoul + excluded gu + dedupe",                     s02_filter.run),
    Stage("enrich",   "VWorld → PNU + buildingRegistration + development",s03_enrich.run),
    Stage("simulate", "Hotel + office dev metrics (NOI, Cap Rate …)",    s04_simulate.run),
    Stage("parcels",  "VWorld WFS — 필지 polygon (PNU 모양)",              s05_parcels.run),
    Stage("export",   "Korean column rename + JSON/Excel",                s06_export.run),
]
