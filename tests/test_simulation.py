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
    m = compute_dev_metrics(site(300, 600, "일반상업지역"), A, "office")
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
