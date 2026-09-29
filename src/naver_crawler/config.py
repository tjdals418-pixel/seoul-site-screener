from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class Secrets:
    vworld_api_key: str = ""
    vworld_domain: str = ""           # 키 발급 시 등록한 도메인 (필수)
    naver_cookie: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        load_dotenv(override=False)
        return cls(
            vworld_api_key=os.getenv("VWORLD_API_KEY", ""),
            vworld_domain=os.getenv("VWORLD_DOMAIN", ""),
            naver_cookie=os.getenv("NAVER_COOKIE", ""),
        )


@dataclass
class AppConfig:
    """Typed view over the YAML config + .env secrets.

    Stage modules pull what they need from this single object instead of
    reaching into globals or hardcoding values.
    """

    raw: dict[str, Any]
    project_root: Path
    secrets: Secrets = field(default_factory=Secrets.from_env)

    def path(self, key: str) -> Path:
        rel = self.raw["paths"][key]
        return (self.project_root / rel).resolve()

    def section(self, name: str) -> dict[str, Any]:
        return self.raw[name]

    def ensure_dirs(self) -> None:
        for k in ("raw_dir", "interim_dir", "output_dir", "reference_dir"):
            self.path(k).mkdir(parents=True, exist_ok=True)


def load_config(config_path: str | Path, project_root: Path | None = None) -> AppConfig:
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    root = project_root or config_path.resolve().parent.parent
    cfg = AppConfig(raw=raw, project_root=root)
    cfg.ensure_dirs()
    return cfg
