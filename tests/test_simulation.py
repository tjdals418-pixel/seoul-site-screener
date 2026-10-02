"""호텔·오피스 시뮬레이션과 DCF의 핵심 산식 검증.

숫자는 config가 아니라 코드 기본값(DevAssumptions())으로 계산한 기대값이다.
"""
from __future__ import annotations

import pytest

from naver_crawler.transforms import (
    DevAssumptions,
    apply_show_filter,
    compute_dev_metrics,
    get_office_market,
    is_dev_zone,
    rail_opened,
)
from app.feasibility import FeasibilityAssumptions, compute_feasibility

SQM_PER_PYEONG = 1 / 0.3025


def site(land_pyeong: float, price_eok: float, zoning: str, gu: str = "중구") -> dict:
    return {
        "articleNo": "T1",
        "landSpace": land_pyeong * SQM_PER_PYEONG,
        "dealPrice": price_eok * 10000,          # 만원
        "regZoning": zoning,
        "divisionName": gu,
    }


A = DevAssumptions()


def test_development_area_and_hotel_grade():
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "hotel")
    # 지상 300 × 800% + 지하 300 × 60%
    assert m["devAbovePyeong"] == pytest.approx(2400)
    assert m["devTotalPyeong"] == pytest.approx(2580)
    assert m["hotelGrade"] == "3성급"          # 1,500 ~ 3,000평
    assert m["devUse"] == "hotel"


def test_hotel_cap_is_noi_over_total_cost():
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "hotel")
    assert m["capRate"] == pytest.approx(m["noiAnnualM"] / m["costTotalM"], abs=1e-4)
    # NOI는 GOP보다 작다 (운영사 fee·FF&E·재산세 차감)
    assert 0.6 < m["noiAnnualM"] / m["gopAnnualM"] < 0.85
    # 총사업비 = 매입 + 공사 + 부대 + 금융
    parts = sum(m[k] for k in ("costPurchaseM", "costConstructionM", "costIncidentalM", "costFinanceM"))
    assert m["costTotalM"] == pytest.approx(parts, abs=0.1)


def test_office_noi_formula():
    # 을지로입구역 옆 (CBD 핵심)
    src = site(300, 600, "일반상업지역") | {"latitude": 37.5660, "longitude": 126.9830}
    m = compute_dev_metrics(src, A, "office")
    total = m["devTotalPyeong"]
    noc = A.office.markets["CBD"].noc_10k
    rev = total * 0.5 * noc * 12 / 100                 # 전용 × NOC × 12 (백만원)
    opex = total * A.office.opex_10k_per_pyeong * 12 / 100
    assert m["officeMarket"] == "CBD"
    assert m["officeRevenueAnnualM"] == pytest.approx(rev, abs=0.1)
    assert m["officeOpexAnnualM"] == pytest.approx(opex, abs=0.1)
    assert m["noiAnnualM"] == pytest.approx(rev - opex, abs=0.1)
    assert m["capRate"] == pytest.approx((rev - opex) / m["costTotalM"], abs=1e-4)


def test_best_use_picks_higher_cap_in_permitted_zone():
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "best")
    assert m["devUse"] in ("hotel", "office")
    assert m["capRate"] == max(m["hotelCapRate"], m["officeCapRate"])


def test_best_use_excludes_residential_zone():
    m = compute_dev_metrics(site(1500, 600, "제2종일반주거지역"), A, "best")
    assert m["hotelCapRate"] is not None        # 계산은 되지만
    assert m["devUse"] is None                   # 주거지역이라 최적 용도 후보 아님
    assert m["capRate"] is None


def test_small_site_is_not_simulated():
    m = compute_dev_metrics(site(50, 100, "일반상업지역"), A, "best")
    # 50평 × 8.6 = 430평 → 호텔(1,500평)·오피스(1,000평) 모두 미달
    assert m["hotelGrade"] == "등급외"
    assert m["officeCapRate"] is None
    assert apply_show_filter(m, A)["isShown"] is False


def test_input_article_is_not_mutated():
    src = site(300, 600, "일반상업지역")
    before = dict(src)
    compute_dev_metrics(src, A, "best")
    assert src == before


def test_stale_metrics_are_reset():
    src = site(50, 100, "일반상업지역") | {"capRate": 0.99, "hotelGrade": "5성급"}
    m = compute_dev_metrics(src, A, "hotel")
    assert m["capRate"] is None
    assert m["hotelGrade"] == "등급외"


