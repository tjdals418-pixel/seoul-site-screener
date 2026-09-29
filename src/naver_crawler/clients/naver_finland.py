from __future__ import annotations

"""fin.land.naver.com client.

공개 지도 화면(fin.land/map)이 사용하는 매물 목록·건축물 정보 요청을 브라우저
세션 안에서 같은 방식으로 호출한다 (Playwright 페이지 컨텍스트의 `fetch`).
요청 사이에 `pace_sec` 간격을 두고, 파이프라인 실행당 세션 하나만 연다.

Context manager: 실행 시작 시 한 번 열고 모든 호출이 공유한 뒤 닫는다.
"""

import json
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Iterator

from naver_crawler.logging_setup import get_logger

log = get_logger(__name__)

BASE_URL = "https://fin.land.naver.com"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
DEFAULT_REFERER = (
    "https://fin.land.naver.com/map?center=3zhVgj-2AM4Le&zoom=14"
    "&tradeTypes=A1&realEstateTypes=E03-D03-D04-E01-Z00"
)


@dataclass
class BoundingBox:
    left: float
    right: float
    top: float
    bottom: float

    def to_payload(self) -> dict:
        return {"left": self.left, "right": self.right, "top": self.top, "bottom": self.bottom}


@dataclass
class ArticleFilter:
    """Filter payload for /article/boundedArticles. Only fields the user
    actually tunes are first-class; rest go via `extra`."""
    trade_types: list[str] = field(default_factory=lambda: ["A1"])               # A1=매매
    real_estate_types: list[str] = field(default_factory=lambda: ["D03", "D04"]) # 빌딩/상가건물
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict:
        body = {
            "tradeTypes": self.trade_types,
            "realEstateTypes": self.real_estate_types,
            "roomCount": [],
            "bathRoomCount": [],
            "optionTypes": [],
            "oneRoomShapeTypes": [],
            "moveInTypes": [],
            "filtersExclusiveSpace": False,
            "floorTypes": [],
            "directionTypes": [],
            "hasArticlePhoto": False,
            "isAuthorizedByOwner": False,
            "parkingTypes": [],
            "entranceTypes": [],
            "hasArticle": False,
        }
        body.update(self.extra)
        return body


