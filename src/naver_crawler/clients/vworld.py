from __future__ import annotations

"""VWorld geocoding & land-characteristics client.

Two endpoints used:
  1. `/req/address` (reverse geocode) → cortarNo + 본번/부번 → PNU 조립
  2. `/ned/data/getLandCharacteristics` (토지특성) → 용도지역 (`prposArea1Nm`)

(2)는 fin.land buildingRegistration이 빈 응답이거나 광역 카테고리("도시지역")만
줄 때 fallback으로 호출 — 공식 도시계획 데이터라 보다 정확함.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import requests

from naver_crawler.logging_setup import get_logger

log = get_logger(__name__)

_JIBUN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


@dataclass
class GeocodeResult:
    """What we extract from VWorld's /req/address response."""
    full_text: str = ""             # 'result.text'
    cortar_no: str = ""             # 'level4LC' — 10-digit legal division
    sector_name: str = ""           # 'level4L' — 동/리 이름
    jibun_main: str = ""            # 본번
    jibun_sub: str = ""             # 부번
    is_san: bool = False            # True if 산 (not flat land)

    def assemble_pnu(self) -> Optional[str]:
        """Compose 19-digit PNU = cortar(10) + 1/2(1) + 본번(4) + 부번(4)."""
        if not self.cortar_no or not self.jibun_main:
            return None
        san_digit = "2" if self.is_san else "1"
        try:
            main = f"{int(self.jibun_main):04d}"
            sub = f"{int(self.jibun_sub):04d}" if self.jibun_sub else "0000"
        except ValueError:
            return None
        pnu = f"{self.cortar_no}{san_digit}{main}{sub}"
        return pnu if len(pnu) == 19 else None


