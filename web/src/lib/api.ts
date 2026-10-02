/**
 * FastAPI 백엔드 클라이언트.
 * 모든 fetch는 NEXT_PUBLIC_API_URL 기준.
 */
import type { DevUse } from "@/lib/dev-class";

// NEXT_PUBLIC_API_URL 비어있으면 same-origin (next.js rewrites가 /api/* 를
// backend로 proxy). Vercel에서는 vercel.json의 services 라우팅이 담당.
const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export interface Article {
  articleNo: string;
  name?: string | null;
  isCombinedDevelopment?: boolean;
  partOfGroup?: string | null;
  groupSize?: number | null;
  groupMembersDetail?: Record<string, unknown>[] | null;
  groupMemberArticles?: string | null;            // "aid1,aid2,..." comma list

  // 위치
  latitude?: number | null;
  longitude?: number | null;
  divisionName?: string | null;
  sectorName?: string | null;
  regRoadAddress?: string | null;

  // 가격/면적
  dealPrice?: number | null;        // 만원
  landSpace?: number | null;        // ㎡
  landPyeong?: number | null;       // 평
  landPerPyeongM?: number | null;   // 백만/평
  dealPriceMissing?: boolean | null;  // raw에 가격 결측 (0과 구분)
  landSpaceMissing?: boolean | null;  // raw에 대지면적 결측

  // 용도 / 현재 건물 현황
  regZoning?: string | null;
  maxFar?: number | null;
  regBuildingUse?: string | null;
  regStructure?: string | null;
  regBuildingCoverageRatio?: number | null;
  regFloorAreaRatio?: number | null;
  regElevatorCount?: number | null;
  regTotalParkingCount?: number | null;
  regHouseholdNumber?: number | null;
  regUseApprovalDate?: number | string | null;     // YYYYMMDD
  approvalDateRaw?: number | string | null;
  approvalElapsedYear?: number | null;
  floorInfo?: string | null;                        // "-1/5" 형태
  groundTotalFloor?: number | null;
  undergroundTotalFloor?: number | null;
  floorSpace?: number | null;                       // 현재 건물 연면적 ㎡
  totalPyeong?: number | null;                      // 현재 건물 연면적 평
  exclusiveSpace?: number | null;
  supplySpace?: number | null;

  // 시뮬 — 선택된 용도(devUse) 기준 공통 필드
  devUse?: "hotel" | "office" | null;
  devClass?: string | null;           // 호텔 등급 또는 오피스 규모 구분
  devZoneOk?: boolean | null;         // 호텔/오피스 신축 가능 용도지역
  inHistoricCore?: boolean | null;    // 한양도성 안 — 역사도심 조례 용적률
  capRate?: number | null;            // 취득 Cap = 안정화 NOI / 총사업비
  noiAnnualM?: number | null;
  hotelCapRate?: number | null;
  officeCapRate?: number | null;

  // 오피스
  officeClass?: string | null;
  officeMarket?: string | null;       // CBD / GBD / YBD / 기타
  officeCore?: string | null;         // 권역 핵심 역 (반경 안일 때만)
  officeCoreDistanceM?: number | null;
  officeExclusivePyeong?: number | null;
  officeLeasablePyeong?: number | null;
  officeNoc10k?: number | null;       // NOC (만원/전용평/월)
  officeVacancy?: number | null;
  officeOpexAnnualM?: number | null;
  officeExitCap?: number | null;
  officeRevenueAnnualM?: number | null;
  officeNoiAnnualM?: number | null;
  officeCostTotalM?: number | null;

  // 호텔
  hotelGrade?: string | null;
  hotelNoiAnnualM?: number | null;
  hotelCostTotalM?: number | null;
  gopYield?: number | null;
  totalRevenueAnnualM?: number | null;
  devRoomCount?: number | null;
  devTotalPyeong?: number | null;
  devExclusivePyeong?: number | null;
  devRoomAreaSqm?: number | null;
  devExclusiveRate?: number | null;
  adr10k?: number | null;
  adrTier?: number | null;
  adrMultiplier?: number | null;
  hotelHub?: string | null;           // 숙박 수요 거점 역 (반경 안일 때만)
  hotelHubDistanceM?: number | null;
  adrBase10k?: number | null;
  occupancy?: number | null;
  fnbRatio?: number | null;
  gopRatio?: number | null;
  gopAnnualM?: number | null;
  roomRevenueAnnualM?: number | null;
  fnbRevenueAnnualM?: number | null;

  // 비용
  costTotalM?: number | null;
  costPurchaseM?: number | null;
  costConstructionM?: number | null;
  costIncidentalM?: number | null;
  costFinanceM?: number | null;
  costPerRoomM?: number | null;
  costPerPyeongM?: number | null;

  // 도시계획
  devJiguPrimaryName?: string | null;
  devJiguPrimaryType?: string | null;
  devJiguPrimaryStep?: string | null;
  devNearestRailStation?: string | null;
  devNearestRailLine?: string | null;
  devNearestRailDistanceM?: number | null;
  devNearestRailWalkMin?: number | null;
  devNearestRailOpenDate?: string | null;

  // 기타
  parcelPolygon?: Record<string, unknown> | null;

  // 주간 변동 (snapshot diff)
  isNew?: boolean | null;
  prevDealPrice?: number | null;
  priceChangePct?: number | null;

  // 데이터 점검 표시 ("price_low" / "cap_high" / "zone_unfit" / "zone_conflict" / "area_mismatch")
  outlierFlags?: string[] | null;
}