class FinlandClient(AbstractContextManager):
    """fin.land `/front-api/v1/...` 호출용 Playwright 세션.

    모든 호출은 `page.evaluate("fetch(...)")`로 지도 페이지와 같은 세션·쿠키를
    사용한다.
    """

    def __init__(
        self,
        cookie_string: str = "",
        *,
        headless: bool = True,
        pace_sec: float = 0.4,
    ):
        # cookie_string is now optional. If empty, the warmup navigation to
        # fin.land/map will set the necessary cookies (NAC/NNB/BUC) naturally.
        # NID_AUT/NID_SES (login session) are NOT required for any of the
        # endpoints we use — verified empirically.
        self._cookie_string = cookie_string
        self._headless = headless
        self._pace_sec = pace_sec
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    # ── lifecycle ───────────────────────────────────────────────────
    def __enter__(self) -> "FinlandClient":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(
                channel="chrome",
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            self._browser = self._pw.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )

        self._ctx = self._browser.new_context(user_agent=DEFAULT_UA, locale="ko-KR")
        if self._cookie_string:
            # Optional manual override (e.g. when debugging or replaying a
            # known-good session).
            self._ctx.add_cookies(self._parse_cookies(self._cookie_string))
        self._page = self._ctx.new_page()
        self._page.set_default_timeout(30000)

        # Warmup: navigating fin.land/map seeds tracking cookies (NAC/NNB/BUC)
        # via Set-Cookie headers, so fetch() calls afterward are authorized.
        self._page.goto(f"{BASE_URL}/map", wait_until="domcontentloaded")
        try:
            self._page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass  # not critical — domcontentloaded is enough for cookies
        log.info("fin.land session ready (cookies=%d)", len(self._ctx.cookies()))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for closer in (self._page, self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    @staticmethod
    def _parse_cookies(raw: str) -> list[dict]:
        cookies = []
        for piece in raw.split(";"):
            piece = piece.strip()
            if not piece or "=" not in piece:
                continue
            name, value = piece.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip().strip('"'),
                "domain": ".naver.com",
                "path": "/",
            })
        return cookies

    # ── low-level fetch via page.evaluate ───────────────────────────
    def _fetch_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
    ) -> Any:
        if self._page is None:
            raise RuntimeError("FinlandClient must be used as a context manager")

        opts = {
            "method": method,
            "credentials": "include",
            "headers": {
                "accept": "application/json, text/plain, */*",
                "accept-language": "ko-KR,ko;q=0.9",
                "referer": DEFAULT_REFERER,
            },
        }
        if body is not None:
            opts["headers"]["content-type"] = "application/json"
            opts["body"] = json.dumps(body, ensure_ascii=False)

        result = self._page.evaluate(
            """async ({url, opts}) => {
                const res = await fetch(url, opts);
                const text = await res.text();
                return {status: res.status, body: text};
            }""",
            {"url": BASE_URL + path, "opts": opts},
        )
        time.sleep(self._pace_sec)

        status, raw = result["status"], result["body"]
        if status == 429:
            raise FinlandRateLimited(path)
        if status >= 400:
            raise FinlandHTTPError(status, path, raw[:200])
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise FinlandHTTPError(status, path, f"non-JSON: {raw[:200]}") from e

    # ── public endpoints ────────────────────────────────────────────
    def get_bounded_articles_count(
        self,
        bbox: BoundingBox,
        filter_: ArticleFilter,
        *,
        precision: int = 14,
    ) -> int:
        """Cheap count-only call. Used by `iter_bounded_articles_auto` to
        decide whether to split a tile."""
        payload = {
            "filter": filter_.to_payload(),
            "boundingBox": bbox.to_payload(),
            "precision": precision,
            "userChannelType": "PC",
        }
        try:
            data = self._fetch_json(
                "/front-api/v1/article/boundedArticlesCount",
                method="POST",
                body=payload,
            )
        except FinlandHTTPError as e:
            log.warning("count call failed bbox=%s: %s", bbox, e)
            return 0
        # Response shape: {"isSuccess": true, "result": {"count": 1234}} or similar
        result = data.get("result")
        if isinstance(result, dict):
            for key in ("count", "totalCount", "total"):
                if key in result:
                    return int(result[key])
        if isinstance(result, int):
            return result
        log.warning("unexpected count payload: %s", str(data)[:120])
        return 0

    def iter_bounded_articles_auto(
        self,
        bbox: BoundingBox,
        filter_: ArticleFilter,
        *,
        max_per_tile: int = 2500,
        min_tile_deg: float = 0.005,   # ~500m, hard floor on recursion
        max_depth: int = 8,
        page_size: int = 30,
        precision: int = 14,
        _depth: int = 0,
    ) -> Iterator[dict]:
        """Recursively quad-split `bbox` until each subtile has fewer than
        `max_per_tile` articles, then paginate that subtile.

        Why: `boundedArticles` caps the total returned per query at ~3000.
        Dense areas (Gangnam, Mapo) blow past that. Auto-split keeps each
        query under the cap and saves tedious manual tile lists.
        """
        count = self.get_bounded_articles_count(bbox, filter_, precision=precision)
        indent = "  " * _depth
        log.info("%stile=%s count=%d", indent, _bbox_short(bbox), count)

        if count == 0:
            return

        too_small = (
            (bbox.right - bbox.left) < min_tile_deg
            or (bbox.top - bbox.bottom) < min_tile_deg
        )
        if count <= max_per_tile or too_small or _depth >= max_depth:
            if count > max_per_tile:
                log.warning(
                    "%stile at floor with count=%d > cap=%d — some articles "
                    "will be missed. Lower min_tile_deg or raise max_depth.",
                    indent, count, max_per_tile,
                )
            yield from self.iter_bounded_articles(
                bbox, filter_, page_size=page_size, precision=precision
            )
            return

        # Split into 4 quadrants and recurse
        midx = (bbox.left + bbox.right) / 2
        midy = (bbox.top + bbox.bottom) / 2
        quads = [
            BoundingBox(left=bbox.left, right=midx, top=bbox.top, bottom=midy),
            BoundingBox(left=midx, right=bbox.right, top=bbox.top, bottom=midy),
            BoundingBox(left=bbox.left, right=midx, top=midy, bottom=bbox.bottom),
            BoundingBox(left=midx, right=bbox.right, top=midy, bottom=bbox.bottom),
        ]
        for q in quads:
            yield from self.iter_bounded_articles_auto(
                q, filter_,
                max_per_tile=max_per_tile,
                min_tile_deg=min_tile_deg,
                max_depth=max_depth,
                page_size=page_size,
                precision=precision,
                _depth=_depth + 1,
            )

    def iter_bounded_articles(
        self,
        bbox: BoundingBox,
        filter_: ArticleFilter,
        *,
        precision: int = 14,
        page_size: int = 30,
        sort: str = "RANKING_DESC",
    ) -> Iterator[dict]:
        """Yield each article from /article/boundedArticles.

        Uses cursor pagination (`lastInfo` + `seed`) until `hasNextPage` is
        false. fin.land에서 단일 화면 11,685건이 표시되는 것을 확인했으므로
        cursor 페이징 자체에는 사실상 cap이 없다고 보면 됨 — 다만 hidden cap
        가능성을 대비해 종료 시 totalCount vs 실제 yield 건수를 비교해서
        mismatch면 WARNING을 남긴다(→ max_per_tile 낮춰야 한다는 신호).
        """
        seed: str | None = None
        last_info: list = []
        page_num = 0
        yielded = 0
        expected_total: int | None = None

        while True:
            page_num += 1
            paging = {
                "size": page_size,
                "articleSortType": sort,
                "lastInfo": last_info,
            }
            if seed:
                paging["seed"] = seed

            payload = {
                "filter": filter_.to_payload(),
                "boundingBox": bbox.to_payload(),
                "precision": precision,
                "userChannelType": "PC",
                "articlePagingRequest": paging,
            }
            data = self._fetch_json(
                "/front-api/v1/article/boundedArticles",
                method="POST",
                body=payload,
            )
            result = data.get("result", {})
            articles = result.get("list", [])
            total = result.get("totalCount")
            if expected_total is None and isinstance(total, int):
                expected_total = total
            log.info(
                "boundedArticles page=%d got=%d total=%s",
                page_num, len(articles), total,
            )
            for a in articles:
                yielded += 1
                yield a

            if not result.get("hasNextPage"):
                break
            seed = result.get("seed", seed)
            last_info = result.get("lastInfo", [])
            if not last_info:
                break  # defensive: no cursor to advance

        # Sanity check: pagination 끝났는데 totalCount보다 적게 받았다면
        # 네이버가 hidden cap을 걸어둔 것 — max_per_tile을 낮춰서 분할로 회피
        if expected_total and yielded < expected_total:
            log.warning(
                "bbox %s: yielded %d but totalCount=%d — possible hidden cap, "
                "consider lowering max_per_tile",
                _bbox_short(bbox), yielded, expected_total,
            )

    def get_building_registration(self, pnu: str, real_estate_type: str) -> dict | None:
        """`/complex/buildingRegistration?pnu=...&realEstateType=...`

        Returns 용도지역, 용적률, 건폐율, 구조, 사용승인일, 주차대수.
        """
        try:
            data = self._fetch_json(
                f"/front-api/v1/complex/buildingRegistration?pnu={pnu}&realEstateType={real_estate_type}",
            )
        except FinlandHTTPError as e:
            log.debug("buildingRegistration failed pnu=%s: %s", pnu, e)
            return None
        return data.get("result")

    def get_article_agent(self, article_number: str) -> dict | None:
        """`/article/agent?articleNumber=...` — realtor name + phone."""
        try:
            data = self._fetch_json(
                f"/front-api/v1/article/agent?articleNumber={article_number}",
            )
        except FinlandHTTPError as e:
            log.debug("agent failed articleNumber=%s: %s", article_number, e)
            return None
        return data.get("result")

    def get_development_info(self, article_number: str) -> dict | None:
        """`/development?type=article&itemId=...` — 지구단위계획구역 + 미래 역세권.

        응답 형태:
            {
              "jiguList": [{name, typeName, step, ...}],   # 도시계획 지구
              "railList": [{stationName, railName, openDate, distance, walkingTime, ...}]
            }
        """
        try:
            data = self._fetch_json(
                f"/front-api/v1/development?type=article&itemId={article_number}",
            )
        except FinlandHTTPError as e:
            log.debug("development failed articleNumber=%s: %s", article_number, e)
            return None
        return data.get("result")


# ── exceptions ──────────────────────────────────────────────────────
class FinlandError(Exception):
    pass


class FinlandRateLimited(FinlandError):
    def __init__(self, path: str):
        super().__init__(f"429 from {path} — refresh cookies or wait")


class FinlandHTTPError(FinlandError):
    def __init__(self, status: int, path: str, snippet: str):
        super().__init__(f"{status} from {path}: {snippet}")
        self.status = status


def _bbox_short(b: BoundingBox) -> str:
    return f"({b.left:.4f},{b.bottom:.4f})-({b.right:.4f},{b.top:.4f})"
