"""Weekly snapshot — simulated.json을 data/snapshots/YYYY-MM-DD.json으로 복사.

pipeline 마지막에 run_weekly.bat에서 호출해도 되고, 수동 실행도 가능.

사용:
    python scripts/snapshot.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "data" / "interim" / "simulated.json"
SNAP_DIR = PROJECT_ROOT / "data" / "snapshots"


def main(label: str | None = None):
    if not SRC.exists():
        print(f"[ERR] {SRC} 없음 — pipeline 먼저 실행")
        sys.exit(1)

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    date = label or datetime.now().strftime("%Y-%m-%d")
    dst = SNAP_DIR / f"{date}.json"

    # 같은 날짜 snapshot이 있으면 덮어쓰기
    if dst.exists():
        print(f"[WARN] {dst.name} 이미 존재 — 덮어쓰기")
    shutil.copy2(SRC, dst)

    # 유효성 검증
    with open(dst, "r", encoding="utf-8") as f:
        data = json.load(f)
    arts = data.get("articles", [])
    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"[OK] saved {dst.name} ({len(arts)} articles, {size_mb:.1f}MB)")

    # 기존 snapshot 목록
    snaps = sorted(SNAP_DIR.glob("*.json"))
    print(f"[INFO] 총 snapshot {len(snaps)}개:")
    for s in snaps[-5:]:
        sz = s.stat().st_size / 1024
        print(f"  - {s.name} ({sz:.0f}KB)")


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else None
    main(label)
