from __future__ import annotations

"""Pure data transformations for the fin.land pipeline. No I/O, no network."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable


# ── Filter (was old stage 03) ───────────────────────────────────────────
def filter_seoul(
    articles: list[dict],
    *,
    required_si: str,
    excluded_gu: Iterable[str],
) -> list[dict]:
    excluded = set(excluded_gu)
    out = []
    for a in articles:
        addr = a.get("address") or {}
        if addr.get("city") != required_si:
            continue
        if addr.get("division") in excluded:
            continue
        out.append(a)
    return out


def dedupe_by_pnu_min_price(articles: list[dict]) -> list[dict]:
    """같은 PNU 매물 중 매매가 가장 낮은 매물만 남김. PNU 없는 매물은 그대로.

    네이버에 같은 필지 매물이 다른 articleNo로 여러 번 등재되는 경우 (좌표
    미세 차이로 좌표 dedupe 안 잡히는 케이스)에 대응. enrich 후 PNU 채워졌을
    때 호출.
    """
    by_pnu: dict[str, dict] = {}
    no_pnu: list[dict] = []
    for art in articles:
        pnu = art.get("pnu")
        if not pnu:
            no_pnu.append(art)
            continue
        price = art.get("dealPrice") or float("inf")
        cur = by_pnu.get(pnu)
        if cur is None or price < (cur.get("dealPrice") or float("inf")):
            by_pnu[pnu] = art
    return list(by_pnu.values()) + no_pnu


def _approx_distance_m(a: dict, b: dict) -> float:
    dlat = (float(a["latitude"]) - float(b["latitude"])) * 111_000
    dlon = (float(a["longitude"]) - float(b["longitude"])) * 88_000   # 서울 위도 기준
    return (dlat * dlat + dlon * dlon) ** 0.5


def same_building_report(articles: Iterable[dict], max_distance_m: float = 50) -> tuple[set[str], set[str]]:
    """같은 건물 중복 등재 판정 → (지울 매물 articleNo, 용도지역이 엇갈린 채 남긴 매물 articleNo).

    같은 자치구에서 대지면적이 같고(±1%) 좌표가 가까운 매물 가운데 아래 순서로 본다.
      1. 대지·현재 연면적이 모두 1㎡ 안에서 같다 → 같은 건물 (주소가 달라도. 중개사가
         같은 건물을 올렸는데 건축물대장만 옆 필지로 붙은 경우)
      2. 도로명주소가 같다 → 같은 건물
      3. 양쪽 도로명주소가 모두 있고 서로 다르다 → 별개 건물. 면적이 같은 나란한
         "쌍둥이 필지"는 땅값 기준으로 호가까지 같게 나오는 일이 흔하다.
      4. (주소가 한쪽이라도 없을 때) 호가가 같다 / 연면적이 같다 / 호가가 10% 안에서
         비슷하고 준공연차나 층수가 같다 → 같은 건물
    그대로 두면 존재하지 않는 "2필지 합필"이 만들어지거나 같은 건물이 순위에 두 번 나온다.

    남기는 순서: 합필 그룹에 속한 매물 → 신축 가능 용도지역으로 잡힌 매물 → 용적률이
    낮은 쪽 → 호가가 낮은 쪽. 용도지역이 서로 다르게 올라온 건물은 두 번째 반환값에
    담아 "용도지역 확인" 표시를 붙일 수 있게 한다. 통합그룹(가상 매물)은 대상이 아니다.
    """
    by_gu: dict[Any, list[dict]] = {}
    for a in articles:
        if a.get("isCombinedDevelopment"):
            continue
        price, land = a.get("dealPrice"), a.get("landSpace")
        if not price or not land or a.get("latitude") is None or a.get("longitude") is None:
            continue
        by_gu.setdefault(a.get("divisionName"), []).append(a)

    def same_value(a: dict, b: dict, key: str) -> bool:
        va, vb = _num_or_none(a.get(key)), _num_or_none(b.get(key))
        return va is not None and va == vb

    def same_building(a: dict, b: dict) -> bool:
        if _approx_distance_m(a, b) > max_distance_m:
            return False
        fa, fb = _safe_num(a.get("floorSpace")), _safe_num(b.get("floorSpace"))
        if (fa and fb and abs(fa - fb) <= 1.0
                and abs(float(a["landSpace"]) - float(b["landSpace"])) <= 1.0):
            return True
        addr_a, addr_b = a.get("regRoadAddress") or "", b.get("regRoadAddress") or ""
        if addr_a and addr_b:
            return addr_a == addr_b
        pa, pb = float(a["dealPrice"]), float(b["dealPrice"])
        if round(pa) == round(pb) or (fa and fb and round(fa) == round(fb)):
            return True
        return (abs(pa - pb) <= 0.10 * max(pa, pb)
                and (same_value(a, b, "approvalElapsedYear") or same_value(a, b, "groundTotalFloor")))

    dropped: set[str] = set()
    zoning_conflict: set[str] = set()
    for group in by_gu.values():
        group.sort(key=lambda x: (
            x.get("partOfGroup") is None,
            not is_dev_zone(x.get("regZoning")),
            _safe_num(x.get("maxFar")) or 0,
            float(x["dealPrice"]),
            str(x.get("articleNo")),
        ))
        kept: dict[int, list[dict]] = {}     # 대지면적(㎡ 정수) → 남긴 매물
        for a in group:
            land = float(a["landSpace"])
            tol = max(1.0, land * 0.01)
            near = (k for bucket in range(int(land - tol), int(land + tol) + 1)
                    for k in kept.get(bucket, ()) if abs(float(k["landSpace"]) - land) <= tol)
            match = next((k for k in near if same_building(a, k)), None)
            if match is None:
                kept.setdefault(int(land), []).append(a)
                continue
            dropped.add(str(a.get("articleNo")))
            if lookup_far(a.get("regZoning"))[0] != lookup_far(match.get("regZoning"))[0]:
                zoning_conflict.add(str(match.get("articleNo")))
    return dropped, zoning_conflict


def find_same_building_duplicates(articles: Iterable[dict], max_distance_m: float = 50) -> set[str]:
    """같은 건물이 여러 번 등재된 매물의 articleNo 집합 (남길 1건 제외). same_building_report 참고."""
    return same_building_report(articles, max_distance_m)[0]


def dedupe_by_address_min_price(articles: list[dict]) -> list[dict]:
    """Keep the cheapest article per (city, division, sector, lat, lon).

    fin.land's `boundedArticles` doesn't expose a single full-address string,
    so we key on (시·구·동 + 좌표) which is good enough to collapse duplicate
    listings of the same physical building.
    """
    by_key: dict[tuple, dict] = {}
    no_addr: list[dict] = []
    for art in articles:
        addr = art.get("address") or {}
        coord = addr.get("coordinates") or {}
        key = (
            addr.get("city"),
            addr.get("division"),
            addr.get("sector"),
            coord.get("xCoordinate"),
            coord.get("yCoordinate"),
        )
        if not all(key):
            no_addr.append(art)
            continue
        price = (art.get("priceInfo") or {}).get("dealPrice", float("inf"))
        cur = by_key.get(key)
        if cur is None or price < (cur.get("priceInfo") or {}).get("dealPrice", float("inf")):
            by_key[key] = art
    return list(by_key.values()) + no_addr


# ── Flatten ─────────────────────────────────────────────────────────────
def _g(d: dict | None, *path, default=None):
    """Safe nested-get: _g(article, 'address', 'coordinates', 'xCoordinate')."""
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def flatten_article(
    bounded: dict,
    *,
    pnu: str | None = None,
    building: dict | None = None,
    agent: dict | None = None,
    development: dict | None = None,
) -> dict:
    """Combine a `boundedArticles` entry + (optional) buildingRegistration +
    agent + development response into a single flat row.

    development:
      `/front-api/v1/development?type=article&itemId=...` 응답 result.
      `jiguList` (지구단위계획), `railList` (미래 역세권)."""
    rep = bounded.get("representativeArticleInfo") or {}
    space = rep.get("spaceInfo") or {}
    price = rep.get("priceInfo") or {}
    addr = rep.get("address") or {}
    coord = addr.get("coordinates") or {}
    binfo = rep.get("buildingInfo") or {}
    detail = rep.get("articleDetail") or {}
    floor_detail = detail.get("floorDetailInfo") or {}
    broker = rep.get("brokerInfo") or {}

    # 결측 marker — "raw에서 누락"과 "0으로 들어옴"을 구분 (downstream 0 처리는 유지,
    # 단 marker로 매물 검토자에게 "가격정보 없음" 배지 등 노출 가능)
    _price_raw_missing = price.get("dealPrice") in (None, "", 0, "0")
    _land_raw_missing = space.get("landSpace") in (None, "", 0, "0")

    out: dict[str, Any] = {
        # 기본
        "articleNo": rep.get("articleNumber", ""),
        "name": rep.get("articleName", ""),
        "tradeType": rep.get("tradeType", ""),
        "realEstateType": rep.get("realEstateType", ""),

        # 가격 — fin.land는 원 단위로 응답하므로 만원으로 변환해서 저장
        # (옛 new.land는 만원 단위였고, 이후 코드는 모두 만원 가정으로 짜였음)
        "dealPrice": _won_to_10k(price.get("dealPrice", 0)),
        "warrantyPrice": _won_to_10k(price.get("warrantyPrice", 0)),
        "rentPrice": _won_to_10k(price.get("rentPrice", 0)),
        "dealPriceMissing": _price_raw_missing,
        "landSpaceMissing": _land_raw_missing,

        # 면적
        "supplySpace": space.get("supplySpace", 0),
        "exclusiveSpace": space.get("exclusiveSpace", 0),
        "landSpace": space.get("landSpace", 0),       # 대지면적
        "floorSpace": space.get("floorSpace", 0),     # 연면적

        # 주소 / 좌표
        "cityName": addr.get("city", ""),
        "divisionName": addr.get("division", ""),
        "sectorName": addr.get("sector", ""),
        "latitude": coord.get("yCoordinate"),
        "longitude": coord.get("xCoordinate"),

        # 층
        "floorInfo": detail.get("floorInfo", ""),
        "groundTotalFloor": floor_detail.get("groundTotalFloor", ""),
        "undergroundTotalFloor": floor_detail.get("undergroundTotalFloor", ""),

        # 매물 메타
        "articleFeatureDescription": detail.get("articleFeatureDescription", ""),
        "approvalDateRaw": binfo.get("buildingConjunctionDate", ""),
        "approvalElapsedYear": binfo.get("approvalElapsedYear", ""),

        # 중개업소 (목록 기본)
        "brokerageName": broker.get("brokerageName", ""),
        "brokerName": broker.get("brokerName", ""),

        # 사진 1장
        "thumbnailUrl": _g(rep, "articleMediaDto", "imageUrl", default=""),
    }

    # PNU
    out["pnu"] = pnu or ""

    # 건축물대장 (옵션)
    if building:
        out.update({
            "regBuildingName": building.get("name", ""),
            "regRoadAddress": building.get("roadNameAddress", ""),
            "regStructure": building.get("structure", ""),
            "regBuildingUse": building.get("buildingUse", ""),
            "regUseApprovalDate": building.get("useApprovalDate", ""),
            "regHouseholdNumber": building.get("householdNumber", 0),
            "regElevatorCount": building.get("elevatorCount", 0),
            "regFloorAreaRatio": _g(building, "buildingRatioInfo", "floorAreaRatio"),
            "regBuildingCoverageRatio": _g(building, "buildingRatioInfo", "buildingCoverageRatio"),
            "regTotalParkingCount": _g(building, "parkingInfo", "totalParkingCount"),
            "regZoning": _g(building, "specialPurposeInfo", "area", "purpose", default=""),
            "regDistrict": _g(building, "specialPurposeInfo", "district", "purpose", default=""),
        })
    else:
        # placeholders so the downstream DataFrame has stable columns
        for k in (
            "regBuildingName", "regRoadAddress", "regStructure", "regBuildingUse",
            "regUseApprovalDate", "regHouseholdNumber", "regElevatorCount",
            "regFloorAreaRatio", "regBuildingCoverageRatio", "regTotalParkingCount",
            "regZoning", "regDistrict",
        ):
            out[k] = ""

    # 중개업소 디테일 (옵션)
    if agent:
        out.update({
            "agentBrokerageName": agent.get("brokerageName", ""),
            "agentBrokerName": agent.get("brokerName", ""),
            "agentAddress": agent.get("address", ""),
            "agentBusinessNo": agent.get("businessRegistrationNumber", ""),
            "agentPhone": _g(agent, "phone", "brokerage", default=""),
        })
    else:
        for k in ("agentBrokerageName", "agentBrokerName", "agentAddress",
                  "agentBusinessNo", "agentPhone"):
            out[k] = ""

    # 개발정보: 지구단위계획구역 + 미래 역세권
    _apply_development(out, development)

    # FAR 명목값 (조례에 의한 최대 용적률 — 용도지역 이름 기준)
    out["maxFar"], out["maxFarSeoulCore"] = lookup_far(out["regZoning"])

    return out


def rail_opened(open_date: Any, as_of: str | None) -> bool:
    """개통 예정일이 기준일(YYYY-MM-DD)보다 앞선 달이면 True — 이미 개통했다고 본다.

    open_date는 "2024.12", "2027-11", "2030" 같은 형태 (연도만 있으면 12월로 본다).
    """
    m = re.match(r"\s*(\d{4})(?:\D+(\d{1,2}))?", str(open_date or ""))
    if not m or not as_of:
        return False
    opened = (int(m.group(1)), int(m.group(2) or 12))
    return opened < (int(as_of[:4]), int(as_of[5:7]))


def _apply_development(out: dict, development: dict | None) -> None:
    """development 응답에서 지구단위계획 + 미래역세권 요약을 out에 채움."""
    jigu_list = (development or {}).get("jiguList") or []
    # 수집 시점에 이미 개통한 역은 "개통 예정"에서 뺀다 (원본에 옛 예정일이 남아 있음)
    today = date.today().isoformat()
    rail_list = [r for r in (development or {}).get("railList") or []
                 if not rail_opened(r.get("openDate"), today)]

    # 지구 (지구단위계획구역 우선)
    out["devJiguCount"] = len(jigu_list)
    if jigu_list:
        # 지구단위계획구역 우선, 없으면 첫 항목
        primary = next(
            (j for j in jigu_list if "지구단위계획" in (j.get("typeName") or "")),
            jigu_list[0],
        )
        out["devJiguPrimaryName"] = primary.get("name", "")
        out["devJiguPrimaryType"] = primary.get("typeName", "")
        out["devJiguPrimaryStep"] = primary.get("step", "")
        # 전체 지구 목록 (요약 — 콤마 구분)
        out["devJiguAllNames"] = ", ".join(
            f"{j.get('name')}[{j.get('typeName')}]" for j in jigu_list if j.get("name")
        )
    else:
        out["devJiguPrimaryName"] = ""
        out["devJiguPrimaryType"] = ""
        out["devJiguPrimaryStep"] = ""
        out["devJiguAllNames"] = ""

    # 미래 역세권 (가장 가까운 1~3개)
    out["devRailCount"] = len(rail_list)
    if rail_list:
        rails_sorted = sorted(rail_list, key=lambda r: r.get("distance") or 999999)
        nearest = rails_sorted[0]
        out["devNearestRailStation"] = nearest.get("stationName", "")
        out["devNearestRailLine"] = nearest.get("railName", "")
        out["devNearestRailDistanceM"] = nearest.get("distance")
        out["devNearestRailWalkMin"] = nearest.get("walkingTime")
        out["devNearestRailOpenDate"] = nearest.get("openDate", "")
        # 모든 미래역 요약
        out["devRailSummary"] = " · ".join(
            f"{r.get('stationName')}({r.get('walkingTime')}분, {r.get('openDate')})"
            for r in rails_sorted[:3]
        )
    else:
        for k in ("devNearestRailStation", "devNearestRailLine", "devNearestRailOpenDate", "devRailSummary"):
            out[k] = ""
        out["devNearestRailDistanceM"] = None
        out["devNearestRailWalkMin"] = None


# ── 용도지역 → 명목 최대 용적률 (도시계획법 시행령) ──────────────────────
# 정식 용도지역 분류 + buildingRegistration이 광역 카테고리로 줄 때를 위한 fallback.
# 광역 키는 보수적인 값(해당 카테고리에서 평균~보수)으로 매핑.
FAR_BY_ZONING: dict[str, dict[str, int]] = {
    # ── 정식 분류 ──
    "제1종전용주거지역": {"max_far": 100},
    "제2종전용주거지역": {"max_far": 120},
    "제1종일반주거지역": {"max_far": 150},
    "제2종일반주거지역": {"max_far": 200},
    "제3종일반주거지역": {"max_far": 250},
    "준주거지역": {"max_far": 400},
    "중심상업지역": {"max_far": 1000, "max_far_seoul_core": 800},
    "일반상업지역": {"max_far": 800, "max_far_seoul_core": 600},
    "근린상업지역": {"max_far": 600, "max_far_seoul_core": 500},
    "유통상업지역": {"max_far": 600, "max_far_seoul_core": 500},
    "전용공업지역": {"max_far": 200},
    "일반공업지역": {"max_far": 200},
    "준공업지역": {"max_far": 400},
    "보전녹지지역": {"max_far": 50},
    "생산녹지지역": {"max_far": 50},
    "자연녹지지역": {"max_far": 50},
    # ── 광역 fallback (buildingRegistration이 광역 카테고리로 줄 때) ──
    "일반주거지역": {"max_far": 200},      # 평균: 제1~제3 일반주거 (150~250)
    "일반주거": {"max_far": 200},          # 약식 표기
    "주거지역": {"max_far": 200},          # 광역 (전용+일반+준)
    "전용주거지역": {"max_far": 100},      # 보수적
    "준주거": {"max_far": 400},
    "상업지역": {"max_far": 800, "max_far_seoul_core": 600},   # 광역 (중심/일반/근린/유통) — 일반상업 기준
    "준공업": {"max_far": 400},
    "도시지역": {"max_far": 200},          # 도시지역 광역 — 보수적 (대부분 일반주거)
    # 복합 표기 (buildingRegistration이 ',' 로 여러 지역 줄 때) — 첫 항목 기준
    "준공업지역,노선상업지역": {"max_far": 400},
    # 의도적 제외 (호텔 개발 부적합 / 추가 규제):
    # - "절대보호구역" / "상대보호구역" → 학교 주변 등 추가 제한
    # - "가로구역별최고높이제한지역" → 높이 추가 규제
    # - "건축용도지역기타" → 모호함
}


def normalize_zoning(raw: str | None) -> str | None:
    """네이버 raw 용도지역 표기를 FAR/필터 lookup 가능한 정규형으로.

    - 공백 trim ("제3종일반주거지역 " → "제3종일반주거지역")
    - 복합표기 "준공업지역,노선상업지역" → "준공업지역" (첫 토큰, 가장 제한적)
      복합 키 자체가 FAR_BY_ZONING에 있으면 그대로 유지.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    # 복합표기 — 사전에 명시된 복합 키면 그대로
    if s in FAR_BY_ZONING:
        return s
    if "," in s:
        first = s.split(",", 1)[0].strip()
        return first or None
    return s


