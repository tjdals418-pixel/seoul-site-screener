"""데이터 로더 + 시뮬 재계산.

매물 로드(로컬 simulated.json 또는 공개용 data/published) → DevAssumptions 적용
(transforms.compute_dev_metrics + apply_show_filter) → 통합그룹을 실제 필지
인접성 기준으로 재계산. 결과는 lru_cache로 메모리 캐시.
"""
from __future__ import annotations

import gzip
import json
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from naver_crawler.transforms import (
    DevAssumptions,
    apply_show_filter,
    compute_dev_metrics,
    data_issue,
    existing_gfa_sqm,
    rail_opened,
    redevelopment_issue,
    same_building_report,
)


# 프로젝트 루트 (api/app/data.py 기준 3단계 상위)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "interim" / "simulated.json"
PUBLIC_DATA_PATH = PROJECT_ROOT / "data" / "published" / "articles.json.gz"
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "snapshots"
CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"
GU_GEOJSON_PATH = PROJECT_ROOT / "reference" / "seoul_gu.geojson"
SUBWAY_LINES_PATH = PROJECT_ROOT / "reference" / "seoul_subway_lines.geojson"
SUBWAY_STATIONS_PATH = PROJECT_ROOT / "reference" / "seoul_subway_stations.geojson"


# 중개사/중개업소 정보는 API로 절대 내보내지 않는다 (개인정보).
_PRIVATE_KEY_PREFIXES = ("agent", "broker")


def strip_private(obj: Any) -> Any:
    """dict/list를 재귀 순회하며 agent*/broker* 키 제거 (그룹 멤버 중첩 포함)."""
    if isinstance(obj, dict):
        return {
            k: strip_private(v) for k, v in obj.items()
            if not k.lower().startswith(_PRIVATE_KEY_PREFIXES)
        }
    if isinstance(obj, list):
        return [strip_private(v) for v in obj]
    return obj