@pytest.mark.parametrize("use", ["hotel", "office"])
def test_dcf_yield_on_cost_matches_headline_cap(use):
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, use)
    r = compute_feasibility(m, FeasibilityAssumptions())
    assert r is not None
    assert r.yoc_year3 == pytest.approx(m["capRate"], abs=1e-3)
    assert r.exit_cap_used == m["exitCap"]


def test_dcf_unlevered_excludes_finance_cost():
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "hotel")
    r = compute_feasibility(m, FeasibilityAssumptions(construction_years=2, hold_years=5))
    capex = -(r.cash_flows_M[0] + r.cash_flows_M[1])
    vehicle = m["costTotalM"] * 0.006 * 2
    assert capex - vehicle == pytest.approx(m["costTotalM"] - m["costFinanceM"], rel=1e-6)


def test_zone_and_market_helpers():
    assert is_dev_zone("일반상업지역")
    assert is_dev_zone("준공업지역,노선상업지역")
    assert not is_dev_zone("제3종일반주거지역")
    assert get_office_market("강남구") == "GBD"
    assert get_office_market("성동구") == "기타"


def test_historic_core_uses_ordinance_far():
    inside = site(300, 600, "일반상업지역") | {"latitude": 37.5636, "longitude": 126.9826}   # 명동
    outside = site(300, 600, "일반상업지역") | {"latitude": 37.4979, "longitude": 127.0276}  # 강남역
    m_in = compute_dev_metrics(inside, A, "hotel")
    m_out = compute_dev_metrics(outside, A, "hotel")
    assert m_in["inHistoricCore"] and m_in["maxFar"] == 600
    assert not m_out["inHistoricCore"] and m_out["maxFar"] == 800
    assert m_in["devAbovePyeong"] == pytest.approx(300 * 6)


def test_partial_unit_listing_is_hidden():
    # 연면적 14,000㎡ 건물이 120억 → 건물 평당 약 280만원: 호실·지분 매물로 보고 제외
    src = site(287, 120, "일반상업지역") | {"floorSpace": 14438.86}
    m = apply_show_filter(compute_dev_metrics(src, A, "hotel"), A)
    assert m["isShown"] is False and "호실" in m["shownReason"]


def test_land_share_of_large_parcel_is_hidden():
    # 대지 820㎡인데 소재 필지는 67,537㎡ → 단지 안 대지지분
    src = site(248, 140, "일반상업지역") | {"parcelAreaM2": 67537.4}
    m = apply_show_filter(compute_dev_metrics(src, A, "hotel"), A)
    assert m["isShown"] is False and "대지지분" in m["shownReason"]


def test_site_already_built_out_is_not_a_candidate():
    # 개발 가능 연면적 2,580평인데 현재 건물이 이미 1,900평(74%) — 새로 지어도 1.5배가 안 됨
    src = site(300, 600, "일반상업지역") | {"floorSpace": 1900 * SQM_PER_PYEONG, "approvalElapsedYear": 30}
    m = apply_show_filter(compute_dev_metrics(src, A, "hotel"), A)
    assert m["isShown"] is False and "신축 실익" in m["shownReason"]
    low = src | {"floorSpace": 1500 * SQM_PER_PYEONG}         # 58%면 후보
    assert apply_show_filter(compute_dev_metrics(low, A, "hotel"), A)["isShown"] is True


def test_new_building_is_not_a_candidate_unless_underbuilt():
    built = site(300, 600, "일반상업지역") | {"floorSpace": 1500 * SQM_PER_PYEONG, "approvalElapsedYear": 20}
    m = apply_show_filter(compute_dev_metrics(built, A, "hotel"), A)
    assert m["isShown"] is False and "철거 실익" in m["shownReason"]   # 20년차에 58% 사용 중
    low = built | {"floorSpace": 300 * SQM_PER_PYEONG}       # 저층 근생은 새 건물이어도 후보
    assert apply_show_filter(compute_dev_metrics(low, A, "hotel"), A)["isShown"] is True
    old = built | {"approvalElapsedYear": 40}                 # 40년차면 58%여도 후보
    assert apply_show_filter(compute_dev_metrics(old, A, "hotel"), A)["isShown"] is True


# 좌표: 종로3가역 옆(낙원동) / 동묘앞 북쪽(숭인동) / 장안동 / 여의도 건너 대방동
NAKWON = {"latitude": 37.5722, "longitude": 126.9905}
SUNGIN = {"latitude": 37.5760, "longitude": 127.0160}
JANGAN = {"latitude": 37.5700, "longitude": 127.0680}
DAEBANG = {"latitude": 37.5125, "longitude": 126.9270}