export interface ArticleList {
  count: number;
  articles: Article[];
}

/** DCF 가정값 — POST body. 모두 optional. None이면 등급/Tier 기반 default. */
export interface FeasibilityAssumptions {
  construction_years?: number;
  hold_years?: number;
  ramp_up?: number[];
  exit_cap?: number;
  discount_rate?: number;
  dev_discount_rate?: number;
  ltv?: number;
  loan_rate?: number;
  selling_cost_rate?: number;
  inflation?: number;
  mgmt_fee_base?: number;
  mgmt_fee_incentive?: number;
  property_tax_rate?: number;
  ff_e_reserve?: number;
  vehicle_cost_rate?: number;
  pip_cycle_years?: number;
  pip_cost_per_room_M?: number;
}

/** DCF 결과. */
export interface FeasibilityResponse {
  irr_unlevered: number | null;
  irr_levered: number | null;
  npv_M: number | null;
  npv_dev_M: number | null;
  payback_year: number | null;
  yoc_year3: number | null;
  exit_value_M: number | null;
  entry_cap: number | null;
  exit_cap_used: number | null;
  noi_to_gop: number | null;
  construction_years_used: number | null;
  cash_flows_M: number[];
  cash_flows_equity_M: number[];
  notes: string[];
}

export async function fetchFeasibility(
  aid: string,
  assumptions: FeasibilityAssumptions,
  use: DevUse,
  sim: Record<string, unknown> | null,
): Promise<FeasibilityResponse> {
  const res = await fetch(`${API}/api/articles/${aid}/feasibility`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...assumptions, use, sim }),
    cache: "no-store",
  });
  if (!res.ok) {
    // FastAPI HTTPException → {detail: "..."} — 422 등 메시지 노출용
    let detail = `사업성 계산 실패 (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch { /* non-JSON */ }
    throw new Error(detail);
  }
  return (await res.json()) as FeasibilityResponse;
}

export interface MetaOptions {
  gu: string[];
  grades: string[];
  zonings: string[];
  price_max_M: number;
  land_max_pyeong: number;
  total_articles: number;
  data_as_of: string | null;
  prev_snapshot_date: string | null;
}

export interface FilterParams {
  gu?: string[];
  categories?: string[];
  grades?: string[];
  price_min_M?: number;
  price_max_M?: number;
  land_min?: number;
  land_max?: number;
  cap_min?: number;
  cap_max?: number;
  zonings?: string[];
  only_with_rail?: boolean;
  only_with_jigu?: boolean;
  hotel_zone_only?: boolean;
  outliers_only?: boolean;
}

function buildQuery(params: FilterParams): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => sp.append(k, String(item)));
    } else if (typeof v === "boolean") {
      if (v) sp.append(k, "true");
    } else {
      sp.append(k, String(v));
    }
  }
  return sp.toString();
}

export async function fetchArticles(params: FilterParams, use: DevUse): Promise<ArticleList> {
  const qs = buildQuery({ ...params, use } as FilterParams);
  const url = `${API}/api/articles${qs ? `?${qs}` : ""}`;
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`fetchArticles ${r.status}`);
  return r.json();
}

export async function fetchArticle(id: string, use: DevUse): Promise<Article> {
  const r = await fetch(`${API}/api/articles/${encodeURIComponent(id)}?use=${use}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`fetchArticle ${r.status}`);
  return r.json();
}

export async function fetchMeta(): Promise<MetaOptions> {
  const r = await fetch(`${API}/api/meta/gu-options`);
  if (!r.ok) throw new Error(`fetchMeta ${r.status}`);
  return r.json();
}

export async function fetchGuBoundaries(): Promise<GeoJSON.FeatureCollection> {
  const r = await fetch(`${API}/api/meta/gu-boundaries`);
  if (!r.ok) throw new Error(`fetchGuBoundaries ${r.status}`);
  return r.json();
}

export async function fetchSubwayLines(): Promise<GeoJSON.FeatureCollection> {
  const r = await fetch(`${API}/api/meta/subway-lines`);
  if (!r.ok) throw new Error(`fetchSubwayLines ${r.status}`);
  return r.json();
}

