from __future__ import annotations

"""S4: simulate — 호텔·오피스 개발 시뮬레이션 (단일 매물 + 인접 통합개발 그룹).

흐름:
  1) enriched.json 로드
  2) 모든 단일 매물에 `compute_dev_metrics` 적용
  3) 인접 매물 그룹화 → 가상 통합개발 매물 생성 → 시뮬
  4) `apply_show_filter(any_use=True)`로 isShown 결정 — 호텔/오피스 중 하나라도
     가능하면 유지 (대시보드가 용도별로 다시 계산)
  5) simulated.json 저장

가정값 변경은 `dev_simulation` 섹션, 그룹 임계는 `grouping` 섹션 (모두
config/default.yaml).
"""

from collections import Counter

from naver_crawler.config import AppConfig
from naver_crawler.grouping import expand_with_combined_articles
from naver_crawler.logging_setup import get_logger
from naver_crawler.transforms import (
    DevAssumptions,
    apply_show_filter,
    compute_dev_metrics,
    dedupe_by_pnu_min_price,
    find_same_building_duplicates,
)
from naver_crawler.utils.io import read_json, write_json_atomic

log = get_logger(__name__)


def run(cfg: AppConfig) -> None:
    payload = read_json(cfg.path("enriched_json"))
    articles = payload.get("articles", [])

    # 같은 PNU 매물 중복 제거 (네이버에 같은 필지가 다른 articleNo로 여러 번
    # 등재된 경우 — 좌표 미세 차이로 좌표 dedupe로는 안 잡힘)
    before = len(articles)
    articles = dedupe_by_pnu_min_price(articles)
    log.info("dedupe by PNU: %d → %d (-%d)", before, len(articles), before - len(articles))

    # 같은 건물이 부번만 다른 PNU / 인접 동 이름으로 중복 등재된 경우 (그룹화 전에 제거해야
    # 같은 건물 2건이 가상 "합필"로 묶이지 않음)
    dup = find_same_building_duplicates(articles)
    articles = [a for a in articles if str(a.get("articleNo")) not in dup]
    log.info("dedupe same building: -%d", len(dup))

    assumptions = DevAssumptions.from_config(cfg.raw.get("dev_simulation"))
    grouping_cfg = cfg.raw.get("grouping") or {}
    group_distance_m = float(grouping_cfg.get("max_distance_m", 50.0))
    group_centroid_max_m = float(grouping_cfg.get("max_centroid_distance_m", 60.0))

    log.info("simulating %d articles (assumptions: max_land_pyeong=%.0f, group_dist=%.0fm)",
             len(articles), assumptions.max_land_pyeong, group_distance_m)

    # 1) 단일 매물 시뮬 (articleNo 인덱스도 같이 만들어둠 — partOfGroup 주입용)
    single_rows = []
    by_article_no: dict[str, dict] = {}
    for a in articles:
        m = compute_dev_metrics(a, assumptions)
        m["isCombinedDevelopment"] = False
        m["partOfGroup"] = None  # 기본값, 그룹 발견 시 채움
        single_rows.append(m)
        if m.get("articleNo"):
            by_article_no[str(m["articleNo"])] = m

    # 2) 인접 통합개발 그룹 → 가상 매물 시뮬
    combined_articles, groups_meta = expand_with_combined_articles(
        articles,
        max_distance_m=group_distance_m,
        max_centroid_distance_m=group_centroid_max_m,
    )
    combined_rows = [compute_dev_metrics(c, assumptions) for c in combined_articles]
    # compute_dev_metrics가 isCombinedDevelopment를 덮어쓸 수 있으니 재설정
    for r in combined_rows:
        r["isCombinedDevelopment"] = True

    # 2.5) 단일 매물에 "이 매물은 GROUP-N의 멤버" 정보 주입
    for combined in combined_rows:
        group_id = combined.get("articleNo")  # "GROUP-N"
        for member_detail in (combined.get("groupMembersDetail") or []):
            mid = str(member_detail.get("articleNo") or "")
            if mid in by_article_no:
                by_article_no[mid]["partOfGroup"] = group_id

    # 3) 합치기 + show filter
    rows = single_rows + combined_rows
    rows = [apply_show_filter(r, assumptions, any_use=True) for r in rows]

    # 4) 통계 로그
    total = len(rows)
    shown = sum(1 for r in rows if r.get("isShown"))
    shown_combined = sum(1 for r in rows if r.get("isShown") and r.get("isCombinedDevelopment"))
    by_grade = Counter(r.get("hotelGrade") or "계산불가" for r in rows)
    office_ok = sum(1 for r in rows if r.get("officeCapRate") is not None)

    log.info(
        "→ 단일 %d + 통합 %d = 총 %d 매물 (isShown=%d 중 통합=%d)",
        len(single_rows), len(combined_rows), total, shown, shown_combined,
    )
    log.info("호텔 등급 분포 (전체): %s", dict(by_grade.most_common()))
    log.info("오피스 시뮬 가능: %d", office_ok)

    # 통합개발만 따로 분포
    combined_by_grade = Counter(
        r.get("hotelGrade") or "계산불가" for r in rows if r.get("isCombinedDevelopment")
    )
    log.info("등급 분포 (통합개발만): %s", dict(combined_by_grade.most_common()))

    out = cfg.path("simulated_json")
    write_json_atomic(out, {"count": total, "articles": rows, "groups_meta": groups_meta})
    log.info("saved → %s", out)
