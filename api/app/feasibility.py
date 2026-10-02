"""호텔 개발 사업성 — 정식 DCF 모델 (IRR / NPV / Payback).

Cap Rate 단일 지표는 "1년차 stabilized 운영"을 가정하는데, 실제 호텔 개발은
공사 24~42개월 + 운영 ramp-up 2~5년 + Exit 매각이라는 시간 축이 있다.
이 모듈은 그 시간 축을 cash flow로 풀어서 IRR / NPV / Payback을 계산한다.

⚠️ 중요: 이 모듈은 시뮬 기본가정(GOP 마진 / ADR / 공사비)을 건드리지 않는다.
costTotalM / gopAnnualM 등 transforms.py가 산출한 값을 입력으로 받아 그 위에
재무 모델만 얹는다. GOP→NOI 차감률의 기본값은 DevAssumptions(= 헤드라인
Cap Rate 계산)와 같은 값을 쓰므로, override가 없으면 안정화 NOI가
article의 noiAnnualM과 일치한다.

기본 시나리오:
  - 보유 5년 = 공사 2년 + 안정화 3년 (build-stabilize-sell). 모두 override 가능.
  - NOI = GOP − 운영사 fee − 재산세·보험 − FF&E reserve (NOI/GOP ≈ 0.73).
  - Vehicle(SPC/펀드) 운용비: 총사업비 60bp/년 영업외 비용 (현금흐름에서만 차감).
  - exit_cap 입지 Tier 차등 (prime일수록 낮은 cap).
  - loan_rate 5.5% (LTV 60% 기준, 조정 가능).
  - Unlevered CF는 금융비(건설이자)를 제외, Levered CF는 PF draw + 이자 반영.
  - 토지 = equity, PF는 공사단계 draw down (Y0 토지매입 시 부채 0).
  - Exit value = 매각 다음 해(buyer 첫 해) NOI / exit cap — ramp-up 반영.
  - PIP(대수선): 운영 8년차 1회 — 5년 base에선 미발생, hold 늘리면 적용.

산출:
  irr_unlevered / irr_levered : 전체 사업 / 자본금 기준 IRR
  npv_M (= npv_core_M)        : NPV @ discount_rate (코어 8%)
  npv_dev_M                   : NPV @ dev_discount_rate (개발 risk 12%)
  payback_year                : 누적 cash flow 양 전환 시점
  yoc_year3                   : Yield on Cost = 안정화 NOI / 총개발비
  entry_cap / exit_cap_used   : cap rate compression/expansion 가시화
"""
from __future__ import annotations

from dataclasses import dataclass

from naver_crawler.transforms import DevAssumptions

_DEV_DEFAULTS = DevAssumptions()


# ── 도메인 default ───────────────────────────────────────────────────────
# 기본 시나리오: 공사 2년 + 안정화(운영) 3년 = 보유 5년 base.
# merchant build-stabilize-sell — 개발 후 stabilization 직후 매각 패턴.
_DEFAULT_RAMP = (0.70, 0.85, 1.00)     # 호텔 운영 1·2·3년차 (3년 안정화)
_DEFAULT_OFFICE_RAMP = (0.60, 0.90, 1.00)  # 오피스 임대 lease-up (준공 후 3년)
_DEFAULT_CY = 2                         # 공사 2년

# Exit Cap 기본값은 article의 exitCap (호텔: 입지 보정 후 ADR Tier별, 오피스: 권역별 —
# transforms.select_use가 채움). 없을 때만 fallback.
_FALLBACK_EXIT_CAP = 0.060


