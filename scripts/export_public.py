"""공개 배포용 데이터 export — data/published/articles.json.gz

로컬 파이프라인 산출물(data/interim/simulated.json)에서
  1) 중개사/중개업소 정보(agent*/broker*)를 재귀적으로 제거하고
  2) API가 쓰는 필드만 남기고 (Article 스키마 whitelist)
  3) 시뮬 대상이 될 수 없는 초소형 매물을 걸러
gzip JSON으로 저장한다. 이 파일만 git에 포함되어 배포 환경의 유일한 데이터가 된다.

이전 snapshot(data/snapshots/)이 있으면 가격 변동/신규 표시용 prevPrices도 함께 담는다.

사용:
    python scripts/export_public.py
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT_ROOT / "src"), str(PROJECT_ROOT / "api")]

from app.data import (  # noqa: E402
    DATA_PATH,
    PUBLIC_DATA_PATH,
    find_previous_snapshot,
    snapshot_prices,
    strip_private,
)
from app.schemas import Article  # noqa: E402

# 개발 연면적 추정치(대지 × (용적률 + 지하비율)) 가 이 값 미만이면 어떤 용도로도
# 시뮬 대상이 안 되므로 제외 (그룹 멤버는 예외)
MIN_DEV_PYEONG = 500
SQM_TO_PYEONG = 0.3025
BASEMENT_RATIO = 0.6

FIELDS = set(Article.model_fields)


def _slim(a: dict) -> dict:
    out = {k: v for k, v in a.items() if k in FIELDS and v not in (None, "")}
    if out.get("groupMembersDetail"):
        out["groupMembersDetail"] = [
            {k: v for k, v in m.items() if k in FIELDS and v not in (None, "")}
            for m in out["groupMembersDetail"]
        ]
    return out


def _worth_keeping(a: dict) -> bool:
    if a.get("isCombinedDevelopment") or a.get("partOfGroup"):
        return True
    land_py = float(a.get("landSpace") or 0) * SQM_TO_PYEONG
    far = float(a.get("maxFar") or 0) / 100
    return land_py * (far + BASEMENT_RATIO) >= MIN_DEV_PYEONG


def main() -> None:
    if not DATA_PATH.exists():
        sys.exit(f"[ERR] {DATA_PATH} 없음 — 파이프라인(simulate, parcels) 먼저 실행")

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.fromtimestamp(DATA_PATH.stat().st_mtime).strftime("%Y-%m-%d")
    raw = payload.get("articles") or []
    articles = [_slim(strip_private(a)) for a in raw if _worth_keeping(a)]

    prev = find_previous_snapshot(generated_at)
    prev_prices: dict[str, float] = {}
    if prev is not None:
        keep_ids = {str(a.get("articleNo")) for a in articles}
        prev_prices = {k: v for k, v in snapshot_prices(prev).items() if k in keep_ids}

    out = {
        "generatedAt": generated_at,
        "prevSnapshotDate": prev.stem if prev is not None else None,
        "prevPrices": prev_prices,
        "articles": articles,
    }
    PUBLIC_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(PUBLIC_DATA_PATH, "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = PUBLIC_DATA_PATH.stat().st_size / 1024 / 1024
    print(f"[OK] {PUBLIC_DATA_PATH.relative_to(PROJECT_ROOT)} - "
          f"{len(articles)}/{len(raw)} articles, {size_mb:.1f}MB, "
          f"기준일 {generated_at}, 이전 snapshot {out['prevSnapshotDate']}")


if __name__ == "__main__":
    main()
