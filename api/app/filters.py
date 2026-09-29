"""매물 필터링 (dict in/out). 프론트엔드 applyFilterClient와 같은 정책."""
from __future__ import annotations

from naver_crawler.transforms import is_dev_zone


def _category_of(a: dict) -> str:
    if a.get("isCombinedDevelopment"):
        return "통합그룹"
    if a.get("partOfGroup"):
        return "그룹멤버"
    return "단일"


def filter_articles(articles: list[dict], f) -> list[dict]:
    """FilterParams 적용. dict in/out (pandas 없이).

    그룹멤버는 통합개발 시각 보조용이라 grade/price/land/cap/zoning 같은
    개별 매물 필터는 무시하고, 소속 통합그룹이 필터를 통과했을 때만 보인다.
    예외: outliers_only는 멤버에도 적용 — 사용자가 "outlier만" 의도하면
    멤버까지 다 나오는 게 혼란.
    """
    kept = _filter_pass(articles, f)
    visible_groups = {str(a.get("articleNo")) for a in kept
                      if a.get("isCombinedDevelopment")}
    return [
        a for a in kept
        if _category_of(a) != "그룹멤버"
        or str(a.get("partOfGroup")) in visible_groups
        # 카테고리 필터로 그룹 자체를 숨기고 멤버만 보는 경우는 허용
        or (f.categories and "통합그룹" not in f.categories)
    ]


def _filter_pass(articles: list[dict], f) -> list[dict]:
    out = []
    for a in articles:
        cat = _category_of(a)
        is_member = cat == "그룹멤버"

        if f.gu and a.get("divisionName") not in f.gu:
            continue
        if f.categories and cat not in f.categories:
            continue

        # outliers_only는 멤버에도 적용 (단독 흐름)
        if is_member and getattr(f, "outliers_only", False):
            if not (a.get("outlierFlags") or []):
                continue

        # 그룹멤버는 단독 등급/가격/면적 필터를 적용하지 않음 (보조 시각)
        if not is_member:
            if f.grades and (a.get("devClass") or "") not in f.grades:
                continue

            price_M = (a.get("dealPrice") or 0) / 100  # 만원 → 백만원
            if f.price_min_M is not None and price_M < f.price_min_M:
                continue
            if f.price_max_M is not None and price_M > f.price_max_M:
                continue

            land_py = a.get("landPyeong") or 0
            if f.land_min is not None and land_py < f.land_min:
                continue
            if f.land_max is not None and land_py > f.land_max:
                continue

            cr = a.get("capRate")
            if f.cap_min is not None:
                if cr is None or cr < f.cap_min:
                    continue
            if f.cap_max is not None:
                if cr is None or cr > f.cap_max:
                    continue

            if f.zonings and (a.get("regZoning") or "") not in f.zonings:
                continue

            if f.only_with_rail:
                rail = a.get("devNearestRailStation") or ""
                if not str(rail).strip():
                    continue
            if f.only_with_jigu:
                jigu = a.get("devJiguPrimaryName") or ""
                if not str(jigu).strip():
                    continue
            # 호텔/오피스 신축 가능 용도지역만 (일반주거 / 전용주거 / 녹지 등 제외)
            if getattr(f, "hotel_zone_only", False):
                if not is_dev_zone(a.get("regZoning")):
                    continue
            # outlier만 보기 — 데이터 의심/검증용
            if getattr(f, "outliers_only", False):
                if not (a.get("outlierFlags") or []):
                    continue

        out.append(a)
    return out
