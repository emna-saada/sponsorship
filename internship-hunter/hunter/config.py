import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    profile: dict
    search: dict
    email: dict
    ai: dict
    raw: dict = field(default_factory=dict)
    base_dir: Path = field(default=ROOT)

    @property
    def db_path(self) -> Path:
        return self.base_dir / "hunter.db"

    @property
    def outbox(self) -> Path:
        return self.base_dir / "outbox"

    @property
    def output(self) -> Path:
        return self.base_dir / "output"

    def path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.base_dir / p

    @staticmethod
    def secret(name: str) -> str | None:
        return os.environ.get(name) or None


def load(path: str | Path | None = None) -> Config:
    path = Path(path) if path else ROOT / "config.toml"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run: python -m hunter init")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(
        profile=data.get("profile", {}),
        search=data.get("search", {}),
        email=data.get("email", {}),
        ai=data.get("ai", {}),
        raw=data,
        base_dir=path.resolve().parent,
    )
