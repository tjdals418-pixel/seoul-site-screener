from __future__ import annotations

"""인접 매물 그룹화 (통합개발 시뮬용).

같은 동(`sectorName`) + 같은 용도지역(`regZoning`) + 좌표 거리 임계 이내 매물
끼리 union-find로 묶은 뒤, 그룹의 합산 대지면적/매매가/좌표중심으로 가상
'통합개발' 매물을 만든다. 이 가상 매물은 simulate 단계에서 일반 매물과 똑같이
`compute_dev_metrics`를 통과하게 된다.

왜 같은 (sector, zoning) 버킷 안에서만? — 도로 하나 사이로도 zoning이
바뀔 수 있고, 다른 zoning 매물끼리는 통합개발이 사실상 불가능하기 때문.
"""

from collections import defaultdict
from typing import Iterable

from naver_crawler.logging_setup import get_logger

log = get_logger(__name__)

# 위·경도 1° 당 미터 (서울 위도 ≈ 37.5° 기준)
_LAT_M_PER_DEG = 111_000.0
_LON_M_PER_DEG = 88_900.0


def _coord_distance_m(a: dict, b: dict) -> float:
    """두 article의 (latitude, longitude) 사이 직선거리(m). 평면 근사."""
    try:
        dlat = (float(a["latitude"]) - float(b["latitude"])) * _LAT_M_PER_DEG
        dlon = (float(a["longitude"]) - float(b["longitude"])) * _LON_M_PER_DEG
    except (KeyError, TypeError, ValueError):
        return float("inf")
    return (dlat * dlat + dlon * dlon) ** 0.5