class VWorldClient:
    GEOCODE_URL = "https://api.vworld.kr/req/address"
    LAND_CHAR_URL = "https://api.vworld.kr/ned/data/getLandCharacteristics"
    WFS_URL = "https://api.vworld.kr/req/wfs"

    def __init__(self, api_key: str, *, timeout_sec: float = 5.0, domain: str = "localhost"):
        if not api_key:
            raise ValueError("VWORLD_API_KEY not set — see .env.example")
        self.api_key = api_key
        self.timeout = timeout_sec
        self.domain = domain
        self.session = requests.Session()

    def reverse_geocode(self, lat: float, lon: float) -> Optional[GeocodeResult]:
        params = {
            "service": "address",
            "request": "getAddress",
            "version": "2.0",
            "crs": "epsg:4326",
            "point": f"{lon},{lat}",
            "format": "json",
            "type": "parcel",
            "zipcode": "true",
            "simple": "false",
            "key": self.api_key,
        }
        try:
            res = self.session.get(self.GEOCODE_URL, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            log.debug("vworld error: %s", e)
            return None

        if res.status_code != 200:
            return None

        try:
            body = res.json().get("response", {})
        except ValueError:
            return None

        if body.get("status") != "OK":
            return None

        result = body["result"][0]
        structure = result.get("structure", {})
        full_text = result.get("text", "")

        # 본번-부번 추출. 원천: level5 (e.g. "630-10") 또는 text 끝의 숫자
        jibun_main, jibun_sub = self._parse_jibun(structure.get("level5", ""), full_text)

        # 산 여부 판별: 주소 텍스트에 "산"이 단독 토큰으로 있으면 산
        is_san = " 산 " in f" {full_text} "

        return GeocodeResult(
            full_text=full_text,
            cortar_no=structure.get("level4LC", ""),
            sector_name=structure.get("level4L", ""),
            jibun_main=jibun_main,
            jibun_sub=jibun_sub,
            is_san=is_san,
        )

    @staticmethod
    def _parse_jibun(level5: str, full_text: str) -> tuple[str, str]:
        m = _JIBUN_RE.match(level5.strip()) if level5 else None
        if m:
            return m.group(1), (m.group(2) or "")

        # Fall back: scan text for "<num>" or "<num>-<num>"
        for token in full_text.split():
            m = _JIBUN_RE.match(token)
            if m:
                return m.group(1), (m.group(2) or "")
        return "", ""

    # ── Land characteristics (PNU → 용도지역) ─────────────────────────
    # 시도 순서: 데이터가 가장 안정적인 연도부터, 이후 최신·일부 연도
    DEFAULT_YEAR_FALLBACKS = ("2017", "2020", "2022", "2024", "2015", "2018")

    def get_zoning_by_pnu(
        self,
        pnu: str,
        *,
        stdr_year: str | None = None,
        year_fallbacks: tuple[str, ...] | None = None,
        retry: int = 2,
    ) -> Optional[str]:
        """`/ned/data/getLandCharacteristics` 호출해서 `prposArea1Nm` 반환.

        VWorld의 토지특성 데이터는 연도별로 갱신됨. 한 연도에 데이터 없어도
        다른 연도에 있을 수 있어 multi-year fallback. stdr_year 지정 안 하면
        DEFAULT_YEAR_FALLBACKS 순서로 시도.
        """
        if not pnu:
            return None
        years = (stdr_year,) if stdr_year else (year_fallbacks or self.DEFAULT_YEAR_FALLBACKS)
        for year in years:
            zoning = self._fetch_zoning(pnu, year, retry)
            if zoning:
                return zoning
        return None

    # ── 필지 polygon (PNU 모양) ─────────────────────────────────────
    def _wfs_features(
        self, lat: float, lon: float, delta_deg: float, max_features: int
    ) -> list[dict]:
        """매물 좌표 주변 bbox WFS GetFeature → features list (raw)."""
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            return []
        bbox = f"{lon_f-delta_deg},{lat_f-delta_deg},{lon_f+delta_deg},{lat_f+delta_deg}"
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typename": "lp_pa_cbnd_bubun",
            "bbox": bbox,
            "srsName": "EPSG:4326",
            "output": "application/json",
            "maxFeatures": str(max_features),
            "key": self.api_key,
            "domain": self.domain,
        }
        try:
            res = self.session.get(self.WFS_URL, params=params, timeout=self.timeout)
        except requests.RequestException:
            return []
        if res.status_code != 200:
            return []
        try:
            return res.json().get("features", []) or []
        except ValueError:
            return []

    def get_parcel_polygon(
        self,
        pnu: str,
        lat: float,
        lon: float,
        *,
        delta_deg: float = 0.0003,   # 약 30m bbox
        max_features: int = 50,
    ) -> Optional[dict]:
        """매물 좌표 주변 bbox로 WFS 호출 → 매칭되는 PNU의 GeoJSON geometry 반환."""
        if not pnu or lat is None or lon is None:
            return None
        for feature in self._wfs_features(lat, lon, delta_deg, max_features):
            props = feature.get("properties") or {}
            if props.get("pnu") == pnu:
                return feature.get("geometry")
        return None

    def get_best_parcel(
        self,
        pnu: str,
        lat: float,
        lon: float,
        land_space: float | None = None,
        *,
        delta_deg: float = 0.0004,    # ~40m bbox (re-snap 후보 충분히)
        max_features: int = 120,
        area_lo: float = 0.6,         # exact 필지 면적/landSpace 허용 하한
        area_hi: float = 1.8,         # 〃 상한
        resnap_radius_m: float = 14.0,
    ) -> Optional[dict]:
        """PNU 매칭 + 면적/근접 기반 re-snap.

        네이버 좌표가 필지 경계 근처에 찍히면 옆 자투리 필지로 reverse-geocode
        되는 경우가 있다 (예: 좌표가 65㎡ 빈 필지에 떨어지는데 실제 매물은 인접
        165㎡ 필지). 매물 land_space와 필지 면적이 크게 어긋나면, 좌표 인근에서
        면적이 더 맞는 필지로 교정한다.

        Returns dict {pnu, geometry, area_m2, resnapped, reason} or None.
        """
        import math

        if lat is None or lon is None:
            return None
        feats = self._wfs_features(lat, lon, delta_deg, max_features)
        if not feats:
            return None

        try:
            from shapely.geometry import shape, Point
        except Exception:  # shapely 없으면 기존 동작 (PNU 매칭만)
            for f in feats:
                if (f.get("properties") or {}).get("pnu") == pnu:
                    return {"pnu": pnu, "geometry": f.get("geometry"),
                            "area_m2": None, "resnapped": False, "reason": "no-shapely"}
            return None

        m_per_deg_lat = 111000.0
        m_per_deg_lon = 111000.0 * math.cos(math.radians(float(lat)))
        area_factor = m_per_deg_lat * m_per_deg_lon
        pt = Point(float(lon), float(lat))

        parcels: list[dict] = []
        exact: Optional[dict] = None
        for f in feats:
            geom = f.get("geometry")
            try:
                g = shape(geom)
            except Exception:
                continue
            rec = {
                "pnu": (f.get("properties") or {}).get("pnu"),
                "geometry": geom,
                "area_m2": g.area * area_factor,
                "dist_m": g.distance(pt) * m_per_deg_lat,
            }
            parcels.append(rec)
            if rec["pnu"] == pnu:
                exact = rec

        if not parcels:
            return None

        def result(rec, reason):
            return {
                "pnu": rec["pnu"], "geometry": rec["geometry"],
                "area_m2": round(rec["area_m2"], 1),
                "resnapped": rec["pnu"] != pnu, "reason": reason,
            }

        # land_space 없으면 검증 불가 → exact 우선, 없으면 좌표 최근접
        if not land_space or land_space <= 0:
            chosen = exact or min(parcels, key=lambda r: r["dist_m"])
            return result(chosen, "no-landspace")

        def ratio(r):
            return r["area_m2"] / land_space

        # exact 필지 면적이 합리적이면 그대로 신뢰
        if exact and area_lo <= ratio(exact) <= area_hi:
            return result(exact, "exact-ok")

        # re-snap: 좌표 인근 + 면적 [0.5×, 2×] land_space 후보 중 면적비 최적
        cands = [r for r in parcels
                 if r["dist_m"] <= resnap_radius_m
                 and 0.5 * land_space <= r["area_m2"] <= 2.0 * land_space]
        if cands:
            best = min(cands, key=lambda r: abs(math.log(r["area_m2"] / land_space)))
            return result(best, "area-resnap")

        # 후보 없으면 exact(있으면) 또는 최근접
        if exact:
            return result(exact, "exact-fallback")
        return result(min(parcels, key=lambda r: r["dist_m"]), "nearest-fallback")

    def _fetch_zoning(self, pnu: str, year: str, retry: int) -> Optional[str]:
        params = {
            "pnu": pnu,
            "stdrYear": year,
            "format": "xml",
            "numOfRows": "10",
            "pageNo": "1",
            "key": self.api_key,
            "domain": self.domain,
        }
        for attempt in range(retry + 1):
            try:
                res = self.session.get(self.LAND_CHAR_URL, params=params, timeout=self.timeout)
            except requests.RequestException:
                continue
            if res.status_code != 200:
                continue
            try:
                root = ET.fromstring(res.text)
            except ET.ParseError:
                continue
            if (root.findtext("totalCount") or "0") == "0":
                return None
            node = root.find(".//prposArea1Nm")
            if node is None or not node.text:
                return None
            return node.text.strip()
        return None
