"""API 쪽 규칙 — 같은 건물 중복 제거, 필터 정책, 시뮬 캐시 키, 입력 검증."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from naver_crawler.transforms import find_same_building_duplicates, same_building_report
from app.data import match_previous_prices
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


def test_same_building_with_different_asking_price_keeps_conservative_one():
    # 중개사마다 호가만 다르게 올린 같은 건물 (대지·현재 연면적 동일)
    dup = find_same_building_duplicates([
        listing("1", price=110000, floorSpace=1200.0, maxFar=800),
        listing("2", price=100000, floorSpace=1200.0, maxFar=800),
    ])
    assert dup == {"1"}                                       # 호가 낮은 쪽 유지
    # 용도지역이 다르게 잡혔으면 용적률 낮은 쪽을 남긴다
    dup = find_same_building_duplicates([
        listing("1", price=100000, floorSpace=1200.0, maxFar=800),
        listing("2", price=110000, floorSpace=1200.0, maxFar=400),
    ])
    assert dup == {"1"}


def test_previous_price_is_matched_by_building_not_article_number():
    # 매물번호는 재등록 때마다 바뀐다 — 같은 자리·같은 대지면적이면 같은 건물
    previous = [
        listing("OLD-1", price=230000),
        listing("OLD-2", price=210000),                       # 같은 건물, 다른 중개사 호가
        listing("OLD-3", price=500000, lat=37.58),            # 1km 떨어진 다른 건물
        listing("OLD-4", price=400000, land=400.0),           # 같은 자리, 다른 면적
    ]
    current = [listing("NEW-1", price=210000), listing("NEW-2", price=200000, lat=37.6)]
    matched = match_previous_prices(current, previous)
    assert matched == {"NEW-1": 210000}                       # 현재 호가와 가장 가까운 이전 호가


def test_same_building_listed_with_slightly_different_numbers():
    # 호가 99억 vs 100억, 같은 대지·층수·준공연차, 한쪽은 도로명주소 없음 → 같은 건물
    a = listing("1", price=990000, floorSpace=776.0, groundTotalFloor=3, approvalElapsedYear=60,
                regRoadAddress="서울특별시 서대문구 통일로 193 (영천동)")
    b = listing("2", price=1000000, floorSpace=874.0, groundTotalFloor=3, approvalElapsedYear=60)
    assert find_same_building_duplicates([a, b]) == {"2"}
    # 대지면적이 1% 안에서 다르게 적힌 같은 주소
    c = listing("3", price=1580000, land=957.7, regRoadAddress="서울특별시 동대문구 천호대로 71 (용두동)")
    d_ = listing("4", price=1600000, land=951.0, regRoadAddress="서울특별시 동대문구 천호대로 71 (용두동)")
    assert find_same_building_duplicates([c, d_]) == {"4"}


def test_twin_lots_with_different_addresses_are_not_duplicates():
    # 면적이 같은 나란한 필지 — 주소가 다르면 호가가 비슷해도 별개 건물
    a = listing("1", price=480000, land=217.8, groundTotalFloor=3, approvalElapsedYear=32,
                regRoadAddress="서울특별시 강남구 테헤란로16길 30-2 (역삼동)")
    b = listing("2", price=500000, land=217.8, groundTotalFloor=3, approvalElapsedYear=32,
                regRoadAddress="서울특별시 강남구 테헤란로16길 30-1 (역삼동)")
    assert not find_same_building_duplicates([a, b])
    # 주소가 없어도 호가가 크게 다르면 별개
    c = listing("3", price=790000, land=217.3, groundTotalFloor=3)
    d_ = listing("4", price=1200000, land=217.4, groundTotalFloor=3)
    assert not find_same_building_duplicates([c, d_])


def test_twin_lots_at_the_same_price_are_not_duplicates():
    # 면적이 같은 나란한 필지는 땅값 기준으로 호가까지 같게 나온다 — 주소가 다르면 별개
    a = listing("1", price=700000, land=649.7, floorSpace=698.0,
                regRoadAddress="서울특별시 양천구 국회대로 27 (신월동)")
    b = listing("2", price=700000, land=649.6, floorSpace=302.4,
                regRoadAddress="서울특별시 양천구 국회대로 29 (신월동)")
    assert not find_same_building_duplicates([a, b])
    # 대지·연면적이 모두 같으면 주소가 달라도 같은 건물 (대장만 옆 필지로 붙은 경우)
    c = listing("3", price=2500000, land=221.2, floorSpace=331.26,
                regRoadAddress="서울특별시 강남구 테헤란로87길 45 (삼성동)")
    d_ = listing("4", price=2490000, land=221.2, floorSpace=331.26,
                 regRoadAddress="서울특별시 강남구 테헤란로87길 47 (삼성동)")
    assert find_same_building_duplicates([c, d_]) == {"3"}


def test_zoning_conflict_keeps_developable_zone_and_reports_it():
    # 같은 건물이 일반상업과 3종주거로 따로 올라옴 → 신축 가능한 쪽을 남기고 표시
    a = listing("1", price=9100000, floorSpace=1500.0, regZoning="제3종일반주거지역", maxFar=250)
    b = listing("2", price=9000000, floorSpace=1500.0, regZoning="일반상업지역", maxFar=800)
    dropped, conflict = same_building_report([a, b])
    assert dropped == {"1"} and conflict == {"2"}
    # 둘 다 신축 가능 지역이면 용적률 낮은 쪽
    c = listing("3", price=4000000, floorSpace=5215.0, regZoning="일반상업지역", maxFar=800)
    d_ = listing("4", price=4300000, floorSpace=5215.0, regZoning="준주거지역", maxFar=400)
    dropped, conflict = same_building_report([c, d_])
    assert dropped == {"3"} and conflict == {"4"}


def test_previous_listing_matched_when_land_area_was_re_entered():
    # 대지면적만 고쳐 다시 올린 매물 — 연면적이 같으면 같은 건물, 호가도 비교
    previous = [listing("OLD-1", price=4500000, land=495.2, floorSpace=1643.5, pnu="P1")]
    current = [
        listing("NEW-1", price=4300000, land=435.2, floorSpace=1643.5, pnu="P1"),
        # 같은 PNU지만 면적 기재가 전부 달라짐 → 신규는 아니되 호가 비교는 하지 않음
        listing("NEW-2", price=9000000, land=900.0, floorSpace=3000.0, pnu="P1"),
        listing("NEW-3", price=9000000, land=900.0, lat=37.6, pnu="P9"),
    ]
    assert match_previous_prices(current, previous) == {"NEW-1": 4500000, "NEW-2": 0.0}
