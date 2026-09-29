"""OSM Overpass API에서 서울 지하철 노선/역 가져와서 GeoJSON으로 저장.

실행:
    python scripts/fetch_subway_geojson.py

산출물:
    reference/seoul_subway_lines.geojson     (MultiLineString features)
    reference/seoul_subway_stations.geojson  (Point features)

각 노선엔 OSM의 `colour` 태그가 있으면 그걸 쓰고, 없으면 라인 ref로 fallback 색상 매핑.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SEOUL_BBOX = (37.4, 126.7, 37.7, 127.2)  # (south, west, north, east)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "reference"

# 노선 번호 → 한국 표준 색상 (OSM colour 태그 없을 때 fallback)
LINE_COLORS = {
    "1": "#0052A4", "2": "#00A84D", "3": "#EF7C1C", "4": "#00A5DE",
    "5": "#996CAC", "6": "#CD7C2F", "7": "#747F00", "8": "#E6186C",
    "9": "#BDB092",
    "공항철도": "#0090D2", "수인분당": "#FABE00", "분당": "#FABE00",
    "신분당": "#D4003B", "경의중앙": "#77C4A3", "경춘": "#178C72",
    "GTX-A": "#9A6292", "GTX A": "#9A6292",
    "서해": "#81A914", "신림": "#6789CA", "우이신설": "#B7C452",
    "김포골드": "#A17800", "에버라인": "#509F22",
    "의정부": "#FFC600", "인천1": "#7CA8D5", "인천2": "#ED8B00",
}


def overpass_query(query: str, timeout: int = 180) -> dict:
    print(f"[overpass] querying ({len(query)} chars)...", flush=True)
    headers = {
        "User-Agent": "seoul-site-screener (https://github.com/tjdals418-pixel/seoul-site-screener)",
        "Accept": "application/json",
    }
    r = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=headers,
        timeout=timeout,
    )
    if r.status_code != 200:
        print(f"[overpass] HTTP {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


def _resolve_color(tags: dict) -> str:
    raw = (tags.get("colour") or tags.get("color") or "").strip()
    if raw:
        if not raw.startswith("#"):
            raw = "#" + raw
        return raw
    ref = (tags.get("ref") or "").strip()
    name = (tags.get("name") or "").strip()
    if ref in LINE_COLORS:
        return LINE_COLORS[ref]
    for key, color in LINE_COLORS.items():
        if key in name or key in ref:
            return color
    return "#6b7280"  # default gray


def lines_to_geojson(osm: dict) -> dict:
    """ref별로 모든 way를 합쳐서 하나의 MultiLineString feature만 생성.

    같은 노선의 양방향/지선/급행이 별도 relation으로 나뉘어 있어 features 부풀림.
    dedupe하지 않으면 156 features → mapbox-gl 렌더링 폭주.
    """
    from collections import defaultdict

    by_ref: dict[str, dict] = defaultdict(lambda: {
        "coords": [], "seen": set(), "tags": {},
    })
    for el in osm.get("elements", []):
        if el.get("type") != "relation":
            continue
        tags = el.get("tags", {})
        if tags.get("route") not in ("subway", "light_rail"):
            continue
        ref = (tags.get("ref") or tags.get("name") or "unknown").strip()
        bucket = by_ref[ref]
        if not bucket["tags"]:
            bucket["tags"] = tags
        for member in el.get("members", []):
            if member.get("type") != "way" or "geometry" not in member:
                continue
            way_id = member.get("ref")
            if way_id in bucket["seen"]:
                continue
            bucket["seen"].add(way_id)
            way_coords = [
                [round(pt["lon"], 6), round(pt["lat"], 6)]
                for pt in member["geometry"]
                if "lon" in pt and "lat" in pt
            ]
            if len(way_coords) >= 2:
                bucket["coords"].append(way_coords)

    features = []
    for ref, b in by_ref.items():
        if not b["coords"]:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": b["coords"]},
            "properties": {
                "ref": ref,
                "name": b["tags"].get("name"),
                "operator": b["tags"].get("operator"),
                "color": _resolve_color(b["tags"]),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def stations_to_geojson(osm: dict) -> dict:
    features = []
    for el in osm.get("elements", []):
        if el.get("type") != "node":
            continue
        tags = el.get("tags", {})
        if tags.get("railway") not in ("station", "halt"):
            continue
        if tags.get("station") not in (None, "subway", "light_rail"):
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [el["lon"], el["lat"]],
            },
            "properties": {
                "name": tags.get("name"),
                "name_en": tags.get("name:en"),
                "operator": tags.get("operator"),
                "ref": tags.get("ref"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    bbox = ",".join(str(x) for x in SEOUL_BBOX)
    lines_query = f"""
[out:json][timeout:180];
(
  relation["route"="subway"]({bbox});
  relation["route"="light_rail"]({bbox});
);
out geom;
""".strip()
    stations_query = f"""
[out:json][timeout:120];
(
  node["railway"="station"]["station"="subway"]({bbox});
  node["railway"="station"]["station"="light_rail"]({bbox});
  node["railway"~"^(station|halt)$"]["subway"="yes"]({bbox});
);
out;
""".strip()

    print("[1/2] 지하철 노선 fetch…")
    lines_osm = overpass_query(lines_query)
    lines_gj = lines_to_geojson(lines_osm)
    print(f"  → {len(lines_gj['features'])} 노선 (raw elements: {len(lines_osm.get('elements', []))})")

    print("[2/2] 지하철역 fetch…")
    stations_osm = overpass_query(stations_query)
    stations_gj = stations_to_geojson(stations_osm)
    print(f"  → {len(stations_gj['features'])} 역")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines_path = OUT_DIR / "seoul_subway_lines.geojson"
    stations_path = OUT_DIR / "seoul_subway_stations.geojson"
    lines_path.write_text(json.dumps(lines_gj, ensure_ascii=False), encoding="utf-8")
    stations_path.write_text(json.dumps(stations_gj, ensure_ascii=False), encoding="utf-8")
    print(f"저장 완료: {lines_path.name} ({lines_path.stat().st_size//1024}KB)")
    print(f"저장 완료: {stations_path.name} ({stations_path.stat().st_size//1024}KB)")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"[ERR] Overpass HTTP error: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"[ERR] Network error: {e}")
        sys.exit(1)
