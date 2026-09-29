from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from naver_crawler.config import AppConfig
from naver_crawler.logging_setup import get_logger

log = get_logger(__name__)

StageFn = Callable[[AppConfig], None]


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    run: StageFn


class Checkpointer:
    """Records the last successfully completed stage so `--resume` can skip
    ahead. Stored as a tiny JSON file in the project root."""

    def __init__(self, path: Path, enabled: bool = True):
        self.path = path
        self.enabled = enabled

    def load(self) -> str | None:
        if not self.enabled or not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("last")
        except Exception:
            return None

    def save(self, stage_name: str) -> None:
        if not self.enabled:
            return
        self.path.write_text(
            json.dumps({"last": stage_name}, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class Pipeline:
    def __init__(self, stages: list[Stage], cfg: AppConfig):
        self.stages = stages
        self.cfg = cfg
        self._index = {s.name: i for i, s in enumerate(stages)}

    def run(
        self,
        *,
        from_stage: str | None = None,
        to_stage: str | None = None,
        resume: bool = False,
    ) -> None:
        cp = Checkpointer(self.cfg.path("checkpoint"))

        start = self._index.get(from_stage, 0) if from_stage else 0
        end = self._index.get(to_stage, len(self.stages) - 1) if to_stage else len(self.stages) - 1

        if resume:
            last = cp.load()
            if last in self._index:
                start = max(start, self._index[last] + 1)
                log.info("resuming after stage '%s'", last)

        for i in range(start, end + 1):
            stage = self.stages[i]
            log.info("=== [%d/%d] %s — %s ===", i + 1, len(self.stages), stage.name, stage.title)
            stage.run(self.cfg)
            cp.save(stage.name)

        log.info("pipeline done.")