# 한양도성(서울 역사도심) 경계 — 성곽 주요 지점을 이은 근사 폴리곤 (위도, 경도).
# 서울시 도시계획 조례상 역사도심 안 상업지역은 용적률이 낮게 적용된다
# (FAR_BY_ZONING의 max_far_seoul_core). 경계 부근 수십 m 오차는 있을 수 있음.
HANYANG_WALL: tuple[tuple[float, float], ...] = (
    (37.5600, 126.9753),  # 숭례문
    (37.5633, 126.9718),  # 소의문 터 (서소문) — 숭례문~돈의문 직선보다 서쪽으로 나간다
    (37.5689, 126.9676),  # 돈의문 터
    (37.5850, 126.9577),  # 인왕산
    (37.5926, 126.9667),  # 창의문
    (37.5932, 126.9764),  # 백악
    (37.5957, 126.9818),  # 숙정문
    (37.5876, 127.0021),  # 혜화문
    (37.5805, 127.0077),  # 낙산
    (37.5711, 127.0095),  # 흥인지문
    (37.5646, 127.0094),  # 광희문
    (37.5560, 127.0010),  # 장충동
    (37.5512, 126.9882),  # 남산
    (37.5553, 126.9790),  # 회현
)


def is_in_historic_core(lat: float | None, lon: float | None) -> bool:
    """좌표가 한양도성 안(역사도심)인지 — ray casting."""
    if lat is None or lon is None:
        return False
    y, x = float(lat), float(lon)
    inside = False
    pts = HANYANG_WALL
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def lookup_far(zoning: str | None) -> tuple[int | None, int | None]:
    z = normalize_zoning(zoning)
    if not z:
        return None, None
    info = FAR_BY_ZONING.get(z, {})
    return info.get("max_far"), info.get("max_far_seoul_core")


