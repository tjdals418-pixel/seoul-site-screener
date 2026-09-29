"""API request/response schemas (Pydantic)."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class Article(BaseModel):
    """매물 (단일 / 통합그룹 / 그룹멤버). 모든 필드 optional — 데이터 결측 허용."""
    # 식별
    articleNo: str
    name: str | None = None

    # 카테고리
    isCombinedDevelopment: bool = False
    partOfGroup: str | None = None
    groupSize: int | None = None
    groupMemberArticles: str | None = None

    # 위치
    latitude: float | None = None
    longitude: float | None = None
    divisionName: str | None = None
    sectorName: str | None = None
    regRoadAddress: str | None = None

    # 가격 / 면적 (만원 / ㎡ / 평)
    dealPrice: float | None = None
    landSpace: float | None = None
    landPyeong: float | None = None
    floorSpace: float | None = None
    totalPyeong: float | None = None
    landPerPyeongM: float | None = None  # 백만원/평
    exclusiveSpace: float | None = None  # 전용면적 ㎡
    supplySpace: float | None = None      # 공급면적 ㎡
    dealPriceMissing: bool | None = None  # raw에 가격정보 결측
    landSpaceMissing: bool | None = None  # raw에 대지면적 결측

    # 용도지역
    regZoning: str | None = None
    maxFar: float | None = None
    regFloorAreaRatio: float | None = None     # 현재 용적률 (raw 건축물대장)
    regBuildingCoverageRatio: float | None = None

    # 시뮬 결과 — 선택된 용도(devUse) 기준 공통 필드
    devUse: str | None = None             # "hotel" | "office"
    devClass: str | None = None           # 호텔 등급 또는 오피스 규모 구분
    devZoneOk: bool | None = None         # 호텔/오피스 신축 가능 용도지역
    inHistoricCore: bool | None = None    # 한양도성 안 — 역사도심 조례 용적률 적용
    hotelCapRate: float | None = None
    officeCapRate: float | None = None
    exitCap: float | None = None          # 매각 Cap Rate (DCF 가정)

    # 오피스
    officeClass: str | None = None
    officeMarket: str | None = None       # CBD / GBD / YBD / 기타
    officeExclusivePyeong: float | None = None
    officeLeasablePyeong: float | None = None
    officeNoc10k: float | None = None     # NOC (만원/전용평/월)
    officeVacancy: float | None = None
    officeOpexAnnualM: float | None = None
    officeExitCap: float | None = None
    officeRevenueAnnualM: float | None = None
    officeNoiAnnualM: float | None = None
    officeCostTotalM: float | None = None

    # 호텔
    hotelGrade: str | None = None
    hotelNoiAnnualM: float | None = None
    hotelCostTotalM: float | None = None
    devTotalPyeong: float | None = None
    devRoomCount: int | None = None
    devRoomAreaSqm: float | None = None
    devExclusivePyeong: float | None = None
    devExclusiveRate: float | None = None
    capRate: float | None = None          # 안정화 NOI / 총개발비
    gopYield: float | None = None         # GOP / 총개발비 (참고)
    noiAnnualM: float | None = None
    totalRevenueAnnualM: float | None = None
    adr10k: float | None = None
    adrTier: int | None = None
    adrMultiplier: float | None = None
    adrBase10k: float | None = None
    occupancy: float | None = None
    fnbRatio: float | None = None
    gopRatio: float | None = None
    gopAnnualM: float | None = None
    roomRevenueAnnualM: float | None = None
    fnbRevenueAnnualM: float | None = None

    # 비용 (백만원)
    costTotalM: float | None = None
    costPurchaseM: float | None = None
    costConstructionM: float | None = None
    costIncidentalM: float | None = None
    costFinanceM: float | None = None
    costPerRoomM: float | None = None
    costPerPyeongM: float | None = None

    # 도시계획 / 미래 호재
    devJiguPrimaryName: str | None = None
    devJiguPrimaryType: str | None = None
    devJiguPrimaryStep: str | None = None
    devNearestRailStation: str | None = None
    devNearestRailLine: str | None = None
    devNearestRailDistanceM: float | None = None
    devNearestRailWalkMin: float | None = None
    devNearestRailOpenDate: str | None = None

    # 현재 건물 (단일 매물)
    regUseApprovalDate: str | None = None
    approvalDateRaw: int | str | None = None    # YYYYMMDD 원본
    regStructure: str | None = None
    regBuildingUse: str | None = None
    regTotalParkingCount: int | None = None
    regElevatorCount: int | None = None
    regHouseholdNumber: int | None = None
    approvalElapsedYear: int | None = None

    # 층수
    floorInfo: str | None = None
    groundTotalFloor: int | None = None
    undergroundTotalFloor: int | None = None

    # 식별 (외부 링크용 PNU)
    pnu: str | None = None

    # geo
    parcelPolygon: dict | None = None
    groupMembersDetail: list[dict] | None = None

    # 주간 변동 추적 (snapshot diff)
    isNew: bool | None = None
    prevDealPrice: float | None = None
    priceChangePct: float | None = None

    # 데이터 outlier 마킹 (분위수 기반)
    outlierFlags: list[str] | None = None

    # 선언되지 않은 필드는 응답에서 제외 (원본 데이터의 불필요/민감 필드 차단)
    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _empty_str_to_none(cls, data: Any) -> Any:
        """빈 문자열을 None으로 — fin.land 데이터에 ""가 자주 들어옴."""
        if isinstance(data, dict):
            return {k: (None if v == "" else v) for k, v in data.items()}
        return data


class ArticleList(BaseModel):
    """필터된 매물 list 응답."""
    count: int
    articles: list[Article]


class FilterParams(BaseModel):
    """필터링 파라미터 (query string으로 받음)."""
    gu: list[str] = Field(default_factory=list)         # 자치구
    categories: list[str] = Field(default_factory=list)  # 단일/통합그룹/그룹멤버
    grades: list[str] = Field(default_factory=list)     # 3성급/4성급/5성급
    price_min_M: float | None = None                    # 매매가 min (백만원)
    price_max_M: float | None = None
    land_min: float | None = None                       # 대지 min (평)
    land_max: float | None = None
    cap_min: float | None = None                        # Cap Rate min (0~1)
    cap_max: float | None = None
    zonings: list[str] = Field(default_factory=list)
    only_with_rail: bool = False
    only_with_jigu: bool = False
    hotel_zone_only: bool = False
    outliers_only: bool = False


class FeasibilityAssumptionsModel(BaseModel):
    """DCF 가정값 — POST /api/articles/{id}/feasibility 요청 body. 모두 optional.

    construction_years / ramp_up / exit_cap이 None이면 용도·입지 기본값으로 해소.
    범위 밖 값은 422 (공개 서버에서 비정상 입력으로 인한 오류·과부하 방지).
    """
    construction_years: int | None = Field(None, ge=1, le=6)
    hold_years: int | None = Field(None, ge=2, le=30)
    ramp_up: list[Annotated[float, Field(ge=0, le=1.5)]] | None = Field(None, max_length=10)
    exit_cap: float | None = Field(None, gt=0.01, le=0.2)
    discount_rate: float | None = Field(None, ge=0, le=0.5)
    dev_discount_rate: float | None = Field(None, ge=0, le=0.5)
    ltv: float | None = Field(None, ge=0, le=0.95)
    loan_rate: float | None = Field(None, ge=0, le=0.3)
    selling_cost_rate: float | None = Field(None, ge=0, le=0.2)
    inflation: float | None = Field(None, ge=-0.1, le=0.2)
    mgmt_fee_base: float | None = Field(None, ge=0, le=0.2)
    mgmt_fee_incentive: float | None = Field(None, ge=0, le=0.5)
    property_tax_rate: float | None = Field(None, ge=0, le=0.05)
    ff_e_reserve: float | None = Field(None, ge=0, le=0.2)
    vehicle_cost_rate: float | None = Field(None, ge=0, le=0.05)
    pip_cycle_years: int | None = Field(None, ge=1, le=30)
    pip_cost_per_room_M: float | None = Field(None, ge=0, le=500)
    # 사용자가 적용한 시뮬 가정값·용도 — 있으면 그 기준으로 재계산된 매물로 DCF
    sim: "SimAssumptions | None" = None
    use: Literal["hotel", "office", "best"] | None = None


class FeasibilityResponse(BaseModel):
    """DCF 결과."""
    irr_unlevered: float | None
    irr_levered: float | None
    npv_M: float | None
    npv_dev_M: float | None
    payback_year: float | None
    yoc_year3: float | None
    exit_value_M: float | None
    entry_cap: float | None
    exit_cap_used: float | None
    noi_to_gop: float | None
    construction_years_used: int | None
    cash_flows_M: list[float]
    cash_flows_equity_M: list[float]
    notes: list[str]


class GradeProfileModel(BaseModel):
    """호텔 등급별 가정값 (일부만 보내면 나머지는 기본값)."""
    model_config = {"extra": "ignore"}
    exclusive_ratio: float | None = Field(None, gt=0, le=1)
    room_area_sqm: float | None = Field(None, ge=5, le=200)
    adr_10k: float | None = Field(None, gt=0, le=500)
    occupancy: float | None = Field(None, gt=0, le=1)
    fnb_ratio: float | None = Field(None, ge=0, le=2)
    gop_ratio: float | None = Field(None, gt=0, le=1)
    construction_cost_per_pyeong_M: float | None = Field(None, gt=0, le=100)


class OfficeMarketModel(BaseModel):
    model_config = {"extra": "ignore"}
    noc_10k: float | None = Field(None, gt=0, le=100)
    vacancy: float | None = Field(None, ge=0, lt=1)
    exit_cap: float | None = Field(None, gt=0.01, le=0.2)


class OfficeProfileModel(BaseModel):
    model_config = {"extra": "ignore"}
    min_total_pyeong: float | None = Field(None, ge=0, le=100_000)
    exclusive_ratio: float | None = Field(None, gt=0, le=1)
    opex_10k_per_pyeong: float | None = Field(None, ge=0, le=50)
    construction_cost_per_pyeong_M: float | None = Field(None, gt=0, le=100)
    large_min_pyeong: float | None = Field(None, gt=0)
    mid_large_min_pyeong: float | None = Field(None, gt=0)
    mid_min_pyeong: float | None = Field(None, gt=0)
    markets: dict[Literal["CBD", "GBD", "YBD", "기타"], OfficeMarketModel] | None = None


class SimAssumptions(BaseModel):
    """시뮬 가정값 — DevAssumptions의 부분 override. 모든 필드 optional, 범위 밖은 422."""
    model_config = {"extra": "ignore"}
    # 개발 용도 — hotel / office / best(최유효이용). 캐시 키 계산 시 분리됨.
    use: Literal["hotel", "office", "best"] | None = None
    sqm_to_pyeong: float | None = Field(None, gt=0.2, lt=0.4)
    basement_ratio: float | None = Field(None, ge=0, le=5)
    incidental_rate: float | None = Field(None, ge=0, le=0.5)
    ltv: float | None = Field(None, ge=0, le=0.95)
    interest_rate: float | None = Field(None, ge=0, le=0.3)
    loan_years: int | None = Field(None, ge=0, le=10)

    grade_3_min_pyeong: float | None = Field(None, ge=0, le=100_000)
    grade_4_min_pyeong: float | None = Field(None, ge=0, le=100_000)
    grade_5_min_pyeong: float | None = Field(None, ge=0, le=100_000)

    max_land_pyeong: float | None = Field(None, gt=0, le=1_000_000)
    min_land_per_pyeong_M: float | None = Field(None, ge=0)
    max_land_per_pyeong_M: float | None = Field(None, gt=0)
    min_bldg_per_pyeong_M: float | None = Field(None, ge=0)

    # GOP → NOI 차감률
    mgmt_fee_base: float | None = Field(None, ge=0, le=0.2)
    mgmt_fee_incentive: float | None = Field(None, ge=0, le=0.5)
    property_tax_rate: float | None = Field(None, ge=0, le=0.05)
    ff_e_reserve: float | None = Field(None, ge=0, le=0.2)

    grade_3: GradeProfileModel | None = None
    grade_4: GradeProfileModel | None = None
    grade_5: GradeProfileModel | None = None
    office: OfficeProfileModel | None = None

    @model_validator(mode="after")
    def _thresholds_ascending(self) -> "SimAssumptions":
        g = [self.grade_3_min_pyeong, self.grade_4_min_pyeong, self.grade_5_min_pyeong]
        given = [x for x in g if x is not None]
        if given != sorted(given):
            raise ValueError("등급 기준 연면적은 3성 < 4성 < 5성 순이어야 합니다.")
        if self.office:
            o = [self.office.mid_min_pyeong, self.office.mid_large_min_pyeong, self.office.large_min_pyeong]
            given = [x for x in o if x is not None]
            if given != sorted(given):
                raise ValueError("오피스 규모 기준은 중형 < 중대형 < 대형 순이어야 합니다.")
        return self


FeasibilityAssumptionsModel.model_rebuild()
