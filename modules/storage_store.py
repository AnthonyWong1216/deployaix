"""
Simple file-backed store for IBM Storage FlashSystem connection profiles.

Only the connection endpoint (IP / hostname) and the username are persisted —
the password is NEVER stored and must be re-entered on each connect.

Stored in ~/.powerpilot/storage_systems.json
"""

import json
import uuid
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_DIR = Path.home() / ".powerpilot"
STORE_FILE = STORE_DIR / "storage_systems.json"


class StorageStore:
    def __init__(self):
        STORE_DIR.mkdir(mode=0o700, exist_ok=True)
        if not STORE_FILE.exists():
            STORE_FILE.write_text("[]")

    def _load(self) -> List[Dict]:
        try:
            return json.loads(STORE_FILE.read_text())
        except Exception:
            return []

    def _save(self, data: List[Dict]):
        STORE_FILE.write_text(json.dumps(data, indent=2))

    def list(self) -> List[Dict]:
        """Return all saved storage systems (no passwords are ever stored)."""
        return self._load()

    def get(self, sys_id: str) -> Optional[dict]:
        for item in self._load():
            if item.get("id") == sys_id:
                return item
        return None

    def add(self, data: dict) -> dict:
        """Add a storage system, or update the existing one that matches the
        same (storage_ip, username) pair so we don't create duplicates."""
        storage_ip = (data.get("storage_ip") or "").strip()
        username = (data.get("username") or "").strip()
        name = (data.get("name") or storage_ip).strip()

        items = self._load()

        # De-duplicate on (storage_ip, username): update name if it already exists.
        for item in items:
            if (item.get("storage_ip") == storage_ip
                    and item.get("username") == username):
                item["name"] = name or item.get("name", "")
                self._save(items)
                return item

        entry = {
            "id": str(uuid.uuid4()),
            "name": name,
            "storage_ip": storage_ip,
            "username": username,
        }
        items.append(entry)
        self._save(items)
        return entry

    def remove(self, sys_id: str):
        items = [i for i in self._load() if i.get("id") != sys_id]
        self._save(items)