# 호텔(숙박시설)·대형 오피스(업무시설) 신축이 가능한 용도지역 keyword.
# 일반주거/전용주거/녹지 등은 숙박시설 불가, 업무시설도 소규모만 허용.
DEV_ZONE_KEYWORDS = ("상업지역", "준주거지역", "준공업지역", "관광휴양")


def is_dev_zone(zoning: str | None) -> bool:
    """호텔/오피스 신축 가능 용도지역 여부 (normalize 후 keyword substring)."""
    z = normalize_zoning(zoning)
    return bool(z) and any(kw in z for kw in DEV_ZONE_KEYWORDS)


# ── 개발 시뮬레이션 (호텔: 등급별 모델) ─────────────────────────────────
#
# 모델 흐름:
#   1) 개발 연면적 (지상+지하) 평수 계산
#   2) 평수 임계치로 호텔 등급 자동 분류 (3성/4성/5성)
#   3) 등급별 프로필 적용 (전용율, 객실면적, ADR/Occ/F&B/GOP, 평당 공사비)
#   4) ADR을 자치구 Tier multiplier로 보정하고, 숙박 거점 역 반경 밖이면 보정율 하향
#   5) 매출 = effective_ADR × Occ × 365 × 객실수 + F&B
#   6) 수익(GOP) = 매출 × GOP 비율
#   7) NOI = GOP − 운영사 fee − 재산세·보험 − FF&E reserve
#   8) Cap Rate = 안정화 NOI / 총개발비 (Yield on Cost)
#
# 등급별 가정값은 `config/default.yaml`의 `dev_simulation.grade_3/4/5` 섹션에서
# 오버라이드. 코드 수정 없이 가정 변경 가능.

# ── 자치구별 ADR Tier (위치 프리미엄) ──────────────────────────────────
# 같은 등급 호텔이라도 위치에 따라 ADR이 다름. Tier 1(핵심) ~ Tier 4(외곽).
# 사이드바 ADR 슬라이더는 Tier 1 기준값을 의미하고, 다른 Tier 구는 자동 비례.
GU_ADR_TIER: dict[str, float] = {
    # Tier 1 (100%) — 핵심 관광·업무 지역
    "마포구": 1.00, "종로구": 1.00, "중구": 1.00, "강남구": 1.00,
    # Tier 2 (90%) — 준핵심
    "용산구": 0.90, "성동구": 0.90, "서초구": 0.90,
    # Tier 3 (80%) — 주요 부도심
    "서대문구": 0.80, "동대문구": 0.80, "송파구": 0.80, "영등포구": 0.80,
    # 그 외 (70%) — Tier 4, default
}
ADR_TIER_DEFAULT: float = 0.70

# ADR Tier별 호텔 매각(Exit) Cap Rate — prime일수록 낮음. 가정값.
HOTEL_EXIT_CAP_BY_TIER: dict[int, float] = {1: 0.050, 2: 0.058, 3: 0.065, 4: 0.072}

# ── 입지 보정: 핵심 역세권 ──────────────────────────────────────────────
# 자치구 단위 가정(호텔 ADR Tier, 오피스 권역)만 쓰면 같은 구의 변두리 동에도 핵심지
# 값이 들어가, 땅값이 싼 변두리 부지가 순위 상단을 차지한다. 그래서 역 좌표 기준
# 반경으로 한 번 더 나눈다. (이름, 위도, 경도) — 반경은 DevAssumptions.
#
# 숙박 수요 거점 — 관광·비즈니스 호텔이 실제로 모여 있는 곳. 반경 밖이면 ADR 보정율을
# hotel_off_hub_adr_step만큼 낮춘다 (Tier 4 구는 60%까지 내려간다).
HOTEL_HUBS: tuple[tuple[str, float, float], ...] = (
    ("명동", 37.5609, 126.9864), ("을지로입구", 37.5659, 126.9826), ("시청", 37.5655, 126.9771),
    ("광화문", 37.5716, 126.9769), ("종각", 37.5702, 126.9832), ("종로3가", 37.5704, 126.9923),
    ("안국", 37.5768, 126.9862), ("회현", 37.5587, 126.9784), ("서울역", 37.5547, 126.9707),
    ("충무로", 37.5612, 126.9941), ("을지로3가", 37.5663, 126.9925),
    ("동대문역사문화공원", 37.5653, 127.0079), ("동대문", 37.5705, 127.0095),
    ("홍대입구", 37.5570, 126.9252), ("합정", 37.5494, 126.9137), ("신촌", 37.5552, 126.9369),
    ("공덕", 37.5437, 126.9508), ("이태원", 37.5345, 126.9944), ("용산", 37.5299, 126.9648),
    ("강남", 37.4979, 127.0276), ("신논현", 37.5043, 127.0245), ("역삼", 37.5006, 127.0364),
    ("선릉", 37.5045, 127.0490), ("삼성", 37.5088, 127.0631), ("신사", 37.5161, 127.0195),
    ("논현", 37.5110, 127.0214), ("잠실", 37.5132, 127.1001),
    ("여의도", 37.5217, 126.9243), ("국회의사당", 37.5280, 126.9180), ("여의나루", 37.5269, 126.9325),
    ("영등포", 37.5154, 126.9069),
    ("성수", 37.5446, 127.0561), ("뚝섬", 37.5472, 127.0474), ("서울숲", 37.5436, 127.0446),
    ("건대입구", 37.5404, 127.0701),
    ("구로디지털단지", 37.4853, 126.9016), ("신도림", 37.5090, 126.8914),
)