def find_adjacent_groups(
    articles: list[dict],
    *,
    max_distance_m: float = 50.0,
    duplicate_distance_m: float = 5.0,
    max_centroid_distance_m: float = 60.0,
) -> list[list[int]]:
    """`articles` 중 같은 (sector, zoning) + 좌표거리 ≤ max_distance_m 이면
    같은 그룹으로 묶음. 2개 이상인 그룹의 인덱스 리스트만 반환.

    그룹 내에서 좌표거리 ≤ `duplicate_distance_m` 매물은 같은 땅으로 보고
    하나만 남김 (네이버에 동일 매물이 다른 articleNo로 여러 번 등록되는
    경우 대응). 가격 가장 낮은 매물(또는 articleNo 작은 매물) 선택.

    `max_centroid_distance_m` 으로 union-find의 chain 효과 방지:
      A↔B 인접 + B↔C 인접 + A↔C 멀리 인 경우 union이 셋을 묶지만,
      그룹 centroid에서 너무 먼 멤버는 제외 → 진짜 밀집한 매물만 그룹.
    """
    # (sector, zoning) 버킷
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for i, a in enumerate(articles):
        sec = a.get("sectorName")
        zoning = a.get("regZoning")
        lat = a.get("latitude")
        lon = a.get("longitude")
        if sec and zoning and lat is not None and lon is not None:
            buckets[(sec, zoning)].append(i)

    # union-find
    parent = list(range(len(articles)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for indices in buckets.values():
        if len(indices) < 2:
            continue
        # O(N²) within bucket; OK because buckets stay small (한 동 안 매물 수십~수백)
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                if _coord_distance_m(articles[indices[i]], articles[indices[j]]) <= max_distance_m:
                    union(indices[i], indices[j])

    raw_groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(articles)):
        raw_groups[find(i)].append(i)

    # 그룹 내 중복 제거 + centroid 거리 정제 (chain 효과 방지)
    deduped_groups: list[list[int]] = []
    for group in raw_groups.values():
        if len(group) < 2:
            continue
        kept = _dedupe_within_group(group, articles, duplicate_distance_m)
        if len(kept) < 2:
            continue
        # centroid 거리 제한 — 외곽 매물 제거
        refined = _refine_by_centroid(kept, articles, max_centroid_distance_m)
        if len(refined) >= 2:
            deduped_groups.append(refined)
    return deduped_groups


def _refine_by_centroid(
    indices: list[int],
    articles: list[dict],
    max_centroid_distance_m: float,
    *,
    max_iterations: int = 5,
) -> list[int]:
    """그룹 centroid에서 max_centroid_distance_m 초과 멤버 반복 제거.

    iterative한 이유: 멀리 있는 outlier 1개가 centroid를 끌어당기므로 한 번에
    못 제거. outlier 제외 후 centroid 다시 계산 → 또 outlier 검사 → ...
    더 이상 outlier 없을 때까지 (최대 5회).
    """
    current = list(indices)
    for _ in range(max_iterations):
        if len(current) < 2:
            break
        lats = [float(articles[i].get("latitude") or 0) for i in current]
        lons = [float(articles[i].get("longitude") or 0) for i in current]
        cy = sum(lats) / len(lats)
        cx = sum(lons) / len(lons)

        kept = []
        removed = False
        for i in current:
            a = articles[i]
            try:
                dy = (float(a["latitude"]) - cy) * _LAT_M_PER_DEG
                dx = (float(a["longitude"]) - cx) * _LON_M_PER_DEG
            except (KeyError, TypeError, ValueError):
                continue
            if (dy * dy + dx * dx) ** 0.5 <= max_centroid_distance_m:
                kept.append(i)
            else:
                removed = True
        current = kept
        if not removed:
            break
    return current


def _dedupe_within_group(
    indices: list[int],
    articles: list[dict],
    duplicate_distance_m: float,
) -> list[int]:
    """그룹 내에서 좌표가 거의 같은 매물 묶고 그 중 1개만 선택.
    선택 기준: dealPrice 낮은 매물 우선 (싸게 잡을 수 있는 매물). 동률이면
    articleNo 사전순 (안정적).
    """
    # 클러스터링
    clusters: list[list[int]] = []
    used = set()
    for idx in indices:
        if idx in used:
            continue
        cluster = [idx]
        used.add(idx)
        for j in indices:
            if j in used:
                continue
            if _coord_distance_m(articles[idx], articles[j]) <= duplicate_distance_m:
                cluster.append(j)
                used.add(j)
        clusters.append(cluster)

    # 각 클러스터에서 대표 1개 선택
    chosen = []
    for cluster in clusters:
        if len(cluster) == 1:
            chosen.append(cluster[0])
            continue
        cluster.sort(key=lambda i: (
            articles[i].get("dealPrice") or float("inf"),
            str(articles[i].get("articleNo") or ""),
        ))
        chosen.append(cluster[0])
    return chosen


def make_combined_article(
    member_indices: list[int],
    articles: list[dict],
    group_no: int,
) -> dict:
    """그룹 합산 가상 매물. enriched 형태와 호환되어 compute_dev_metrics가
    그대로 처리할 수 있도록 같은 키 셋을 채워 넣음."""
    members = [articles[i] for i in member_indices]
    n = len(members)

    sum_deal_price = sum(_safe_num(m.get("dealPrice")) for m in members)
    sum_land = sum(_safe_num(m.get("landSpace")) for m in members)
    sum_floor = sum(_safe_num(m.get("floorSpace")) for m in members)
    avg_lat = sum(_safe_num(m.get("latitude")) for m in members) / n
    avg_lon = sum(_safe_num(m.get("longitude")) for m in members) / n

    first = members[0]  # 같은 sector + zoning이라 대표값으로 OK
    member_ids = [m.get("articleNo") for m in members]
    total_billion_won = sum_deal_price / 10000  # 만원 → 억원

    # 멤버별 디테일 — 팝업에 매물별 매매가/대지/평당가 표시용 + 지도 점선용
    members_detail = []
    for m in members:
        land_sqm = _safe_num(m.get("landSpace"))
        deal_10k = _safe_num(m.get("dealPrice"))
        land_py = land_sqm * 0.3025
        # 평당가 (백만원/평) — 토지 기준
        land_per_pyeong_M = (deal_10k / 100) / land_py if land_py and deal_10k else None
        members_detail.append({
            "articleNo": m.get("articleNo"),
            "name": m.get("name") or m.get("realEstateType"),
            "dealPrice": deal_10k,                   # 만원
            "landSpace": land_sqm,                   # ㎡
            "landPyeong": round(land_py, 1) if land_py else None,
            "landPerPyeongM": round(land_per_pyeong_M, 1) if land_per_pyeong_M else None,
            "regRoadAddress": m.get("regRoadAddress") or "",
            "agentPhone": m.get("agentPhone") or "",
            # 지도 점선용 좌표
            "latitude": _safe_num(m.get("latitude")),
            "longitude": _safe_num(m.get("longitude")),
        })

    return {
        # 식별
        "articleNo": f"GROUP-{group_no}",
        "name": f"통합개발 ({n}필지)",
        "tradeType": "A1",
        "realEstateType": "GROUP",
        # 가격 / 면적 (합산)
        "dealPrice": sum_deal_price,
        "warrantyPrice": 0,
        "rentPrice": 0,
        "landSpace": sum_land,
        "floorSpace": sum_floor,
        "supplySpace": 0,
        "exclusiveSpace": 0,
        # 주소 / 좌표 (대표)
        "cityName": first.get("cityName"),
        "divisionName": first.get("divisionName"),
        "sectorName": first.get("sectorName"),
        "latitude": avg_lat,
        "longitude": avg_lon,
        # 용도지역 (대표)
        "regZoning": first.get("regZoning"),
        "regBuildingUse": first.get("regBuildingUse"),
        "regStructure": first.get("regStructure"),
        "regUseApprovalDate": "",
        "regHouseholdNumber": 0,
        "regElevatorCount": 0,
        "regFloorAreaRatio": None,
        "regBuildingCoverageRatio": None,
        "regTotalParkingCount": 0,
        "regBuildingName": f"GROUP-{group_no}",
        "regRoadAddress": "",
        "regDistrict": first.get("regDistrict"),
        # 명목 용적률 (그룹의 first 기준)
        "maxFar": first.get("maxFar"),
        "maxFarSeoulCore": first.get("maxFarSeoulCore"),
        # 평탄화 호환 필드 (없으면 export에서 빈칸)
        "pnu": "",
        "floorInfo": "",
        "groundTotalFloor": "",
        "undergroundTotalFloor": "",
        "approvalDateRaw": "",
        "approvalElapsedYear": "",
        "thumbnailUrl": "",
        "brokerageName": "",
        "brokerName": "",
        "agentBrokerageName": "",
        "agentBrokerName": "",
        "agentAddress": "",
        "agentBusinessNo": "",
        "agentPhone": "",
        # 그룹 메타 + 통합개발 플래그
        "isCombinedDevelopment": True,
        "groupSize": n,
        "groupMemberArticles": ",".join(str(x) for x in member_ids),
        "groupMembersDetail": members_detail,  # 팝업 세부 표시용
        "articleFeatureDescription": (
            f"인접 {n}개 매물 통합개발 (대지 {sum_land:.0f}㎡, 매매가 합 {total_billion_won:.0f}억)"
        ),
    }


def _safe_num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def expand_with_combined_articles(
    articles: list[dict],
    *,
    max_distance_m: float = 50.0,
    max_centroid_distance_m: float = 60.0,
) -> tuple[list[dict], list[dict]]:
    """원본 articles는 그대로 두고, 인접 그룹별 가상 매물을 별도 리스트로
    반환. 두 리스트는 호출자가 합쳐서 simulate에 넘기면 됨.

    Returns:
        (combined_articles, groups_meta)
        combined_articles: list of 가상 통합개발 매물
        groups_meta: 디버깅/통계용 — 각 그룹의 멤버 articleNo 리스트
    """
    groups = find_adjacent_groups(
        articles,
        max_distance_m=max_distance_m,
        max_centroid_distance_m=max_centroid_distance_m,
    )
    log.info(
        "adjacent groups: %d (총 %d 매물 묶음, max_distance=%.0fm, centroid_max=%.0fm)",
        len(groups), sum(len(g) for g in groups), max_distance_m, max_centroid_distance_m,
    )

    combined: list[dict] = []
    meta: list[dict] = []
    for i, g in enumerate(groups, start=1):
        combined.append(make_combined_article(g, articles, group_no=i))
        meta.append({
            "groupNo": i,
            "size": len(g),
            "members": [articles[idx].get("articleNo") for idx in g],
        })
    return combined, meta