export async function fetchSubwayStations(): Promise<GeoJSON.FeatureCollection> {
  const r = await fetch(`${API}/api/meta/subway-stations`);
  if (!r.ok) throw new Error(`fetchSubwayStations ${r.status}`);
  return r.json();
}

export async function postSimulate(
  assumptions: Record<string, unknown>,
  use: DevUse,
): Promise<ArticleList> {
  const r = await fetch(`${API}/api/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...assumptions, use }),
  });
  if (!r.ok) throw new Error(`postSimulate ${r.status}`);
  return r.json();
}

/** 현재 적용 중인 시뮬 기본 가정값 (config/default.yaml). */
export async function fetchSimDefaults(): Promise<Record<string, unknown>> {
  const r = await fetch(`${API}/api/meta/sim-defaults`);
  if (!r.ok) throw new Error(`fetchSimDefaults ${r.status}`);
  return r.json();
}


// 호텔/오피스 신축 가능 용도지역 keyword — backend transforms.DEV_ZONE_KEYWORDS와 동일.
const HOTEL_ZONE_KEYWORDS = ["상업지역", "준주거지역", "준공업지역", "관광휴양"];

function isHotelZone(zoning: string | null | undefined): boolean {
  // backend normalize_zoning과 동일: 복합표기("준공업지역,노선상업지역")는 첫 토큰 기준
  // (단, 사전에 정의된 복합 키 "준공업지역,노선상업지역"은 첫 토큰도 준공업이라 결과 동일)
  const z = (zoning ?? "").trim().split(",")[0].trim();
  return !!z && HOTEL_ZONE_KEYWORDS.some((kw) => z.includes(kw));
}

/** 그룹멤버 제외 = 실제 후보(단일 + 통합그룹) 수. */
export function countCandidates(articles: Article[]): number {
  return articles.filter((a) => !a.partOfGroup || a.isCombinedDevelopment).length;
}

/**
 * sim 결과를 받은 후 frontend에서 다시 filter 적용. backend filter_articles와
 * 동일 정책: 멤버는 grade/price/land/cap/rail/jigu 등 단독 필터 skip하고,
 * 소속 통합그룹이 통과했을 때만 표시.
 */
export function applyFilterClient(list: ArticleList, f: FilterParams): ArticleList {
  const kept = list.articles.filter((a: Article) => {
    if (f.gu && f.gu.length && !f.gu.includes(a.divisionName ?? "")) return false;
    const isMember = !!a.partOfGroup && !a.isCombinedDevelopment;
    if (f.categories && f.categories.length) {
      const cat = a.isCombinedDevelopment
        ? "통합그룹"
        : a.partOfGroup ? "그룹멤버" : "단일";
      if (!f.categories.includes(cat)) return false;
    }
    if (isMember) {
      // 멤버는 outliers_only만 적용 (backend filter_articles와 동일)
      if (f.outliers_only) {
        const flags = (a.outlierFlags ?? []) as string[];
        if (!flags.length) return false;
      }
      return true;
    }
    if (f.grades && f.grades.length && !f.grades.includes(a.devClass ?? "")) return false;
    const priceM = (a.dealPrice ?? 0) / 100;
    if (f.price_min_M !== undefined && priceM < f.price_min_M) return false;
    if (f.price_max_M !== undefined && priceM > f.price_max_M) return false;
    const land = a.landPyeong ?? 0;
    if (f.land_min !== undefined && land < f.land_min) return false;
    if (f.land_max !== undefined && land > f.land_max) return false;
    if (f.cap_min !== undefined && (a.capRate ?? -1) < f.cap_min) return false;
    if (f.cap_max !== undefined && (a.capRate ?? 999) > f.cap_max) return false;
    if (f.zonings && f.zonings.length && !f.zonings.includes(a.regZoning ?? "")) return false;
    if (f.only_with_rail && !((a.devNearestRailStation ?? "").trim())) return false;
    if (f.only_with_jigu && !((a.devJiguPrimaryName ?? "").trim())) return false;
    if (f.hotel_zone_only && !isHotelZone(a.regZoning)) return false;
    if (f.outliers_only) {
      const flags = (a.outlierFlags ?? []) as string[];
      if (!flags.length) return false;
    }
    return true;
  });
  const visibleGroups = new Set(
    kept.filter((a) => a.isCombinedDevelopment).map((a) => a.articleNo),
  );
  const groupsHidden = !!f.categories?.length && !f.categories.includes("통합그룹");
  const out = kept.filter(
    (a) =>
      !a.partOfGroup ||
      a.isCombinedDevelopment ||
      groupsHidden ||
      visibleGroups.has(a.partOfGroup),
  );
  return { count: out.length, articles: out };
}
