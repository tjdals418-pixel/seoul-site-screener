"""API 쪽 규칙 — 같은 건물 중복 제거, 필터 정책, 시뮬 캐시 키, 입력 검증."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from naver_crawler.transforms import find_same_building_duplicates
from app.filters import filter_articles
from app.main import _sim_key
from app.schemas import FilterParams, SimAssumptions


def listing(aid, price=100000, land=325.0, lat=37.5706, lon=126.9616, gu="서대문구", **kw):
    return {"articleNo": aid, "dealPrice": price, "landSpace": land,
            "latitude": lat, "longitude": lon, "divisionName": gu, **kw}


def test_same_building_listed_twice_is_deduped():
    dup = find_same_building_duplicates([
        listing("200"), listing("100", lat=37.57065),        # 약 5m 떨어진 같은 건물
    ])
    assert dup == {"200"}                                     # articleNo 작은 쪽 유지


def test_dedupe_keeps_group_member_over_outsider():
    dup = find_same_building_duplicates([
        listing("100"), listing("200", partOfGroup="GROUP-1"),
    ])
    assert dup == {"100"}                                     # 합필 멤버를 남김


def test_different_price_or_far_apart_is_not_duplicate():
    assert not find_same_building_duplicates([listing("1"), listing("2", price=90000)])
    assert not find_same_building_duplicates([listing("1"), listing("2", lat=37.58)])  # ~1km


def test_member_shown_only_when_parent_group_passes_filters():
    rows = [
        {"articleNo": "GROUP-1", "isCombinedDevelopment": True, "capRate": 0.03, "divisionName": "중구"},
        {"articleNo": "m1", "partOfGroup": "GROUP-1", "divisionName": "중구"},
        {"articleNo": "s1", "capRate": 0.07, "divisionName": "중구"},
    ]
    out = {a["articleNo"] for a in filter_articles(rows, FilterParams(cap_min=0.05))}
    assert out == {"s1"}                                      # 그룹이 빠지면 멤버도 숨김
    out = {a["articleNo"] for a in filter_articles(rows, FilterParams(cap_min=0.02))}
    assert out == {"GROUP-1", "m1", "s1"}


def test_sim_cache_key_ignores_order_and_nulls():
    a = SimAssumptions.model_validate({"ltv": 0.6, "grade_3": {"adr_10k": 16, "occupancy": None}})
    b = SimAssumptions.model_validate({"grade_3": {"adr_10k": 16}, "ltv": 0.6, "office": None})
    assert _sim_key(a, "best") == _sim_key(b, "best")
    assert _sim_key(None, "best") == ""                       # 기본값은 공용 캐시
    assert _sim_key(None, "hotel") != _sim_key(None, "office")


def test_sim_assumptions_reject_bad_input():
    with pytest.raises(ValidationError):
        SimAssumptions.model_validate({"grade_3": {"adr_10k": -1}})
    with pytest.raises(ValidationError):
        SimAssumptions.model_validate({"grade_3_min_pyeong": 5000, "grade_4_min_pyeong": 100})
