from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path


def _load_version() -> str:
    try:
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass
    try:
        return metadata.version("italiano-bvpn-protector")
    except metadata.PackageNotFoundError:
        return "unknown"


APP_VERSION = _load_version()