# 오피스 권역 핵심 — 해당 자치구 안에서 반경 안이면 그 권역 NOC·매각 Cap, 밖이면 '기타'.
# (구 조건을 함께 보는 이유: 반경만 쓰면 구 경계 너머 동네까지 권역으로 잡힌다.)
OFFICE_CORES: dict[str, tuple[tuple[str, float, float], ...]] = {
    "CBD": (
        ("광화문", 37.5716, 126.9769), ("종각", 37.5702, 126.9832), ("종로3가", 37.5704, 126.9923),
        ("시청", 37.5655, 126.9771), ("을지로입구", 37.5659, 126.9826),
        ("을지로3가", 37.5663, 126.9925), ("명동", 37.5609, 126.9864),
        ("회현", 37.5587, 126.9784), ("서울역", 37.5547, 126.9707),
    ),
    "GBD": (
        ("강남", 37.4979, 127.0276), ("역삼", 37.5006, 127.0364), ("선릉", 37.5045, 127.0490),
        ("삼성", 37.5088, 127.0631), ("신논현", 37.5043, 127.0245), ("논현", 37.5110, 127.0214),
        ("신사", 37.5161, 127.0195), ("교대", 37.4937, 127.0137),
        ("언주", 37.5073, 127.0339), ("선정릉", 37.5103, 127.0439),
        ("삼성중앙", 37.5131, 127.0535), ("봉은사", 37.5142, 127.0602),
        ("학동", 37.5140, 127.0308), ("강남구청", 37.5172, 127.0413),
    ),
}
# YBD는 여의도동 전체 (섬이라 반경보다 동 경계가 정확하다)
YBD_SECTOR = "여의도동"