@dataclass
class FeasibilityAssumptions:
    """DCF 가정값. 모두 사용자 override 가능 (DetailPanel 슬라이더).

    construction_years / ramp_up / exit_cap이 None이면 base/Tier로 자동 해소.
    """
    # None → base/Tier 자동 해소
    construction_years: int | None = None  # None → 공사 2년 base
    ramp_up: tuple[float, ...] | None = None  # None → (70/85/100) 3년 안정화
    exit_cap: float | None = None          # None → 입지 Tier별 exit cap

    hold_years: int = 5                    # 보유 기간 (공사 2 + 안정화 3 = 5 base)
    discount_rate: float = 0.08            # NPV 할인율 (코어 Equity 요구수익률)
    dev_discount_rate: float = 0.12        # 개발 risk-adjusted 할인율
    ltv: float = 0.60                      # 대출 비율 (총개발비 대비 sizing)
    loan_rate: float = 0.055               # LTV 60% 기준 현 금리 (사용자 조정 가능)
    selling_cost_rate: float = 0.02        # Exit 시 매각 수수료
    inflation: float = 0.02                # ADR / OCC 연간 성장 (보수적)

    # NOI = GOP - (운영사 fee + 재산세 + FF&E reserve) — 기본값은 DevAssumptions와 공유
    mgmt_fee_base: float = _DEV_DEFAULTS.mgmt_fee_base            # 총매출 대비
    mgmt_fee_incentive: float = _DEV_DEFAULTS.mgmt_fee_incentive  # GOP 대비
    property_tax_rate: float = _DEV_DEFAULTS.property_tax_rate    # 총개발비 대비
    ff_e_reserve: float = _DEV_DEFAULTS.ff_e_reserve              # 총매출 대비

    # Vehicle(SPC/펀드 비히클) 운용비 — 영업외 비용. 총사업비의 60bp/년.
    # NOI가 아닌 fund-level 비용이라 exit 가치산정엔 제외, 현금흐름에서만 차감.
    vehicle_cost_rate: float = 0.006       # 60bp/년 (총개발비 대비)

    # PIP (Property Improvement Plan / 대수선) — hold 중 1회 lump-sum
    pip_cycle_years: int = 8               # 운영 N년차에 PIP (5년 base면 미발생)
    pip_cost_per_room_M: float = 35.0      # 객실당 (백만원) — 5성 3000~5000만


@dataclass
class FeasibilityResult:
    irr_unlevered: float | None
    irr_levered: float | None
    npv_M: float | None                    # = npv_core_M (back-compat)
    npv_dev_M: float | None                # @ dev_discount_rate
    payback_year: float | None
    yoc_year3: float | None
    exit_value_M: float | None
    entry_cap: float | None                # 시뮬 Cap Rate (entry)
    exit_cap_used: float | None            # 실제 적용된 exit cap
    noi_to_gop: float | None               # stabilized NOI/GOP (검증용)
    construction_years_used: int | None
    cash_flows_M: list[float]              # 연도별 unlevered (백만원)
    cash_flows_equity_M: list[float]       # 연도별 levered (지분 cash flow)
    notes: list[str]


def _irr(cash_flows: list[float]) -> float | None:
    """numpy-financial IRR. 수렴 실패 시 None."""
    try:
        import numpy_financial as npf
        v = npf.irr(cash_flows)
        if v is None or v != v:  # NaN check
            return None
        return float(v)
    except Exception:
        return None


def _npv(rate: float, cash_flows: list[float]) -> float:
    """수동 NPV — numpy-financial 의존 회피."""
    return sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))


def _payback(cash_flows: list[float]) -> float | None:
    """첫 누적 양 전환 시점 (선형 보간). 전환 안 되면 None."""
    cum = 0.0
    for i, cf in enumerate(cash_flows):
        prev = cum
        cum += cf
        if prev < 0 <= cum:
            frac = (-prev) / cf if cf else 0.0
            return i - 1 + frac
    return None


def _resolve_assumptions(
    a: FeasibilityAssumptions, article: dict
) -> tuple[int, tuple[float, ...], float]:
    """None인 필드를 base/Tier default로 해소.

    - construction_years: None → 2년 (base)
    - ramp_up: None → (70/85/100) 3년 안정화 (base)
    - exit_cap: None → 입지 Tier별 (prime일수록 낮음)
    Returns (construction_years, ramp_up, exit_cap).
    """
    is_office = article.get("devUse") == "office"
    cy = a.construction_years if a.construction_years is not None else _DEFAULT_CY
    default_ramp = _DEFAULT_OFFICE_RAMP if is_office else _DEFAULT_RAMP
    ramp = a.ramp_up if a.ramp_up is not None else default_ramp

    if a.exit_cap is not None:
        exit_cap = a.exit_cap
    else:
        exit_cap = article.get("exitCap") or _FALLBACK_EXIT_CAP

    return cy, ramp, exit_cap