@lru_cache(maxsize=1)
def _load_payload() -> dict:
    """로컬 파이프라인 산출물(simulated.json) 우선, 없으면 공개용 데이터.

    공개용 데이터(`data/published/articles.json.gz`)는 scripts/export_public.py가
    만든 PII 제거·필드 축소본이며 git에 포함된다 (배포 환경의 유일한 데이터).
    """
    if DATA_PATH.exists():
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        payload.setdefault(
            "generatedAt",
            datetime.fromtimestamp(DATA_PATH.stat().st_mtime).strftime("%Y-%m-%d"),
        )
        return payload
    if PUBLIC_DATA_PATH.exists():
        with gzip.open(PUBLIC_DATA_PATH, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {}


_RAIL_KEYS = ("devNearestRailStation", "devNearestRailLine", "devNearestRailOpenDate",
              "devNearestRailDistanceM", "devNearestRailWalkMin", "devRailSummary")


def _drop_opened_rail(a: dict, as_of: str | None) -> None:
    """기준일 전에 이미 개통한 역은 '개통 예정 역'에서 뺀다 (원본에 옛 예정일이 남아 있음)."""
    if rail_opened(a.get("devNearestRailOpenDate"), as_of):
        for k in _RAIL_KEYS:
            a.pop(k, None)
    for m in a.get("groupMembersDetail") or []:
        _drop_opened_rail(m, as_of)


_JIGU_KEYS = ("devJiguPrimaryName", "devJiguPrimaryType", "devJiguPrimaryStep")


def _inherit_planning(group: dict, members: list[dict]) -> None:
    """합필 부지의 지구단위계획·개통 예정 역 — 구성 필지 값을 물려받는다.

    가상 매물이라 자체 값이 없어서, 그대로 두면 '지구단위계획구역만'·'개통 예정 역
    인근만' 필터에서 합필이 전부 빠지고 상세에도 표시되지 않는다.
    """
    with_jigu = next((m for m in members if str(m.get("devJiguPrimaryName") or "").strip()), None)
    if with_jigu:
        for k in _JIGU_KEYS:
            group[k] = with_jigu.get(k)
    with_rail = [m for m in members if str(m.get("devNearestRailStation") or "").strip()]
    if with_rail:
        nearest = min(with_rail, key=lambda m: m.get("devNearestRailDistanceM") or float("inf"))
        for k in _RAIL_KEYS:
            if k in nearest:
                group[k] = nearest[k]


@lru_cache(maxsize=1)
def load_raw_articles() -> tuple[dict, ...]:
    """매물 list (tuple로 immutable). 중개사 정보는 로드 시점에 제거."""
    as_of = data_as_of()
    out = []
    for a in _load_payload().get("articles") or []:
        a = strip_private(a)
        _drop_opened_rail(a, as_of)
        out.append(a)
    return tuple(out)


def data_as_of() -> str | None:
    """데이터 수집 기준일 (YYYY-MM-DD)."""
    return _load_payload().get("generatedAt")


@lru_cache(maxsize=1)
def load_config_assumptions() -> dict[str, Any]:
    """config/default.yaml의 dev_simulation 섹션 (API 기본 가정값의 source)."""
    if not CONFIG_PATH.exists():
        return {}
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return raw.get("dev_simulation") or {}


@lru_cache(maxsize=1)
def load_gu_boundaries() -> dict:
    """서울 자치구 경계 GeoJSON."""
    if not GU_GEOJSON_PATH.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(GU_GEOJSON_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_subway_lines() -> dict:
    """서울 지하철 노선 GeoJSON (MultiLineString features, 노선 색 포함)."""
    if not SUBWAY_LINES_PATH.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(SUBWAY_LINES_PATH.read_text(encoding="utf-8"))


def find_previous_snapshot(current_date: str | None) -> Path | None:
    """현재 데이터 기준일보다 *이전* 날짜의 가장 최근 snapshot 파일."""
    if not SNAPSHOTS_DIR.exists():
        return None
    snaps = sorted(SNAPSHOTS_DIR.glob("*.json"))
    if current_date:
        snaps = [s for s in snaps if s.stem < current_date]
    return snaps[-1] if snaps else None


def _listing_site(a: dict) -> dict | None:
    """스냅샷 간 같은 건물을 찾는 데 쓰는 값. 통합그룹이거나 필수값이 없으면 None."""
    if a.get("isCombinedDevelopment"):
        return None
    try:
        site = {
            "gu": str(a.get("divisionName")), "land": float(a["landSpace"]),
            "lat": float(a["latitude"]), "lon": float(a["longitude"]),
            "price": float(a["dealPrice"]), "floor": float(a.get("floorSpace") or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if site["land"] <= 0 or site["price"] <= 0:
        return None
    site["pnu"] = str(a.get("pnu") or "")
    site["road"] = str(a.get("regRoadAddress") or "")
    return site


def match_previous_prices(current: list[dict] | tuple[dict, ...], previous: list[dict],
                          max_distance_m: float = 30) -> dict[str, float]:
    """현재 매물번호 → 이전 스냅샷에서 같은 건물의 호가.

    이전 스냅샷에 없던 건물이면 키가 없고(= 신규), 같은 건물은 있었지만 비교할 만한
    호가가 없으면 0.0 (신규는 아님). 매물번호는 재등록될 때마다 바뀌어 스냅샷 사이에
    이어지지 않으므로 아래 순서로 같은 건물을 찾는다.
      1. 같은 자치구에서 좌표가 가깝고 대지면적이 같거나(±1㎡, 30m) 현재 연면적이
         같은(±1㎡, 50m) 매물 → 같은 조건의 매물로 보고 호가를 비교한다. 여러 건이면
         현재 호가와 가장 가까운 값 (중개사별 호가 차이를 변동으로 오인하지 않도록).
      2. 같은 PNU이거나 도로명주소가 같은 매물 → 같은 건물이지만 면적 기재가 달라진
         경우. 신규로 표시하지 않되, 매물 범위가 달라졌을 수 있어 호가는 비교하지 않는다.
    """
    Entry = tuple[float, float, float, float, float]   # 대지, 연면적, 위도, 경도, 호가
    by_land: dict[tuple[str, int], list[Entry]] = {}
    by_floor: dict[tuple[str, int], list[Entry]] = {}
    pnus: set[str] = set()
    roads: set[str] = set()
    for a in previous:
        site = _listing_site(a)
        if not site:
            continue
        entry = (site["land"], site["floor"], site["lat"], site["lon"], site["price"])
        by_land.setdefault((site["gu"], int(site["land"])), []).append(entry)
        if site["floor"] > 0:
            by_floor.setdefault((site["gu"], int(site["floor"])), []).append(entry)
        if site["pnu"]:
            pnus.add(site["pnu"])
        if site["road"]:
            roads.add(site["road"])

    def near(e: Entry, site: dict, limit_m: float) -> bool:
        return (((e[2] - site["lat"]) * 111_000) ** 2 + ((e[3] - site["lon"]) * 88_000) ** 2) ** 0.5 <= limit_m

    def lookup(index: dict[tuple[str, int], list[Entry]], site: dict, key: str, col: int,
               limit_m: float) -> list[Entry]:
        v = site[key]
        return [e for bucket in (int(v) - 1, int(v), int(v) + 1)
                for e in index.get((site["gu"], bucket), ())
                if abs(e[col] - v) <= 1.0 and near(e, site, limit_m)]

    matched: dict[str, float] = {}
    for a in current:
        site = _listing_site(a)
        if not site:
            continue
        same = lookup(by_land, site, "land", 0, max_distance_m)
        if site["floor"] > 0:
            same += lookup(by_floor, site, "floor", 1, 50)
        if same:
            matched[str(a.get("articleNo"))] = min((e[4] for e in same), key=lambda v: abs(v - site["price"]))
        elif (site["pnu"] and site["pnu"] in pnus) or (site["road"] and site["road"] in roads):
            matched[str(a.get("articleNo"))] = 0.0
    return matched


@lru_cache(maxsize=1)
def load_previous_snapshot() -> tuple[str | None, dict[str, float]]:
    """(이전 snapshot 날짜, 현재 매물번호 → 같은 건물의 이전 호가). 없으면 (None, {}).

    diff 비교용: 이전 스냅샷에 같은 건물이 없으면 NEW, 있으면 가격 변동률.
    공개 데이터는 export 시점에 계산해 둔 prevPrices를 그대로 쓴다.
    """
    payload = _load_payload()
    if payload.get("prevPrices"):
        return payload.get("prevSnapshotDate"), payload["prevPrices"]
    prev = find_previous_snapshot(data_as_of())
    if prev is None:
        return None, {}
    try:
        previous = json.loads(prev.read_text(encoding="utf-8")).get("articles") or []
    except (OSError, ValueError):
        return None, {}
    return prev.stem, match_previous_prices(load_raw_articles(), previous)


@lru_cache(maxsize=1)
def load_subway_stations() -> dict:
    """서울 지하철 역 GeoJSON (Point features, 한글/영문명)."""
    if not SUBWAY_STATIONS_PATH.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(SUBWAY_STATIONS_PATH.read_text(encoding="utf-8"))


# geo 변환 실패 통계 — /api/meta/data-quality로 노출 (silent skip 추적)
_GEO_STATS = {"skipped": 0, "total": 0}


def get_geo_stats() -> dict:
    """parcelPolygon → shapely 변환 실패 통계 (data-quality endpoint용)."""
    return dict(_GEO_STATS)


def _to_shapely(geom: dict | None, count_stats: bool = False):
    """GeoJSON dict → shapely Geometry. None / 잘못된 geom은 None.

    shapely.geometry.shape는 dict["type"]+dict["coordinates"]를 그대로 받음.
    실패(coordinates 결측, 잘못된 nesting 등)는 _GEO_STATS.skipped로 카운트.
    """
    if not geom:
        return None
    try:
        from shapely.geometry import shape
        return shape(geom)
    except Exception:
        if count_stats:
            _GEO_STATS["skipped"] += 1
        return None


# threshold ≈ 4m in WGS84 degrees (latitude). 좁은 골목(<4m) cross 방지.
# 1° latitude ≈ 111,000m → 0.000036° ≈ 4m.
#
# 한쪽 polygon만 buffer 후 intersects = "두 polygon 최단거리 ≤ 4m" — 도로 건너편
# 필지가 인접으로 잡히지 않도록 좁게 잡은 값.
_ADJACENCY_THRESHOLD_DEG = 0.000036
_CONNECTIVITY_LOCK = threading.Lock()


def compute_group_connectivity() -> dict[str, frozenset[str]]:
    """동시 첫 요청이 계산을 중복하지 않도록 lock 뒤에서 1회만 계산."""
    with _CONNECTIVITY_LOCK:
        return _compute_group_connectivity()


@lru_cache(maxsize=1)
def _compute_group_connectivity() -> dict[str, frozenset[str]]:
    """각 통합 그룹의 인접 멤버 set (가장 큰 connected component).

    Shapely + STRtree spatial index 사용으로 O(g²) → O(g log g).
    한쪽 polygon만 4m buffer → R-tree query로 인접 후보 추림 → 원본 polygon과
    intersects 확인. effective threshold = polygon 최단거리 4m (의도된 값).
    """
    _GEO_STATS.update(skipped=0, total=0)
    groups: dict[str, list[str]] = {}
    for a in load_raw_articles():
        if a.get("partOfGroup"):
            groups.setdefault(str(a.get("partOfGroup")), []).append(
                str(a.get("articleNo"))
            )
    return {gid: _largest_adjacent(member_aids, count_stats=True) for gid, member_aids in groups.items()}


@lru_cache(maxsize=1)
def _raw_by_aid() -> dict[str, dict]:
    return {str(a.get("articleNo")): a for a in load_raw_articles()}


def _largest_adjacent(member_aids: list[str], count_stats: bool = False) -> frozenset[str]:
    """주어진 매물들 중 서로 맞닿은(최단거리 4m 이내) 가장 큰 묶음. 2개 미만이면 빈 set.

    count_stats는 /api/meta/data-quality용 통계 — 최초 인접성 계산에서만 센다.
    """
    from shapely.strtree import STRtree

    by_aid = _raw_by_aid()
    # polygon load (원본 + 4m buffer 둘 다 보관)
    geoms: list = []          # 원본 polygon
    buffers: list = []        # 4m buffer (한쪽만)
    valid_aids: list[str] = []
    for aid in member_aids:
        a = by_aid.get(aid)
        if count_stats:
            _GEO_STATS["total"] += 1
        g = _to_shapely(a.get("parcelPolygon") if a else None, count_stats)
        if g is None or g.is_empty:
            continue
        geoms.append(g)
        buffers.append(g.buffer(_ADJACENCY_THRESHOLD_DEG))
        valid_aids.append(aid)

    if len(valid_aids) < 2:
        return frozenset()

    # R-tree는 원본 polygon으로 build, query는 buffer로 → 최단거리 ≤ 4m 후보
    tree = STRtree(geoms)
    adj: dict[str, set[str]] = {aid: set() for aid in member_aids}
    for i, g_buf in enumerate(buffers):
        # buffer가 닿는 원본 polygon 후보 (한쪽 buffer = 최단거리 4m semantic)
        candidates = tree.query(g_buf)
        for j in candidates:
            if j <= i:        # 무방향 → 한쪽만
                continue
            if g_buf.intersects(geoms[j]):
                a_i, a_j = valid_aids[i], valid_aids[j]
                adj[a_i].add(a_j)
                adj[a_j].add(a_i)

    # BFS connected components
    visited: set[str] = set()
    components: list[set[str]] = []
    for aid in member_aids:
        if aid in visited:
            continue
        comp: set[str] = set()
        stack = [aid]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            visited.add(cur)
            for nb in adj.get(cur, ()):
                if nb not in comp:
                    stack.append(nb)
        components.append(comp)
    largest = max(components, key=len, default=set())
    return frozenset(largest) if len(largest) >= 2 else frozenset()


def _dedupe_close_listings(articles: list[dict]) -> tuple[list[dict], set[str]]:
    """통합그룹 멤버 중 '같은 필지'를 중복 등재한 케이스 dedupe.

    parcels 단계의 면적 기반 re-snap으로 PNU가 정확해졌으므로 **PNU 기준**으로
    dedupe한다 — 같은 그룹 안에서 같은 PNU = 같은 필지 = 중복 → 가장 싼 매물만
    남김. 서로 다른 PNU는 인접한 별개 필지이므로 둘 다 유지 (예: 946-42 150억 ↔
    946-16 105억 — 붙어있는 다른 필지인데 옛 좌표+면적 휴리스틱이 중복 오판).

    PNU 없는 멤버는 fallback으로 좌표 30m + landSpace 5% 휴리스틱 적용.

    반환: (deduped articles, dropped articleNo set)
    """
    from collections import defaultdict

    members = [a for a in articles
               if a.get("partOfGroup") and not a.get("isCombinedDevelopment")]
    non_members = [a for a in articles
                   if not a.get("partOfGroup") or a.get("isCombinedDevelopment")]

    bucket: dict[tuple, list[int]] = defaultdict(list)
    for i, a in enumerate(members):
        key = (a.get("sectorName") or "", a.get("partOfGroup") or "")
        bucket[key].append(i)

    def price(i: int) -> float:
        return float(members[i].get("dealPrice") or 0)

    dropped: set[str] = set()
    for _, idxs in bucket.items():
        # 1) PNU 있는 멤버: 같은 PNU = 같은 필지 → 가장 싼 것만 keep
        by_pnu: dict[str, list[int]] = defaultdict(list)
        no_pnu: list[int] = []
        for i in idxs:
            pnu = members[i].get("pnu")
            if pnu:
                by_pnu[pnu].append(i)
            else:
                no_pnu.append(i)
        for _pnu, same in by_pnu.items():
            if len(same) <= 1:
                continue
            same.sort(key=price)  # 가장 싼 것 [0] 남기고 나머지 drop
            for i in same[1:]:
                dropped.add(str(members[i].get("articleNo")))

        # 2) PNU 없는 멤버: 좌표+면적 휴리스틱 (자기들끼리만)
        used: set[int] = set()
        for i in no_pnu:
            if i in used:
                continue
            a = members[i]
            land_a = float(a.get("landSpace") or 0)
            lat_a = a.get("latitude"); lon_a = a.get("longitude")
            if not (land_a and lat_a and lon_a):
                continue
            for j in no_pnu:
                if j <= i or j in used:
                    continue
                b = members[j]
                land_b = float(b.get("landSpace") or 0)
                lat_b = b.get("latitude"); lon_b = b.get("longitude")
                if not (land_b and lat_b and lon_b):
                    continue
                dlat = (lat_a - lat_b) * 111000
                dlon = (lon_a - lon_b) * 88000
                if (dlat * dlat + dlon * dlon) ** 0.5 > 30:
                    continue
                if abs(land_a - land_b) / max(land_a, land_b) > 0.05:
                    continue
                if price(j) >= price(i):
                    dropped.add(str(b.get("articleNo"))); used.add(j)
                else:
                    dropped.add(str(a.get("articleNo"))); used.add(i); break
    deduped_members = [m for m in members
                       if str(m.get("articleNo")) not in dropped]
    return non_members + deduped_members, dropped


@lru_cache(maxsize=1)
def _same_building_report() -> tuple[frozenset[str], frozenset[str]]:
    """같은 건물 중복 등재 → (지울 매물, 용도지역이 엇갈린 채 남긴 매물). 가정값과 무관해 1회만 계산."""
    dropped, zoning_conflict = same_building_report(load_raw_articles())
    return frozenset(dropped), frozenset(zoning_conflict)


def _same_building_duplicates() -> frozenset[str]:
    return _same_building_report()[0]


def build_assumptions(sim: dict[str, Any] | None = None) -> DevAssumptions:
    """config 기본값 위에 사용자 override(sim)를 덮어쓴 DevAssumptions.

    등급별 프로필(grade_3/4/5)은 키 단위로 병합 — 일부 값만 보내도 나머지는
    config 값 유지.
    """
    return DevAssumptions.from_config(_deep_merge(load_config_assumptions(), sim or {}))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """중첩 dict 병합 (office.markets.CBD.noc_10k처럼 일부만 바꿔도 나머지 유지)."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _percentile(values: list[float], p: float) -> float | None:
    """단순 분위수 — values sorted, p ∈ [0,1]."""
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
    return s[idx]


CAP_CHECK_THRESHOLD = 0.10   # 취득 Cap 10% 초과 → 호가·면적 재확인 권장
AREA_MISMATCH_RATIO = 1.5    # 매물 대지면적 ÷ 연결된 필지 면적이 이 배수 밖이면 '면적 확인' 표시


def _area_mismatch(a: dict) -> bool:
    """매물에 적힌 대지면적이 연결된 필지 면적과 크게 다르다.

    여러 필지를 묶은 매물(지도에는 한 필지만 그려진다)이거나 필지가 잘못 연결된 경우.
    절반 미만은 대지지분으로 보고 아예 제외하므로(data_issue) 여기 오는 건 그보다 덜한 불일치.
    """
    try:
        land, parcel = float(a.get("landSpace") or 0), float(a.get("parcelAreaM2") or 0)
    except (TypeError, ValueError):
        return False
    return bool(land and parcel) and not (1 / AREA_MISMATCH_RATIO <= land / parcel <= AREA_MISMATCH_RATIO)

# 이전 스냅샷의 같은 건물 호가와 비교
MIN_COMPARABLE_PRICE = 10000         # 1억(만원) 미만 호가는 비교 대상에서 제외 (입력 오류)
PRICE_TYPO_RATIO = 0.3               # 현재 호가가 이전의 30% 미만 → 자릿수 누락 등 입력 오류로 보고 제외
PRICE_CHANGE_RANGE = (0.5, 1.5)      # 이 범위 밖 변동은 같은 조건의 매물이 아니라고 보고 표시하지 않음


def _mark_outliers(articles: list[dict], p5_lpp: float | None,
                   zoning_conflict: frozenset[str] = frozenset()) -> None:
    """데이터 점검이 필요한 매물에 outlierFlags 마킹 (in-place).

    순위 상위권이 구조적으로 걸리지 않도록 분위수 대신 절대 기준을 쓴다
    (평당가 하한만 분위수 — 호가·면적 입력 오류가 주로 여기서 나옴).
    - landPerPyeongM < P5 → 'price_low'  (저평가 — 면적/가격 오기 의심)
    - capRate > 10%      → 'cap_high'   (서울 신축 기준으로 드문 수준)
    - 신축 불가 용도지역인데 시뮬됨 → 'zone_unfit' (호텔/오피스 단일 모드)
    - 같은 건물이 다른 용도지역으로도 등재됨 → 'zone_conflict' (용적률 낮은 쪽으로 계산)
    - 대지면적이 연결된 필지 면적과 1.5배 이상 다름 → 'area_mismatch' (합필은 구성 필지 중 하나라도)

    p5_lpp는 용도 모드와 무관한 모집단(신축 가능 용도지역의 개발 후보 전체)에서 구한
    값을 받는다 — 같은 매물의 표시가 모드에 따라 달라지지 않도록.
    """
    for a in articles:
        flags: list[str] = []
        lpp = a.get("landPerPyeongM")
        cr = a.get("capRate")
        if lpp is not None and p5_lpp is not None and lpp < p5_lpp:
            flags.append("price_low")
        if cr is not None and cr > CAP_CHECK_THRESHOLD:
            flags.append("cap_high")
        # 호텔/오피스 신축 불가 용도지역인데 시뮬된 매물 (hotel/office 단일 모드)
        if a.get("devUse") and not a.get("devZoneOk"):
            flags.append("zone_unfit")
        if str(a.get("articleNo")) in zoning_conflict:
            flags.append("zone_conflict")
        if a.get("isCombinedDevelopment"):
            raw_by_aid = _raw_by_aid()
            parcels = [raw_by_aid.get(str(m.get("articleNo")), m) for m in a.get("groupMembersDetail") or []]
        else:
            parcels = [a]
        if any(_area_mismatch(x) for x in parcels):
            flags.append("area_mismatch")
        if flags:
            a["outlierFlags"] = flags


def resim_articles(sim: dict[str, Any] | None = None, use: str = "best") -> list[dict]:
    """시뮬 가정값 + 개발 용도(hotel/office/best) 적용 → 시뮬 가능 매물만 +
    평당가 컷 + 통합그룹 metric을 실제 인접 필지 기준으로 재계산.
    """
    raw = load_raw_articles()
    if not raw:
        return []

    assumptions = build_assumptions(sim)
    group_conn = compute_group_connectivity()
    _prev_date, prev_prices = load_previous_snapshot()

    # 같은 건물 중복 등재 제거 — (1) 대지면적·좌표가 같고 호가·연면적·주소 등이 겹치는
    # 매물 (단일·멤버 모두), (2) 그룹 안의 같은 PNU. 제거된 멤버는 아래 그룹 재계산에서도 빠진다.
    same_building, zoning_conflict = _same_building_report()
    deduped_raw, dropped_aids = _dedupe_close_listings(
        [a for a in raw if str(a.get("articleNo")) not in same_building]
    )
    dropped_aids = dropped_aids | same_building

    def comparable_prev_price(a: dict) -> float | None:
        prev = prev_prices.get(str(a.get("articleNo")))
        return prev if prev and prev >= MIN_COMPARABLE_PRICE else None

    def price_typo(a: dict) -> bool:
        """같은 건물의 이전 호가보다 터무니없이 낮으면 자릿수 누락 같은 입력 오류로 본다."""
        prev = comparable_prev_price(a)
        return bool(prev) and float(a.get("dealPrice") or 0) < prev * PRICE_TYPO_RATIO

    # 합필에 넣으면 안 되는 필지 — 단일 매물로도 걸러지는 데이터 이상(평당가 이상치,
    # 호실·지분 매물, 호가 오타), 가격 미공개(1억 미만), 그리고 그 자체로 철거 실익이
    # 없는 건물(이미 꽉 채워 지었거나 신축). 그대로 합산하면 그룹 Cap이 왜곡된다.
    excluded = set(dropped_aids)
    for a in deduped_raw:
        if a.get("isCombinedDevelopment") or not a.get("partOfGroup"):
            continue
        if (a.get("dealPrice") or 0) < 10000 or (a.get("landSpace") or 0) <= 0 or price_typo(a):
            excluded.add(str(a.get("articleNo")))
            continue
        m = compute_dev_metrics(a, assumptions, use)
        if data_issue(m, assumptions) or redevelopment_issue(m, assumptions, as_member=True):
            excluded.add(str(a.get("articleNo")))

    # 그룹별 최종 멤버 — 제외 필지가 빠지면 그룹의 남은 필지 전체에서 맞닿은 가장 큰
    # 묶음을 다시 고른다 (빠진 필지가 다리 역할이었으면 떨어진 필지는 같이 묶지 않고,
    # 원래 두 번째였던 묶음이 온전하면 그쪽을 쓴다).
    members_of: dict[str, list[str]] = {}
    for a in raw:
        if a.get("partOfGroup") and not a.get("isCombinedDevelopment"):
            members_of.setdefault(str(a.get("partOfGroup")), []).append(str(a.get("articleNo")))
    final_members: dict[str, frozenset[str]] = {}
    for gid, allowed in group_conn.items():
        if allowed & excluded:
            allowed = _largest_adjacent(sorted(set(members_of.get(gid, ())) - excluded))
        final_members[gid] = allowed

    processed: list[dict] = []
    lpp_population: list[float] = []   # 평당가 하위 5% 기준 — 용도 모드와 무관한 모집단
    for a in deduped_raw:
        if not a.get("isCombinedDevelopment") and price_typo(a):
            continue
        # 통합 그룹 — 최종 멤버만 합산해서 metric 재계산
        if a.get("isCombinedDevelopment"):
            gid = str(a.get("articleNo") or "")
            allowed = final_members.get(gid, frozenset())
            if len(allowed) < 2:
                continue
            all_members = a.get("groupMembersDetail") or []
            kept = [m for m in all_members if str(m.get("articleNo") or "") in allowed]
            if len(kept) < 2:
                continue
            raw_by_aid = _raw_by_aid()
            a = dict(a)
            _inherit_planning(a, [raw_by_aid.get(str(m.get("articleNo")), m) for m in kept])
            # 철거 실익 판단용 현재 연면적 — 멤버별 추정치(건축물대장 보완) 합
            a["existingGfaSqm"] = sum(
                existing_gfa_sqm(raw_by_aid.get(str(m.get("articleNo")), m)) for m in kept
            ) or None
            # 멤버가 줄었으면 metric 재계산
            if len(kept) < len(all_members):
                total_land = sum(float(m.get("landSpace") or 0) for m in kept)
                total_price = sum(float(m.get("dealPrice") or 0) for m in kept)
                lats = [float(m.get("latitude")) for m in kept if m.get("latitude")]
                lons = [float(m.get("longitude")) for m in kept if m.get("longitude")]
                if total_land > 0 and lats and lons:
                    a["landSpace"] = total_land
                    a["dealPrice"] = total_price
                    a["floorSpace"] = sum(
                        float(raw_by_aid.get(str(m.get("articleNo")), {}).get("floorSpace") or 0)
                        for m in kept
                    ) or None
                    a["groupSize"] = len(kept)
                    a.pop("articleFeatureDescription", None)   # 멤버 수·합계가 옛 값으로 적혀 있음
                    a["groupMembersDetail"] = kept
                    a["groupMemberArticles"] = ",".join(str(m.get("articleNo")) for m in kept)
                    a["latitude"] = sum(lats) / len(lats)
                    a["longitude"] = sum(lons) / len(lons)
                    a["name"] = f"통합개발 ({len(kept)}필지)"

        # 그룹멤버 — connectivity 분석에서 component에 안 들어가면 partOfGroup 제거
        # (떨어진 필지는 같이 묶지 않음 → 단일 매물 취급)
        elif a.get("partOfGroup"):
            gid = str(a.get("partOfGroup"))
            allowed = final_members.get(gid, frozenset())
            aid = str(a.get("articleNo") or "")
            if aid not in allowed:
                a = dict(a)
                a["partOfGroup"] = None  # 인접 component 밖이라 묶음 해제

        # compute_dev_metrics가 일부 키 덮어쓸 수 있으니 보존
        preserved = {
            "isCombinedDevelopment": a.get("isCombinedDevelopment", False),
            "partOfGroup": a.get("partOfGroup"),
            "groupSize": a.get("groupSize"),
            "groupMemberArticles": a.get("groupMemberArticles"),
            "groupMembersDetail": a.get("groupMembersDetail"),
            "parcelPolygon": a.get("parcelPolygon"),
        }
        m = compute_dev_metrics(a, assumptions, use)
        for k, v in preserved.items():
            if v is not None:
                m[k] = v
        if (m.get("devZoneOk") and m.get("landPerPyeongM") is not None
                and (m.get("hotelCapRate") is not None or m.get("officeCapRate") is not None)
                and not data_issue(m, assumptions) and not redevelopment_issue(m, assumptions)):
            lpp_population.append(float(m["landPerPyeongM"]))
        m = apply_show_filter(m, assumptions)

        # apply_show_filter가 isShown=False로 마크하면 무조건 제외
        if not m.get("isShown"):
            continue

        # ── 주간 변동 추적 (단일/멤버만) ──
        # 통합그룹의 dealPrice는 멤버 수 / dedupe 영향 받아 부정확
        is_group = bool(m.get("isCombinedDevelopment"))
        m["isNew"] = bool(prev_prices) and not is_group and str(m.get("articleNo")) not in prev_prices
        m["prevDealPrice"] = None
        m["priceChangePct"] = None
        prev_price = None if is_group else comparable_prev_price(m)
        if prev_price:
            ratio = float(m.get("dealPrice") or 0) / prev_price
            if PRICE_CHANGE_RANGE[0] <= ratio <= PRICE_CHANGE_RANGE[1]:
                m["prevDealPrice"] = prev_price
                m["priceChangePct"] = round((ratio - 1) * 100, 2)

        processed.append(m)

    # 그룹멤버는 소속 통합그룹이 살아남았을 때만 의미가 있다. 그룹이 탈락
    # (인접 부족 / 등급외 / 이상치)했으면 멤버를 단일 매물로 되돌려 등급 판정.
    surviving_groups = {
        str(m.get("articleNo")) for m in processed
        if m.get("isCombinedDevelopment") and m.get("devUse")
    }
    new_articles: list[dict] = []
    for m in processed:
        is_member = m.get("partOfGroup") and not m.get("isCombinedDevelopment")
        if is_member and str(m.get("partOfGroup")) not in surviving_groups:
            m["partOfGroup"] = None
            is_member = False
            # 멤버일 때는 건너뛴 단일 매물 기준(등급·철거 실익)을 다시 적용
            if not apply_show_filter(m, assumptions).get("isShown"):
                continue
        if m.get("devUse") or is_member:
            new_articles.append(m)

    # outlier 마킹 — 전체 산출 후 분위수 기반
    _mark_outliers(new_articles, _percentile(lpp_population, 0.05), zoning_conflict)
    # 평당가 하위 5% + 취득 Cap 10% 초과가 겹치면 호가·면적 입력 오류일 가능성이 매우
    # 높다 (예: 대지·연면적 뒤바뀜) — 순위에 올리지 않는다.
    return [
        a for a in new_articles
        if not {"price_low", "cap_high"} <= set(a.get("outlierFlags") or [])
    ]