def _dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이 거리 (m) — 서울 위도 기준 평면 근사."""
    dlat = (lat1 - lat2) * 111_000
    dlon = (lon1 - lon2) * 88_000
    return (dlat * dlat + dlon * dlon) ** 0.5


def nearest_anchor(lat: Any, lon: Any,
                   anchors: Iterable[tuple[str, float, float]]) -> tuple[str | None, float | None]:
    """가장 가까운 기준점 (이름, 거리 m). 좌표가 없으면 (None, None)."""
    y, x = _num_or_none(lat), _num_or_none(lon)
    if y is None or x is None:
        return None, None
    name, d = min(((n, _dist_m(y, x, alat, alon)) for n, alat, alon in anchors), key=lambda t: t[1])
    return name, d


def _tier_of(mult: float) -> int:
    if mult >= 1.00: return 1
    if mult >= 0.90: return 2
    if mult >= 0.80: return 3
    return 4


def get_adr_tier(division_name: str | None) -> tuple[float, int]:
    """자치구 이름 → (multiplier, tier 1-4).

    >>> get_adr_tier("강남구")  → (1.0, 1)
    >>> get_adr_tier("동작구")  → (0.70, 4)
    """
    mult = GU_ADR_TIER.get(division_name or "", ADR_TIER_DEFAULT)
    return mult, _tier_of(mult)


def hotel_location(division_name: str | None, lat: Any, lon: Any,
                   hub_radius_m: float, off_hub_step: float,
                   ) -> tuple[float, int, str | None, float | None]:
    """호텔 입지 → (ADR 보정율, Tier, 거점 이름, 가장 가까운 거점까지 거리 m).

    자치구 Tier에서 출발해, 숙박 수요 거점 반경 밖이면 보정율을 off_hub_step만큼
    낮춘다. 거점 이름은 반경 안일 때만 채운다. 좌표가 없으면 반경을 확인할 수 없으므로
    거점 밖으로 본다.
    """
    mult, _ = get_adr_tier(division_name)
    hub, dist = nearest_anchor(lat, lon, HOTEL_HUBS)
    if dist is None or dist > hub_radius_m:
        mult = round(mult - off_hub_step, 4)
        hub = None
    return mult, _tier_of(mult), hub, dist

@dataclass
class HotelGradeProfile:
    """등급별 호텔 가정값."""
    exclusive_ratio: float          # 전용면적 비율 (지상 대비)
    room_area_sqm: float            # 1객실당 면적 (㎡)
    adr_10k: float                  # 객실 평균 단가 ADR (만원/박)
    occupancy: float                # 객실 점유율 (0~1)
    fnb_ratio: float                # F&B 매출 = 객실 매출 × 이 비율
    gop_ratio: float                # GOP 마진 (총매출 대비)
    construction_cost_per_pyeong_M: float  # 평당 공사비 (백만/평)


# 등급별 기본값 (사용자 정의).
# 전용률은 지상 연면적 중 객실이 차지하는 비율 — 로비·복도·코어·부대시설을 빼고 남는 몫.
# 지하를 포함한 객실당 연면적으로 환산하면 약 35㎡(3성) / 54㎡(4성) / 89㎡(5성).
_DEFAULT_GRADE_3 = HotelGradeProfile(
    exclusive_ratio=0.62, room_area_sqm=20.0,
    adr_10k=15.0, occupancy=0.87, fnb_ratio=0.10,
    gop_ratio=0.50, construction_cost_per_pyeong_M=12.0,
)
_DEFAULT_GRADE_4 = HotelGradeProfile(
    exclusive_ratio=0.50, room_area_sqm=25.0,
    adr_10k=20.0, occupancy=0.85, fnb_ratio=0.15,
    gop_ratio=0.45, construction_cost_per_pyeong_M=14.0,
)
_DEFAULT_GRADE_5 = HotelGradeProfile(
    exclusive_ratio=0.40, room_area_sqm=33.0,
    adr_10k=40.0, occupancy=0.80, fnb_ratio=0.30,
    gop_ratio=0.375, construction_cost_per_pyeong_M=18.0,
)


# ── 오피스 개발 (임대형) ─────────────────────────────────────────────
#   전용면적 = 연면적 × 전용률(50%),  임대면적 = 연면적 (전용률 역산)
#   임대수입 = 전용면적 × NOC(권역별, 원/전용평/월) × 12 × (1 − 공실률)
#   운용비용 = 임대면적 × 운용비 단가(3만원/평/월) × 12   (재산세·관리 포함)
#   NOI      = 임대수입 − 운용비용
# NOC(Net Occupancy Cost)는 임차인이 전용평당 실제 부담하는 월 비용(임대료+관리비,
# 렌트프리 반영). ⚠️ 권역별 NOC·매각 Cap은 가정값 — config에서 검토/수정.

# 자치구 → 그 구에 핵심이 있는 오피스 권역 (YBD는 여의도동으로 따로 본다)
GU_OFFICE_MARKET: dict[str, str] = {
    "중구": "CBD", "종로구": "CBD",
    "강남구": "GBD", "서초구": "GBD",
}
OFFICE_MARKET_DEFAULT = "기타"


def get_office_market(division_name: str | None) -> str:
    """자치구 → 그 구에 핵심 역이 있는 권역 이름 (없으면 '기타'). 실제 권역 판정은 office_location."""
    return GU_OFFICE_MARKET.get(division_name or "", OFFICE_MARKET_DEFAULT)


def office_location(division_name: str | None, sector_name: str | None, lat: Any, lon: Any,
                    core_radius_m: float) -> tuple[str, str | None, float | None]:
    """오피스 입지 → (권역, 핵심 역 이름, 그 권역 핵심 역까지 거리 m).

    CBD·GBD는 해당 자치구 안에서 핵심 역 반경 안일 때만, YBD는 여의도동만 인정하고
    그 밖은 '기타' — 같은 구라도 업무지구에서 떨어진 동에 프라임 NOC를 주지 않기 위함.
    좌표가 없으면 반경을 확인할 수 없으므로 '기타'.
    """
    if sector_name == YBD_SECTOR:
        return "YBD", "여의도", None
    market = get_office_market(division_name)
    if market == OFFICE_MARKET_DEFAULT:
        return OFFICE_MARKET_DEFAULT, None, None
    name, d = nearest_anchor(lat, lon, OFFICE_CORES[market])
    if d is not None and d <= core_radius_m:
        return market, name, d
    return OFFICE_MARKET_DEFAULT, None, d


@dataclass
class OfficeMarket:
    noc_10k: float         # NOC (만원/전용평/월)
    vacancy: float         # 안정화 공실률 (NOC가 이미 반영했다면 0)
    exit_cap: float        # 매각 Cap Rate (DCF용)


_DEFAULT_OFFICE_MARKETS: dict[str, OfficeMarket] = {
    "CBD": OfficeMarket(noc_10k=28.0, vacancy=0.0, exit_cap=0.045),
    "GBD": OfficeMarket(noc_10k=28.0, vacancy=0.0, exit_cap=0.045),
    "YBD": OfficeMarket(noc_10k=24.0, vacancy=0.0, exit_cap=0.048),
    "기타": OfficeMarket(noc_10k=17.0, vacancy=0.0, exit_cap=0.055),
}


@dataclass
class OfficeProfile:
    min_total_pyeong: float = 1000          # 개발 연면적 이 미만이면 오피스 부적합
    exclusive_ratio: float = 0.50           # 전용률 (전용면적 / 연면적)
    opex_10k_per_pyeong: float = 3.0        # 운용비용 (만원/임대평/월)
    construction_cost_per_pyeong_M: float = 11.0
    # 연면적 규모 구분 (평) — 대형 / 중대형 / 중형 / 소형
    large_min_pyeong: float = 10000
    mid_large_min_pyeong: float = 5000
    mid_min_pyeong: float = 2000
    markets: dict[str, OfficeMarket] = field(
        default_factory=lambda: dict(_DEFAULT_OFFICE_MARKETS)
    )

    def size_class(self, total_py: float) -> str:
        if total_py >= self.large_min_pyeong:
            return "대형 오피스"
        if total_py >= self.mid_large_min_pyeong:
            return "중대형 오피스"
        if total_py >= self.mid_min_pyeong:
            return "중형 오피스"
        return "소형 오피스"

    def market(self, name: str) -> OfficeMarket:
        return self.markets.get(name) or self.markets.get(OFFICE_MARKET_DEFAULT) \
            or _DEFAULT_OFFICE_MARKETS[OFFICE_MARKET_DEFAULT]

    @classmethod
    def from_config(cls, section: dict[str, Any] | None) -> "OfficeProfile":
        if not section:
            return cls()
        kwargs = {k: v for k, v in section.items()
                  if k in cls.__dataclass_fields__ and k != "markets"}
        markets = dict(_DEFAULT_OFFICE_MARKETS)
        for name, m in (section.get("markets") or {}).items():
            base = markets.get(name) or _DEFAULT_OFFICE_MARKETS[OFFICE_MARKET_DEFAULT]
            markets[name] = OfficeMarket(**{
                f: m.get(f, getattr(base, f)) for f in OfficeMarket.__dataclass_fields__
            })
        return cls(**kwargs, markets=markets)


@dataclass
class DevAssumptions:
    """호텔 개발 가정값 (등급 무관 + 등급 분류 임계 + 등급별 프로필).

    단위 표기:
      *_M     = 백만원
      *_10k   = 만원
      *_pct   = 퍼센트(0~100)
      *_ratio = 비율(0~1)
    """
    # 면적/금융 (등급 무관)
    sqm_to_pyeong: float = 0.3025
    basement_ratio: float = 0.60         # 지하면적 = 대지(평) × 60%
    incidental_rate: float = 0.06        # 부대비용 = (매입+공사) × 6%
    ltv: float = 0.60                    # 대출 비율
    interest_rate: float = 0.055         # 연 이자율 (건설이자 · DCF 대출금리 공통)
    loan_years: int = 2                  # 대출 기간

    # 호텔 등급 분류 임계 (개발 연면적 평 기준)
    grade_3_min_pyeong: float = 1500     # 1500평 미만 → 등급외 (호텔 부적합)
    grade_4_min_pyeong: float = 3000     # 1500~3000평 → 3성급
    grade_5_min_pyeong: float = 7000     # 3000~7000평 → 4성급, 이상 → 5성급

    # 표시(`isShown`) 필터 — 지도/엑셀에 보일지 여부
    # 대지면적 상한: 단지/이상치 매물 제외 (예: 강남구 7000평짜리 부지 = 단지 또는 잘못된 등재)
    max_land_pyeong: float = 10000       # 약 33,058㎡ 초과 시 isShown=False
    # 토지 평당가 이상치 임계 (백만원/평)
    min_land_per_pyeong_M: float = 20.0    # 2,000만원/평 미만 → 데이터 오류
    max_land_per_pyeong_M: float = 1000.0  # 10억/평 초과 → 호실 매물 등 오등록
    # 현재 건물 연면적 기준 평당가 하한 — 이보다 싸면 건물 전체가 아니라 호실·지분 매물로 봄
    min_bldg_per_pyeong_M: float = 5.0     # 500만원/평
    # 상업지역 토지 평당가 하한 — 서울 핵심 구 상업지역에서 이보다 싸면 면적·호가 입력 오류로 봄
    min_commercial_land_per_pyeong_M: float = 40.0   # 4,000만원/평
    # 대지면적이 소재 필지 면적의 이 비율 미만 → 큰 필지의 지분·호실 매물로 봄
    min_parcel_share: float = 0.5
    # 현재 건물 연면적 ÷ 개발 가능 연면적이 이 값 이상 → 새로 지어도 면적이 1.5배가 안 됨 (신축 실익 부족)
    max_existing_gfa_ratio: float = 0.67
    # 준공 new_building_years년차 미만이고 이미 new_building_gfa_ratio 이상 지어진 건물은
    # 아직 쓸 만한 중층 건물 → 철거 대상 아님 (예: 20년차 13층 건물을 1.5배 지으려고 헐지 않는다)
    new_building_years: float = 30
    new_building_gfa_ratio: float = 0.5

    # 입지 보정 — 자치구 단위 가정을 핵심 역세권 여부로 한 번 더 나눈다 (HOTEL_HUBS / OFFICE_CORES)
    hotel_hub_radius_m: float = 800      # 숙박 수요 거점 역 반경
    hotel_off_hub_adr_step: float = 0.10 # 거점 밖이면 ADR 보정율을 이만큼 낮춤
    office_core_radius_m: float = 700    # 권역 핵심 역 반경 — 밖이면 '기타' 권역

    # GOP → NOI 차감 항목 (USALI 기준 — 호텔 Cap Rate는 NOI 기준으로 거래됨)
    #   NOI = GOP − 운영사 base fee − incentive fee − 재산세·보험 − FF&E reserve
    mgmt_fee_base: float = 0.02          # 운영사 base fee (총매출 대비)
    mgmt_fee_incentive: float = 0.08     # 운영사 incentive fee (GOP 대비)
    property_tax_rate: float = 0.003     # 재산세+보험 (총개발비를 자산가치 proxy)
    ff_e_reserve: float = 0.03           # FF&E reserve (총매출 대비)

    # 등급별 프로필
    grade_3: HotelGradeProfile = field(default_factory=lambda: _DEFAULT_GRADE_3)
    grade_4: HotelGradeProfile = field(default_factory=lambda: _DEFAULT_GRADE_4)
    grade_5: HotelGradeProfile = field(default_factory=lambda: _DEFAULT_GRADE_5)

    # 오피스 개발 프로필
    office: OfficeProfile = field(default_factory=OfficeProfile)

    def determine_grade(self, total_pyeong: float) -> int | None:
        """연면적(평) → 호텔 등급. 1500평 미만이면 None (등급외)."""
        if total_pyeong < self.grade_3_min_pyeong:
            return None
        if total_pyeong < self.grade_4_min_pyeong:
            return 3
        if total_pyeong < self.grade_5_min_pyeong:
            return 4
        return 5

    def profile_for(self, grade: int | None) -> HotelGradeProfile | None:
        if grade is None:
            return None
        return getattr(self, f"grade_{grade}", None)

    @classmethod
    def from_config(cls, section: dict[str, Any] | None) -> "DevAssumptions":
        """YAML 섹션에서 인스턴스화. 누락된 필드는 기본값."""
        if not section:
            return cls()

        # 평탄한 (등급 무관) 파라미터
        flat_keys = {
            "sqm_to_pyeong", "basement_ratio", "incidental_rate",
            "ltv", "interest_rate", "loan_years",
            "grade_3_min_pyeong", "grade_4_min_pyeong", "grade_5_min_pyeong",
            "max_land_pyeong",
            "min_land_per_pyeong_M", "max_land_per_pyeong_M", "min_bldg_per_pyeong_M",
            "min_commercial_land_per_pyeong_M",
            "min_parcel_share", "max_existing_gfa_ratio",
            "new_building_years", "new_building_gfa_ratio",
            "hotel_hub_radius_m", "hotel_off_hub_adr_step", "office_core_radius_m",
            "mgmt_fee_base", "mgmt_fee_incentive", "property_tax_rate", "ff_e_reserve",
        }
        kwargs: dict[str, Any] = {k: v for k, v in section.items() if k in flat_keys}

        # 등급별 프로필
        for grade_num, default in ((3, _DEFAULT_GRADE_3), (4, _DEFAULT_GRADE_4), (5, _DEFAULT_GRADE_5)):
            key = f"grade_{grade_num}"
            cfg_profile = section.get(key)
            if cfg_profile:
                # 부분 오버라이드 허용 (누락된 키는 default 값 유지)
                merged = {f: getattr(default, f) for f in HotelGradeProfile.__dataclass_fields__}
                for k, v in cfg_profile.items():
                    if k in HotelGradeProfile.__dataclass_fields__:
                        merged[k] = v
                kwargs[key] = HotelGradeProfile(**merged)

        if section.get("office"):
            kwargs["office"] = OfficeProfile.from_config(section["office"])

        return cls(**kwargs)


# 시뮬 결과로 채워지는 모든 컬럼. 입력 article에 이전 시뮬 값이 남아 있어도
# 매번 None으로 초기화한 뒤 다시 계산한다 (stale 값 방지).
_METRIC_KEYS = (
    "landPyeong", "totalPyeong", "landPerPyeongM", "bldgPerPyeongM",
    "devBasementPyeong", "devAbovePyeong", "devTotalPyeong", "devZoneOk", "inHistoricCore",
    # 선택된 용도 기준 (select_use가 채움)
    "devUse", "devClass", "capRate", "noiAnnualM", "exitCap",
    "costPurchaseM", "costConstructionM", "costIncidentalM", "costFinanceM",
    "costTotalM", "costPerPyeongM",
    # 호텔
    "hotelGrade", "hotelCapRate", "hotelNoiAnnualM", "hotelCostTotalM", "hotelExitCap",
    "hotelCostConstructionM", "hotelCostIncidentalM", "hotelCostFinanceM",
    "devExclusivePyeong", "devExclusiveRate", "devRoomCount", "devRoomAreaSqm",
    "costPerRoomM",
    "adr10k", "adrTier", "adrMultiplier", "adrBase10k", "hotelHub", "hotelHubDistanceM",
    "occupancy", "fnbRatio", "gopRatio",
    "roomRevenueAnnualM", "fnbRevenueAnnualM", "totalRevenueAnnualM",
    "gopAnnualM", "annualRevM", "gopYield",
    # 오피스
    "officeClass", "officeMarket", "officeCore", "officeCoreDistanceM",
    "officeCapRate", "officeNoiAnnualM",
    "officeCostTotalM", "officeCostConstructionM", "officeCostIncidentalM",
    "officeCostFinanceM", "officeExclusivePyeong", "officeLeasablePyeong", "officeNoc10k",
    "officeVacancy", "officeRevenueAnnualM", "officeOpexAnnualM", "officeExitCap",
    # 표시 필터
    "isShown", "shownReason",
)

DEV_USES = ("hotel", "office", "best")


def _dev_costs(purchase_M: float, construction_M: float, a: DevAssumptions) -> tuple[float, float, float]:
    """(부대비용, 금융비, 총개발비) — 백만원. 금융비 = 대출 × 금리 × 대출기간."""
    incidental = (purchase_M + construction_M) * a.incidental_rate
    finance = (purchase_M + construction_M + incidental) * a.ltv * a.interest_rate * a.loan_years
    return incidental, finance, purchase_M + construction_M + incidental + finance


def _hotel_metrics(out: dict, a: DevAssumptions, purchase_M: float,
                   above_py: float, dev_total_py: float) -> None:
    grade = a.determine_grade(dev_total_py)
    profile = a.profile_for(grade)
    if profile is None:
        out["hotelGrade"] = "등급외"  # 호텔 부적합 (연면적 임계 미만)
        return
    out["hotelGrade"] = f"{grade}성급"

    # 전용 + 객실 수
    exclusive_py = above_py * profile.exclusive_ratio
    room_area_py = profile.room_area_sqm * a.sqm_to_pyeong
    n_rooms = int(exclusive_py / room_area_py) if room_area_py else 0
    out["devExclusivePyeong"] = round(exclusive_py, 2)
    out["devExclusiveRate"] = round(exclusive_py / dev_total_py, 4) if dev_total_py else None
    out["devRoomCount"] = n_rooms
    out["devRoomAreaSqm"] = profile.room_area_sqm

    construction = dev_total_py * profile.construction_cost_per_pyeong_M
    incidental, finance, cost_total = _dev_costs(purchase_M, construction, a)
    out["hotelCostConstructionM"] = round(construction, 2)
    out["hotelCostIncidentalM"] = round(incidental, 2)
    out["hotelCostFinanceM"] = round(finance, 2)
    out["hotelCostTotalM"] = round(cost_total, 2)
    out["costPerRoomM"] = round(cost_total / n_rooms, 2) if n_rooms else None

    # ADR 위치 프리미엄 — 등급 profile의 ADR은 Tier 1(마포/종로/중구/강남) 기준.
    # 숙박 수요 거점 반경 밖이면 보정율을 낮춘다.
    adr_mult, adr_tier, hub, hub_dist = hotel_location(
        out.get("divisionName"), out.get("latitude"), out.get("longitude"),
        a.hotel_hub_radius_m, a.hotel_off_hub_adr_step,
    )
    effective_adr = profile.adr_10k * adr_mult
    out["hotelHub"] = hub
    out["hotelHubDistanceM"] = round(hub_dist) if hub_dist is not None else None

    # 매출 (만원/년 → 백만원)
    room_rev_10k = effective_adr * profile.occupancy * 365 * n_rooms
    fnb_rev_10k = room_rev_10k * profile.fnb_ratio
    total_rev_M = (room_rev_10k + fnb_rev_10k) / 100
    gop_M = total_rev_M * profile.gop_ratio

    out["adr10k"] = round(effective_adr, 2)
    out["adrTier"] = adr_tier
    out["hotelExitCap"] = HOTEL_EXIT_CAP_BY_TIER.get(adr_tier, 0.060)
    out["adrMultiplier"] = round(adr_mult, 2)
    out["adrBase10k"] = profile.adr_10k
    out["occupancy"] = profile.occupancy
    out["fnbRatio"] = profile.fnb_ratio
    out["gopRatio"] = profile.gop_ratio
    out["roomRevenueAnnualM"] = round(room_rev_10k / 100, 2)
    out["fnbRevenueAnnualM"] = round(fnb_rev_10k / 100, 2)
    out["totalRevenueAnnualM"] = round(total_rev_M, 2)
    out["annualRevM"] = round(total_rev_M, 2)
    out["gopAnnualM"] = round(gop_M, 2)

    # NOI = GOP − 운영사 fee − 재산세·보험 − FF&E reserve
    noi_M = (
        gop_M
        - total_rev_M * a.mgmt_fee_base
        - gop_M * a.mgmt_fee_incentive
        - cost_total * a.property_tax_rate
        - total_rev_M * a.ff_e_reserve
    )
    out["hotelNoiAnnualM"] = round(noi_M, 2)
    out["hotelCapRate"] = round(noi_M / cost_total, 4) if cost_total else None
    out["gopYield"] = round(gop_M / cost_total, 4) if cost_total else None


def _office_metrics(out: dict, a: DevAssumptions, purchase_M: float,
                    above_py: float, dev_total_py: float) -> None:
    o = a.office
    if dev_total_py < o.min_total_pyeong:
        return
    market_name, core, core_dist = office_location(
        out.get("divisionName"), out.get("sectorName"),
        out.get("latitude"), out.get("longitude"), a.office_core_radius_m,
    )
    mkt = o.market(market_name)

    exclusive_py = dev_total_py * o.exclusive_ratio
    leasable_py = dev_total_py                     # 임대면적 = 전용 ÷ 전용률 = 연면적
    # 만원/년 → 백만원
    rent_rev_M = exclusive_py * mkt.noc_10k * 12 * (1 - mkt.vacancy) / 100
    opex_M = leasable_py * o.opex_10k_per_pyeong * 12 / 100
    noi_M = rent_rev_M - opex_M

    construction = dev_total_py * o.construction_cost_per_pyeong_M
    incidental, finance, cost_total = _dev_costs(purchase_M, construction, a)

    out["officeClass"] = o.size_class(dev_total_py)
    out["officeMarket"] = market_name
    out["officeCore"] = core
    out["officeCoreDistanceM"] = round(core_dist) if core_dist is not None else None
    out["officeExclusivePyeong"] = round(exclusive_py, 2)
    out["officeLeasablePyeong"] = round(leasable_py, 2)
    out["officeNoc10k"] = mkt.noc_10k
    out["officeVacancy"] = mkt.vacancy
    out["officeExitCap"] = mkt.exit_cap
    out["officeRevenueAnnualM"] = round(rent_rev_M, 2)
    out["officeOpexAnnualM"] = round(opex_M, 2)
    out["officeCostConstructionM"] = round(construction, 2)
    out["officeCostIncidentalM"] = round(incidental, 2)
    out["officeCostFinanceM"] = round(finance, 2)
    out["officeCostTotalM"] = round(cost_total, 2)
    out["officeNoiAnnualM"] = round(noi_M, 2)
    out["officeCapRate"] = round(noi_M / cost_total, 4) if cost_total else None


def select_use(out: dict, use: str) -> dict:
    """호텔/오피스 결과 중 하나를 골라 공통 필드(capRate, costTotalM …)에 기록.

    use = "hotel" | "office" | "best".
    best(최유효이용)는 호텔·오피스 신축 가능 용도지역에서만, 취득 Cap
    (NOI ÷ 총사업비)이 높은 쪽.
    선택 불가면 devUse=None (시뮬 대상 아님).
    """
    hotel_ok = out.get("hotelCapRate") is not None
    office_ok = out.get("officeCapRate") is not None
    if use == "hotel":
        chosen = "hotel" if hotel_ok else None
    elif use == "office":
        chosen = "office" if office_ok else None
    else:
        options = []
        if out.get("devZoneOk"):
            if hotel_ok:
                options.append(("hotel", out["hotelCapRate"]))
            if office_ok:
                options.append(("office", out["officeCapRate"]))
        chosen = max(options, key=lambda x: x[1])[0] if options else None

    out["devUse"] = chosen
    if chosen is None:
        out["devClass"] = None
        for k in ("capRate", "noiAnnualM", "costConstructionM", "costIncidentalM",
                  "costFinanceM", "costTotalM", "costPerPyeongM", "exitCap"):
            out[k] = None
        return out

    p = chosen  # "hotel" / "office" 필드 prefix
    out["devClass"] = out["hotelGrade"] if chosen == "hotel" else out["officeClass"]
    out["capRate"] = out[f"{p}CapRate"]
    out["noiAnnualM"] = out[f"{p}NoiAnnualM"]
    out["costConstructionM"] = out[f"{p}CostConstructionM"]
    out["costIncidentalM"] = out[f"{p}CostIncidentalM"]
    out["costFinanceM"] = out[f"{p}CostFinanceM"]
    out["costTotalM"] = out[f"{p}CostTotalM"]
    dev_total_py = out.get("devTotalPyeong")
    out["costPerPyeongM"] = (
        round(out["costTotalM"] / dev_total_py, 3) if dev_total_py else None
    )
    out["exitCap"] = out[f"{p}ExitCap"]   # DCF 매각가치 산정용 (가정)
    return out


def compute_dev_metrics(article: dict, assumptions: DevAssumptions, use: str = "hotel") -> dict:
    """평탄화된 article에 호텔·오피스 개발 시뮬 컬럼을 추가하여 반환.

    필요한 입력 필드:
      landSpace      대지면적 (㎡)
      floorSpace     현재 연면적 (㎡) — 평당가 계산에만 사용
      dealPrice      매매가 (만원, naver 원본 단위)
      regZoning      용도지역 → 최대 용적률 lookup

    호텔(hotel*)과 오피스(office*) 결과를 모두 계산한 뒤 `use`에 따라 공통
    필드(capRate, costTotalM, devUse, devClass …)를 채운다.
    입력 article은 캐시된 원본일 수 있으므로 절대 수정하지 않는다.
    """
    a = assumptions
    out: dict[str, Any] = dict(article)
    for k in _METRIC_KEYS:
        out[k] = None

    land_sqm = _safe_num(article.get("landSpace"))
    floor_sqm = _safe_num(article.get("floorSpace"))
    deal_price_10k = _safe_num(article.get("dealPrice"))

    # maxFar는 FAR_BY_ZONING 갱신을 반영하도록 매번 새로 lookup.
    # 한양도성 안 상업지역은 역사도심 조례 용적률(max_far_seoul_core)을 쓴다.
    fresh_max_far, fresh_max_far_seoul = lookup_far(article.get("regZoning"))
    out["inHistoricCore"] = is_in_historic_core(article.get("latitude"), article.get("longitude"))
    if fresh_max_far is not None:
        out["maxFar"] = fresh_max_far
        out["maxFarSeoulCore"] = fresh_max_far_seoul
        if out["inHistoricCore"] and fresh_max_far_seoul:
            out["maxFar"] = fresh_max_far_seoul
    max_far_pct = _safe_num(out.get("maxFar"))
    out["devZoneOk"] = is_dev_zone(article.get("regZoning"))

    if land_sqm:
        out["landPyeong"] = round(land_sqm * a.sqm_to_pyeong, 2)
    if floor_sqm:
        out["totalPyeong"] = round(floor_sqm * a.sqm_to_pyeong, 2)

    deal_price_M = deal_price_10k / 100  # 만원 → 백만원
    if out["landPyeong"] and deal_price_M:
        out["landPerPyeongM"] = round(deal_price_M / out["landPyeong"], 2)
    if out["totalPyeong"] and deal_price_M:
        out["bldgPerPyeongM"] = round(deal_price_M / out["totalPyeong"], 2)

    # 핵심 입력 검증
    if not (out["landPyeong"] and deal_price_M and max_far_pct):
        return select_use(out, use)

    # 개발 규모 (평): 지하 = 대지 × basement_ratio, 지상 = 대지 × 용적률
    land_py = out["landPyeong"]
    basement_py = land_py * a.basement_ratio
    above_py = land_py * max_far_pct / 100
    dev_total_py = basement_py + above_py
    out["devBasementPyeong"] = round(basement_py, 2)
    out["devAbovePyeong"] = round(above_py, 2)
    out["devTotalPyeong"] = round(dev_total_py, 2)
    out["costPurchaseM"] = round(deal_price_M, 2)

    _hotel_metrics(out, a, deal_price_M, above_py, dev_total_py)
    _office_metrics(out, a, deal_price_M, above_py, dev_total_py)
    return select_use(out, use)


def data_issue(article: dict, assumptions: DevAssumptions) -> str | None:
    """매물 자체의 데이터 이상 사유 (없으면 None). compute_dev_metrics 결과를 받는다.

    단일 매물 표시 여부와, 통합그룹에 합산할 멤버 선별에 같은 기준을 쓴다 —
    호가·면적이 잘못된 필지가 합필에 섞이면 그룹 전체 Cap이 부풀려진다.
    """
    lpp = _safe_num(article.get("landPerPyeongM"))
    if lpp and (
        lpp < assumptions.min_land_per_pyeong_M
        or lpp > assumptions.max_land_per_pyeong_M
    ):
        return f"평당가 이상치 ({lpp:.0f} 백만/평)"

    # 상업지역인데 토지 평당가가 지나치게 낮음 → 대지면적·호가 입력 오류 (예: ㎡·평 뒤바뀜)
    zoning = normalize_zoning(article.get("regZoning")) or ""
    if lpp and "상업지역" in zoning and lpp < assumptions.min_commercial_land_per_pyeong_M:
        return f"상업지역 평당가 이상치 ({lpp:.0f} 백만/평)"

    if article.get("isCombinedDevelopment"):
        return None

    # 건물 평당가가 비정상적으로 낮음 → 큰 건물의 호실·지분만 올라온 매물
    bpp = _safe_num(article.get("bldgPerPyeongM"))
    if bpp and bpp < assumptions.min_bldg_per_pyeong_M:
        return f"호실·지분 매물 의심 (건물 {bpp:.1f} 백만/평)"

    # 대지면적이 소재 필지보다 훨씬 작음 → 단지·집합건물의 대지지분
    land, parcel = _safe_num(article.get("landSpace")), _safe_num(article.get("parcelAreaM2"))
    if land and parcel and land < parcel * assumptions.min_parcel_share:
        return f"대지지분 매물 의심 (대지 {land:.0f}㎡ / 필지 {parcel:.0f}㎡)"
    return None


def existing_gfa_sqm(article: dict) -> float:
    """현재 건물 연면적 추정 (㎡). 없으면 0.

    매물에 적힌 연면적과 건축물대장 용적률로 역산한 지상 연면적(대지 × 용적률) 중 큰 값.
    매물 연면적이 실제보다 작게 올라온 경우(일부 층·전용면적만 기재)를 보완한다.
    통합그룹은 API가 멤버 합계를 existingGfaSqm으로 넣어 준다.
    """
    pre = _safe_num(article.get("existingGfaSqm"))
    if pre:
        return pre
    floor = _safe_num(article.get("floorSpace"))
    land, far = _safe_num(article.get("landSpace")), _safe_num(article.get("regFloorAreaRatio"))
    by_far = land * far / 100 if land and 0 < far <= 1500 else 0.0
    return max(floor, by_far)


def redevelopment_issue(article: dict, assumptions: DevAssumptions, as_member: bool = False) -> str | None:
    """철거 후 신축이 성립하지 않는 사유 (없으면 None). 단일 매물·통합그룹 대상.

    as_member=True는 합필에 넣을 필지를 고를 때 — 작은 필지의 낡은 건물은 제 필지
    기준으로는 꽉 차 보여도 합필 대상이 되므로, 제 필지 용적을 다 채운 건물(100% 이상)과
    신축만 뺀다. 합친 뒤의 실익은 그룹 단위로 다시 본다.
    """
    existing = existing_gfa_sqm(article) * assumptions.sqm_to_pyeong
    dev = _safe_num(article.get("devTotalPyeong"))
    if not existing or not dev:
        return None
    ratio = existing / dev
    if ratio >= (1.0 if as_member else assumptions.max_existing_gfa_ratio):
        return f"현재 건물이 이미 개발 가능 연면적의 {ratio:.0%} (신축 실익 부족)"
    if article.get("isCombinedDevelopment"):
        return None
    age = _num_or_none(article.get("approvalElapsedYear"))
    if (age is not None and age < assumptions.new_building_years
            and ratio >= assumptions.new_building_gfa_ratio):
        return f"준공 {age:.0f}년차 건물이 개발 가능 연면적의 {ratio:.0%} 사용 중 (철거 실익 부족)"
    return None


def apply_show_filter(article: dict, assumptions: DevAssumptions, any_use: bool = False) -> dict:
    """isShown 결정.

    any_use=True면 선택된 용도와 무관하게 호텔·오피스 중 하나라도 시뮬 가능하면
    통과 (파이프라인 단계 — 대시보드에서 용도를 바꿔도 필지 polygon이 있도록).

    isShown=True 조건 (둘 중 하나):
      A. **선택된 용도(devUse)로 시뮬 가능** — 호텔 등급 또는 오피스 규모 충족,
         landPyeong이 max_land_pyeong 이하
      B. **통합개발 그룹의 멤버** — 자기 단독은 시뮬 불가라도 그룹의 일부로
         의미 있음 (`partOfGroup`이 있으면)

    가상 통합 매물(`isCombinedDevelopment=True`)은 A 조건만 적용.
    토지 평당가가 min/max_land_per_pyeong_M 밖이면 데이터 오류로 보고 제외.
    """
    dev_class = article.get("devClass")
    land_py = article.get("landPyeong") or 0
    part_of_group = article.get("partOfGroup")
    if any_use:
        is_eligible = (article.get("hotelCapRate") is not None
                       or article.get("officeCapRate") is not None)
    else:
        is_eligible = article.get("devUse") is not None
    is_within_land = land_py <= assumptions.max_land_pyeong

    article["isCombinedDevelopment"] = article.get("isCombinedDevelopment", False)

    # 대지면적 이상치는 무조건 제외 (단독이든 멤버든 합산 매물이든)
    if land_py and not is_within_land:
        article["isShown"] = False
        article["shownReason"] = f"대지면적 초과 ({land_py:.0f}평 > {assumptions.max_land_pyeong:.0f}평)"
        return article

    # 평당가 이상치 · 호실/지분 매물 — 단일·멤버·통합그룹 공통
    issue = data_issue(article, assumptions)
    if issue:
        article["isShown"] = False
        article["shownReason"] = issue
        return article

    # 통합 그룹의 멤버는 자기 단독 등급 무관하게 표시
    if part_of_group and not article["isCombinedDevelopment"]:
        article["isShown"] = True
        article["shownReason"] = f"{part_of_group} 멤버 ({dev_class or '단독 시뮬 불가'})"
        return article

    if not is_eligible:
        article["isShown"] = False
        article["shownReason"] = article.get("hotelGrade") or "시뮬 불가"
        return article

    # 이미 꽉 채워 지어졌거나 갓 지은 건물 → 개발 후보가 아님
    issue = redevelopment_issue(article, assumptions)
    if issue:
        article["isShown"] = False
        article["shownReason"] = issue
        return article

    article["isShown"] = True
    article["shownReason"] = dev_class
    return article


def _safe_num(v) -> float:
    """None이나 비숫자면 0.0 반환 (컬럼 누락에 안전)."""
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _num_or_none(v) -> float | None:
    """숫자면 float, 없거나 비숫자면 None (0과 결측을 구분해야 할 때)."""
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _won_to_10k(v) -> int:
    """원 단위 → 만원 단위. fin.land가 priceInfo를 원 단위로 응답하므로
    flatten 단계에서 변환해서 저장 (이후 코드는 모두 만원 가정)."""
    try:
        return int(round(float(v) / 10000)) if v else 0
    except (TypeError, ValueError):
        return 0


# ── 한글 컬럼 라벨 ───────────────────────────────────────────────────────
COLUMN_LABELS_KO: dict[str, str] = {
    # 기본
    "articleNo": "매물번호",
    "name": "매물명",
    "tradeType": "거래유형",
    "realEstateType": "유형코드",
    # 가격
    "dealPrice": "매매가(만원)",
    "warrantyPrice": "보증금(만원)",
    "rentPrice": "월세(만원)",
    # 면적
    "supplySpace": "공급면적(㎡)",
    "exclusiveSpace": "전용면적(㎡)",
    "landSpace": "대지면적(㎡)",
    "floorSpace": "연면적(㎡)",
    # 주소
    "cityName": "시도",
    "divisionName": "구",
    "sectorName": "동",
    "latitude": "위도",
    "longitude": "경도",
    "pnu": "PNU코드",
    # 층
    "floorInfo": "층정보",
    "groundTotalFloor": "지상층수",
    "undergroundTotalFloor": "지하층수",
    # 메타
    "articleFeatureDescription": "특징요약",
    "approvalDateRaw": "사용승인일(매물)",
    "approvalElapsedYear": "경과연수",
    "thumbnailUrl": "대표사진URL",
    # 중개업소 (기본)
    "brokerageName": "중개업소명",
    "brokerName": "대표자",
    # 중개업소 (디테일)
    "agentBrokerageName": "중개업소명(상세)",
    "agentBrokerName": "대표자(상세)",
    "agentAddress": "중개업소주소",
    "agentBusinessNo": "사업자등록번호",
    "agentPhone": "중개업소전화",
    # 건축물대장
    "regBuildingName": "건물명(대장)",
    "regRoadAddress": "도로명주소(대장)",
    "regStructure": "구조(대장)",
    "regBuildingUse": "주용도(대장)",
    "regUseApprovalDate": "사용승인일(대장)",
    "regHouseholdNumber": "세대수(대장)",
    "regElevatorCount": "엘리베이터수(대장)",
    "regFloorAreaRatio": "용적률(%)",
    "regBuildingCoverageRatio": "건폐율(%)",
    "regTotalParkingCount": "총주차대수",
    "regZoning": "용도지역",
    "regDistrict": "지구",
    # 명목 용적률 (조례 기준)
    "maxFar": "최대용적률(조례)",
    "maxFarSeoulCore": "역사도심_용적률",
    "inHistoricCore": "역사도심(한양도성 안)",
    # ── 호텔 개발 시뮬레이션 ────────────────────────────────────────────
    "landPyeong": "대지면적(평)",
    "totalPyeong": "연면적(평)",
    "landPerPyeongM": "토지평당가(백만원/평)",
    "bldgPerPyeongM": "건물평당가(백만원/평)",
    # 등급 + 규모
    "hotelGrade": "호텔등급",
    "devBasementPyeong": "개발_지하면적(평)",
    "devAbovePyeong": "개발_지상면적(평)",
    "devTotalPyeong": "개발_연면적(평)",
    "devExclusivePyeong": "개발_전용면적(평)",
    "devExclusiveRate": "개발_전용율",
    "devRoomCount": "객실수",
    "devRoomAreaSqm": "객실면적(㎡)",
    # 비용
    "costPurchaseM": "매입비(백만)",
    "costConstructionM": "공사비(백만)",
    "costIncidentalM": "부대비용(백만)",
    "costFinanceM": "금융비(백만)",
    "costTotalM": "총개발비(백만)",
    "costPerPyeongM": "개발평단가(백만/평)",
    "costPerRoomM": "객실당개발비(백만/실)",
    # 매출/수익 (등급별)
    "adr10k": "ADR(만원, Tier보정)",
    "adrTier": "ADR_Tier(1~4)",
    "adrMultiplier": "ADR_보정율",
    "adrBase10k": "ADR_기준(만원)",
    "occupancy": "Occupancy",
    "fnbRatio": "F&B비율",
    "gopRatio": "GOP마진",
    "roomRevenueAnnualM": "객실매출_년(백만)",
    "fnbRevenueAnnualM": "F&B매출_년(백만)",
    "totalRevenueAnnualM": "총매출_년(백만)",
    "gopAnnualM": "GOP_년(백만)",
    "noiAnnualM": "NOI_년(백만)",
    "annualRevM": "년매출(백만)",
    "capRate": "Cap Rate(NOI/총개발비)",
    "gopYield": "GOP Yield(GOP/총개발비)",
    # 표시 / 통합개발 플래그
    "isShown": "표시여부",
    "isCombinedDevelopment": "통합개발",
    "shownReason": "표시기준",
    "groupSize": "통합필지수",
    "groupMemberArticles": "통합매물번호목록",
    "partOfGroup": "소속통합그룹",
    # 개발 정보 (지구단위계획 + 미래 역세권)
    "devJiguCount": "지구개수",
    "devJiguPrimaryName": "지구단위계획구역",
    "devJiguPrimaryType": "지구종류",
    "devJiguPrimaryStep": "지구진행단계",
    "devJiguAllNames": "지구목록전체",
    "devRailCount": "미래역_개수",
    "devNearestRailStation": "최근접_미래역",
    "devNearestRailLine": "최근접_미래노선",
    "devNearestRailDistanceM": "최근접_미래역_거리(m)",
    "devNearestRailWalkMin": "최근접_미래역_도보(분)",
    "devNearestRailOpenDate": "최근접_미래역_개통예정",
    "devRailSummary": "미래역_요약",
}


def translate_keys(article: dict) -> dict:
    return {COLUMN_LABELS_KO.get(k, k): v for k, v in article.items()}
