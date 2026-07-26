from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import PrinterProfile


class Storage:
    def __init__(self) -> None:
        appdata = Path(os.environ.get("APPDATA", Path.home()))
        self.base = appdata / "PrintRescue"
        self.logs = self.base / "logs"
        self.backups = self.base / "backups"
        self.base.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.profiles_file = self.base / "profiles.json"
        self.settings_file = self.base / "settings.json"

    def load_profiles(self) -> list[PrinterProfile]:
        if not self.profiles_file.exists():
            profiles = [PrinterProfile()]
            self.save_profiles(profiles)
            return profiles
        try:
            raw = json.loads(self.profiles_file.read_text(encoding="utf-8"))
            profiles = [PrinterProfile.from_dict(x) for x in raw if isinstance(x, dict)]
            return profiles or [PrinterProfile()]
        except Exception:
            return [PrinterProfile()]

    def save_profiles(self, profiles: list[PrinterProfile]) -> None:
        self.profiles_file.write_text(
            json.dumps([p.to_dict() for p in profiles], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_settings(self) -> dict[str, Any]:
        try:
            return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self, value: dict[str, Any]) -> None:
        self.settings_file.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