def compute_feasibility(
    article: dict,
    assumptions: FeasibilityAssumptions | None = None,
) -> FeasibilityResult | None:
    """단일 article (단일/통합)의 DCF. devUse(hotel/office)에 따라 NOI 경로 분기.

    - 호텔: GOP → NOI 변환 (운영사 fee / FF&E / 재산세)
    - 오피스: article의 안정화 NOI(임대수입 − 운용비용, 재산세는 운용비에 포함)를 lease-up
      비율로 스케일, PIP 없음

    Returns None if article에 필수 시뮬값(`costTotalM`, NOI/GOP) 없을 때.
    """
    a = assumptions or FeasibilityAssumptions()
    notes: list[str] = []
    is_office = article.get("devUse") == "office"

    cost_total = article.get("costTotalM")
    gop_stab = article.get("gopAnnualM")           # stabilized 단년 GOP (백만원)
    office_noi_stab = article.get("noiAnnualM") if is_office else None
    cost_purchase = article.get("costPurchaseM") or 0
    cost_construction = article.get("costConstructionM") or 0
    cost_incidental = article.get("costIncidentalM") or 0
    cost_finance = article.get("costFinanceM") or 0
    n_rooms = article.get("devRoomCount") or 0

    if not cost_total or not (office_noi_stab if is_office else gop_stab):
        return None

    # stabilized 총매출 — NOI 차감 항목(fee/reserve) 계산에 필요
    rev_stab = article.get("totalRevenueAnnualM")
    if not rev_stab:
        rev_stab = (article.get("roomRevenueAnnualM") or 0) + (article.get("fnbRevenueAnnualM") or 0)
    if not rev_stab:
        # 최후 fallback — gop_ratio 역산 불가 시 GOP의 2.5배 가정
        rev_stab = (gop_stab or 0) * 2.5

    cy, ramp_up, exit_cap = _resolve_assumptions(a, article)
    op_years = a.hold_years - cy
    if op_years < 1:
        notes.append(f"hold_years({a.hold_years}) ≤ construction_years({cy}) — 운영 없음")
        return None

    # ── 1. NOI 변환 함수 (GOP → NOI) ───────────────────────────────
    # NOI = GOP - 운영사 base fee(총매출%) - incentive(GOP%) - 재산세 - FF&E
    prop_tax_annual = cost_total * a.property_tax_rate   # 자산가치 proxy = 총개발비

    def gop_to_noi(gop_y: float, rev_y: float) -> float:
        base_fee = rev_y * a.mgmt_fee_base
        incentive_fee = gop_y * a.mgmt_fee_incentive
        ffe = rev_y * a.ff_e_reserve
        return gop_y - base_fee - incentive_fee - ffe - prop_tax_annual

    # 오피스: 임대수입은 임대율(ramp)만큼, 운용비용은 공실과 무관하게 전액 발생
    office_rev = article.get("officeRevenueAnnualM") or 0
    office_opex = article.get("officeOpexAnnualM") or 0

    def stab_noi(ratio: float, infl: float) -> float:
        if is_office:
            return (office_rev * ratio - office_opex) * infl
        return gop_to_noi(gop_stab * ratio * infl, rev_stab * ratio * infl)

    noi_to_gop_stab = (
        None if is_office or not gop_stab
        else gop_to_noi(gop_stab, rev_stab) / gop_stab
    )

    # ── 2. 공사 기간 Capex 분배 ────────────────────────────────────
    # Year 0: 토지 매입 일시 + 비토지 30% 선급 / Year 1~cy-1: 나머지 70% 균등.
    # Unlevered는 금융비(건설이자)를 뺀 순수 사업비, Levered는 금융비 포함.
    def _split(non_land_amt: float) -> tuple[float, float]:
        if cy <= 1:
            return non_land_amt, 0.0
        return non_land_amt * 0.30, (non_land_amt * 0.70) / (cy - 1)

    non_land = cost_construction + cost_incidental + cost_finance
    non_land_y0, capex_per_remaining_year = _split(non_land)
    capex_y0 = cost_purchase + non_land_y0
    unlev_non_land_y0, unlev_capex_per_remaining = _split(cost_construction + cost_incidental)
    unlev_capex_y0 = cost_purchase + unlev_non_land_y0

    # ── 3. 운영기간 NOI 시계열 (op_years + 1: 마지막은 buyer 첫 해) ─────
    def noi_at(op_idx: int) -> float:
        ratio = ramp_up[op_idx] if op_idx < len(ramp_up) else 1.0
        years_since_stab = max(0, op_idx - len(ramp_up) + 1)
        infl = (1 + a.inflation) ** years_since_stab
        return stab_noi(ratio, infl)

    operating_noi: list[float] = [noi_at(i) for i in range(op_years)]

    # ── 4. Exit value — forward NOI(buyer 첫 해, ramp 반영) / exit_cap ────
    forward_noi = noi_at(op_years)
    exit_gross = forward_noi / exit_cap if exit_cap > 0 else 0
    exit_net = exit_gross * (1 - a.selling_cost_rate)

    # ── 5. PIP capex (운영 pip_cycle_years 차에 1회) ───────────────
    pip_total = 0.0 if is_office else n_rooms * a.pip_cost_per_room_M
    pip_op_idx = a.pip_cycle_years - 1   # 0-indexed 운영연차

    # ── 6. Unlevered cash flow ─────────────────────────────────────
    cash_flows: list[float] = []
    for y in range(a.hold_years):
        if y == 0:
            cash_flows.append(-unlev_capex_y0)
        elif y < cy:
            cash_flows.append(-unlev_capex_per_remaining)
        else:
            op_idx = y - cy
            cf = operating_noi[op_idx]
            if op_idx == pip_op_idx and pip_total > 0:
                cf -= pip_total
            if y == a.hold_years - 1:
                cf += exit_net
            cash_flows.append(cf)

    # ── 7. Levered cash flow — 토지=equity, PF는 공사단계 draw ──────
    # loan_total = 총개발비 × LTV (sizing). 단 비토지 공사비를 넘지 않음
    # (토지는 통상 equity/bridge). draw는 비토지 공사비 지출 비례.
    loan_total = min(cost_total * a.ltv, non_land) if non_land > 0 else 0.0
    # Y0 PF draw = 비토지 Y0 지출 비율만큼
    pf_draw_y0 = loan_total * (non_land_y0 / non_land) if non_land > 0 else 0.0
    pf_draw_remaining = (loan_total - pf_draw_y0) / (cy - 1) if cy > 1 else 0.0
    annual_interest = loan_total * a.loan_rate

    equity_flows: list[float] = []
    for y in range(a.hold_years):
        if y == 0:
            equity_flows.append(-(capex_y0 - pf_draw_y0))
        elif y < cy:
            equity_flows.append(-(capex_per_remaining_year - pf_draw_remaining))
        else:
            op_idx = y - cy
            cf = operating_noi[op_idx] - annual_interest
            if op_idx == pip_op_idx and pip_total > 0:
                cf -= pip_total
            if y == a.hold_years - 1:
                cf += (exit_net - loan_total)   # 매각 시 대출 일시상환
            equity_flows.append(cf)

    # ── 7.5 Vehicle(SPC/펀드) 운용비 — 영업외 비용 ──────────────────
    # 총사업비의 60bp/년. 비히클이 inception~exit 동안 존재하므로 전 보유기간
    # 매년 차감. NOI/exit 가치산정엔 미반영 (fund-level 비용), 현금흐름에서만.
    vehicle_annual = (cost_total or 0) * a.vehicle_cost_rate
    if vehicle_annual:
        cash_flows = [cf - vehicle_annual for cf in cash_flows]
        equity_flows = [cf - vehicle_annual for cf in equity_flows]

    # ── 8. 지표 ────────────────────────────────────────────────────
    irr_unlev = _irr(cash_flows)
    irr_lev = _irr(equity_flows)
    npv_core = _npv(a.discount_rate, cash_flows)
    npv_dev = _npv(a.dev_discount_rate, cash_flows)
    payback = _payback(cash_flows)
    # YoC = 안정화 NOI / 총개발비 (헤드라인 Cap Rate와 같은 정의)
    yoc = stab_noi(1.0, 1.0) / cost_total if cost_total else None

    if irr_unlev is None:
        notes.append("IRR 수렴 실패 — cash flow 패턴 검토 필요")
    if exit_cap <= 0:
        notes.append("Exit cap rate 0 이하 — Exit value 0 처리됨")
    if pip_op_idx < op_years and pip_total > 0:
        pip_year = cy + pip_op_idx
        notes.append(f"PIP(대수선) {pip_total:,.0f}백만 — 운영 {pip_op_idx+1}년차(프로젝트 Y{pip_year})")
    if is_office:
        notes.append("오피스 NOI = 전용면적 × NOC × 12 − 임대면적 × 운용비 단가 × 12 (lease-up 중 운용비 전액 발생)")
    else:
        notes.append(
            f"NOI/GOP {noi_to_gop_stab:.0%} (운영사 fee+재산세+FF&E 차감 후)"
            if noi_to_gop_stab else "NOI/GOP 계산 불가"
        )
    if not is_office:   # 오피스는 운용비용(3만원/평/월)에 재산세 포함
        notes.append(
            f"재산세+보험 {prop_tax_annual:,.0f}백만/년 (총사업비×{a.property_tax_rate:.2%})"
        )
    if vehicle_annual:
        notes.append(
            f"Vehicle 운용비 {vehicle_annual:,.0f}백만/년 "
            f"(총사업비의 {a.vehicle_cost_rate*10000:.0f}bp, 영업외)"
        )

    return FeasibilityResult(
        irr_unlevered=irr_unlev,
        irr_levered=irr_lev,
        npv_M=npv_core,
        npv_dev_M=npv_dev,
        payback_year=payback,
        yoc_year3=yoc,
        exit_value_M=exit_net,
        entry_cap=article.get("capRate"),
        exit_cap_used=exit_cap,
        noi_to_gop=round(noi_to_gop_stab, 4) if noi_to_gop_stab else None,
        construction_years_used=cy,
        cash_flows_M=cash_flows,
        cash_flows_equity_M=equity_flows,
        notes=notes,
    )
