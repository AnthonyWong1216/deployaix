"""
Simple file-backed store for HMC connection profiles.
Stored in ~/.powerpilot/hmcs.json
"""

import json
import uuid
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_DIR = Path.home() / ".powerpilot"
STORE_FILE = STORE_DIR / "hmcs.json"


class HMCStore:
    def __init__(self):
        STORE_DIR.mkdir(mode=0o700, exist_ok=True)
        if not STORE_FILE.exists():
            STORE_FILE.write_text("[]")

    def _load(self) -> List[Dict]:
        try:
            return json.loads(STORE_FILE.read_text())
        except Exception:
            return []

    def _save(self, data: list[dict]):
        STORE_FILE.write_text(json.dumps(data, indent=2))

    def list(self) -> List[Dict]:
        items = self._load()
        result = []
        for item in items:
            row = {k: v for k, v in item.items()
                   if k not in ("api_password", "session_id")}
            # Surface whether a session token is stored (not whether it's still valid)
            row["session_active"] = bool(item.get("session_id"))
            result.append(row)
        return result

    def get(self, hmc_id: str) -> Optional[dict]:
        for item in self._load():
            if item.get("id") == hmc_id:
                return item
        return None

    def add(self, data: dict) -> dict:
        items = self._load()
        entry = {
            "id": str(uuid.uuid4()),
            "name": data.get("name", ""),
            "host": data.get("host", ""),
            "username": data.get("username", "hscroot"),
            "ssh_port": int(data.get("ssh_port", 22)),
            "api_port": int(data.get("api_port", 443)),
            "auth_method": data.get("auth_method", "ssh_key"),
            "key_path": data.get("key_path", ""),
            "api_password": data.get("api_password", ""),
            "notes": data.get("notes", ""),
        }
        items.append(entry)
        self._save(items)
        return {k: v for k, v in entry.items() if k != "api_password"}

    def update(self, hmc_id: str, updates: dict):
        items = self._load()
        for item in items:
            if item.get("id") == hmc_id:
                item.update(updates)
        self._save(items)

    def remove(self, hmc_id: str):
        items = [i for i in self._load() if i.get("id") != hmc_id]
        self._save(items)