def test_hotel_adr_drops_one_tier_outside_demand_hubs():
    hub = compute_dev_metrics(site(300, 600, "일반상업지역", gu="종로구") | NAKWON, A, "hotel")
    off = compute_dev_metrics(site(300, 600, "일반상업지역", gu="동대문구") | JANGAN, A, "hotel")
    assert hub["hotelHub"] == "종로3가" and hub["adrTier"] == 1
    assert hub["adr10k"] == pytest.approx(A.grade_3.adr_10k)
    # 동대문구는 Tier 3(80%)인데 숙박 거점 밖이라 70%
    assert off["hotelHub"] is None and off["hotelHubDistanceM"] > A.hotel_hub_radius_m
    assert off["adrMultiplier"] == pytest.approx(0.70) and off["adrTier"] == 4
    assert off["adr10k"] == pytest.approx(A.grade_3.adr_10k * 0.70)


def test_hotel_room_count_uses_realistic_gross_area_per_room():
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "hotel")
    gross_sqm_per_room = m["devTotalPyeong"] * SQM_PER_PYEONG / m["devRoomCount"]
    assert 33 < gross_sqm_per_room < 40          # 3성급: 객실당 연면적 약 35㎡


def test_office_market_needs_core_station_in_the_right_district():
    core = compute_dev_metrics(site(300, 600, "일반상업지역", gu="종로구") | NAKWON, A, "office")
    fringe = compute_dev_metrics(site(300, 600, "일반상업지역", gu="종로구") | SUNGIN, A, "office")
    assert core["officeMarket"] == "CBD" and core["officeCore"] == "종로3가"
    assert fringe["officeMarket"] == "기타" and fringe["officeCore"] is None
    assert fringe["officeNoc10k"] == A.office.markets["기타"].noc_10k
    # 여의도 건너편(동작구)은 가까워도 YBD가 아니고, 여의도동은 좌표와 무관하게 YBD
    across = compute_dev_metrics(site(300, 600, "일반상업지역", gu="동작구") | DAEBANG, A, "office")
    yeouido = compute_dev_metrics(
        site(300, 600, "일반상업지역", gu="영등포구") | DAEBANG | {"sectorName": "여의도동"}, A, "office")
    assert across["officeMarket"] == "기타"
    assert yeouido["officeMarket"] == "YBD"


def test_generic_commercial_zoning_uses_core_far_inside_the_wall():
    inside = site(300, 600, "상업지역") | {"latitude": 37.5636, "longitude": 126.9826}   # 명동
    assert compute_dev_metrics(inside, A, "hotel")["maxFar"] == 600


def test_existing_floor_area_falls_back_to_registry_ratio():
    # 매물에는 연면적 300평만 적혀 있지만 건축물대장 용적률 500% → 지상만 1,500평인 8년차 건물
    src = site(300, 600, "일반상업지역") | {
        "floorSpace": 300 * SQM_PER_PYEONG, "regFloorAreaRatio": 500, "approvalElapsedYear": 8}
    m = apply_show_filter(compute_dev_metrics(src, A, "hotel"), A)
    assert m["isShown"] is False and "철거 실익" in m["shownReason"]
    # 준공연도를 모르면 새 건물로 단정하지 않는다
    unknown_age = src | {"approvalElapsedYear": None}
    assert apply_show_filter(compute_dev_metrics(unknown_age, A, "hotel"), A)["isShown"] is True


def test_rail_already_opened_is_not_future():
    assert rail_opened("2024.12", "2026-09-29")
    assert not rail_opened("2027-11", "2026-09-29")
    assert not rail_opened("2026", "2026-09-29")       # 연도만 있으면 연말로 본다
    assert not rail_opened("", "2026-09-29") and not rail_opened(None, "2026-09-29")


def test_listing_without_coordinates_gets_no_location_premium():
    # 좌표가 없으면 반경을 확인할 수 없다 → 오피스는 '기타', 호텔은 거점 밖
    m = compute_dev_metrics(site(300, 600, "일반상업지역", gu="중구"), A, "best")
    assert m["officeMarket"] == "기타"
    assert m["hotelHub"] is None and m["adrMultiplier"] == pytest.approx(0.90)


def test_wall_boundary_bulges_west_at_seosomun():
    from naver_crawler.transforms import is_in_historic_core
    assert is_in_historic_core(37.56197, 126.97353)      # 서소문동 세종대로11길 — 도성 안
    assert not is_in_historic_core(37.5600, 126.9690)    # 순화동 쪽 — 도성 밖
