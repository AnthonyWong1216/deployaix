"""
HMC REST API client (HMC Web Services API v1/v2).
Communicates with the HMC over HTTPS on port 443.
"""

import re
import logging
import urllib3
import requests
from typing import Dict, List, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

HMC_API_BASE = "https://{host}:{port}/rest/api"


class HMCApiClient:
    def __init__(self, host, port=443, username=None, password=None,
                 session_id=None):
        self.base = HMC_API_BASE.format(host=host, port=port)
        self.username = username
        self.password = password
        self.session_id = session_id
        # Single persistent session — reuses TCP connection and cookies
        self.session = requests.Session()
        self.session.verify = False

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _get(self, url, accept="application/atom+xml", timeout=30) -> requests.Response:
        """GET with session token header. Uses plain atom+xml by default —
        avoid the verbose IBM media-type strings that cause some HMC versions
        to stall generating the full schema-typed response."""
        headers = {
            "X-API-Session": self.session_id or "",
            "Accept": accept,
            "X-Audit-Memento": "PowerPilot",
        }
        logger.debug("GET %s", url)
        return self.session.get(url, headers=headers, timeout=timeout)

    # ──────────────────────────────────────────────────────
    # Session
    # ──────────────────────────────────────────────────────

    def login(self) -> dict:
        url = f"{self.base}/web/Logon"
        body = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<LogonRequest xmlns="http://www.ibm.com/xmlns/systems/power/'
            'firmware/web/mc/2012_10/" schemaVersion="V1_1_0">'
            '<Metadata><Atom/></Metadata>'
            f'<UserID kb="CUR" kxe="false">{self.username}</UserID>'
            f'<Password kb="CUR" kxe="false">{self.password}</Password>'
            '</LogonRequest>'
        )
        headers = {
            "Content-Type": "application/vnd.ibm.powervm.web+xml; type=LogonRequest",
            "Accept": "application/vnd.ibm.powervm.web+xml; type=LogonResponse",
            "X-Audit-Memento": "PowerPilot",
        }
        try:
            r = self.session.put(url, data=body, headers=headers, timeout=15)
            logger.debug("Logon HTTP %s: %s", r.status_code, r.text[:300])
            if r.status_code == 200:
                m = re.search(r"<X-API-Session[^>]*>\s*(.+?)\s*</X-API-Session>",
                              r.text, re.DOTALL)
                sid = m.group(1).strip() if m else ""
                self.session_id = sid
                return {"ok": True, "session_id": sid}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def logout(self):
        url = f"{self.base}/web/Logon"
        try:
            self.session.delete(url, headers={
                "X-API-Session": self.session_id or ""
            }, timeout=10)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────
    # Managed Systems
    # ──────────────────────────────────────────────────────

    def get_managed_systems(self) -> dict:
        url = f"{self.base}/uom/ManagedSystem"
        try:
            r = self._get(url, timeout=30)
            logger.debug("ManagedSystem HTTP %s  len=%d", r.status_code, len(r.text))
            logger.debug("ManagedSystem body (first 2000):\n%s", r.text[:2000])
            if r.status_code == 200:
                data = self._parse_managed_systems(r.text)
                return {"ok": True, "data": data, "raw": r.text}
            if r.status_code == 401:
                return {"ok": False, "error": "Session expired — please API Login again",
                        "need_login": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}",
                    "raw": r.text[:500]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _parse_managed_systems(self, xml_text: str) -> List[Dict]:
        systems = []
        entries = re.findall(r"<entry[^>]*>(.*?)</entry>", xml_text, re.DOTALL)
        logger.debug("_parse_managed_systems: found %d <entry> blocks", len(entries))
        for entry in entries:
            # UUID — prefer the <id> inside entry, fall back to href link
            uuid = self._extract(entry, "id")
            if not uuid:
                m = re.search(r"/ManagedSystem/([a-f0-9\-]{36})", entry)
                uuid = m.group(1) if m else ""

            # Name
            name = (self._extract(entry, "SystemName")
                    or self._extract(entry, "title")
                    or "—")

            # State
            state = self._extract(entry, "State")

            # Model — try compound field first, then decomposed
            model = self._extract(entry, "MachineTypeModelAndSerialNumber")
            if not model:
                mtype  = self._extract(entry, "MachineType")
                mmodel = self._extract(entry, "Model")
                mser   = self._extract(entry, "SerialNumber")
                parts  = [p for p in [mtype, mmodel] if p]
                model  = "-".join(parts) + (f" SN:{mser}" if mser else "")

            logger.debug("  system: uuid=%s name=%s state=%s model=%s",
                         uuid, name, state, model)
            systems.append({"id": uuid, "name": name, "state": state, "model": model})
        return systems

    # ──────────────────────────────────────────────────────
    # LPARs
    # ──────────────────────────────────────────────────────

    def get_lpars(self, system_id: str) -> dict:
        url = f"{self.base}/uom/ManagedSystem/{system_id}/LogicalPartition"
        try:
            r = self._get(url, timeout=30)
            logger.debug("LPARs HTTP %s  len=%d", r.status_code, len(r.text))
            if r.status_code == 200:
                return {"ok": True, "data": self._parse_lpars(r.text), "raw": r.text}
            if r.status_code == 401:
                return {"ok": False, "error": "Session expired — please API Login again",
                        "need_login": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _parse_lpars(self, xml_text: str) -> List[Dict]:
        lpars = []
        entries = re.findall(r"<entry[^>]*>(.*?)</entry>", xml_text, re.DOTALL)
        logger.debug("_parse_lpars: found %d <entry> blocks", len(entries))
        for entry in entries:
            lpar_id = self._extract(entry, "PartitionID")
            name    = (self._extract(entry, "PartitionName")
                       or self._extract(entry, "title")
                       or "—")
            state      = self._extract(entry, "PartitionState")
            lpar_type  = self._extract(entry, "PartitionType")
            uuid_m = re.search(r"/LogicalPartition/([a-f0-9\-]{36})", entry)
            uuid   = uuid_m.group(1) if uuid_m else self._extract(entry, "id")
            logger.debug("  lpar: uuid=%s id=%s name=%s state=%s",
                         uuid, lpar_id, name, state)
            lpars.append({
                "id": uuid, "lpar_id": lpar_id,
                "name": name, "state": state, "type": lpar_type,
            })
        return lpars

    # ──────────────────────────────────────────────────────
    # LPAR actions
    # ──────────────────────────────────────────────────────

    def lpar_action(self, system_id: str, lpar_id: str, action: str) -> dict:
        action_map = {
            "activate": "do/PowerOn",
            "shutdown": "do/PowerOff",
            "restart":  "do/PowerOff?restart=true",
            "softstop": "do/Shutdown",
        }
        path = action_map.get(action)
        if not path:
            return {"ok": False, "error": f"Unknown action: {action}"}
        url = (f"{self.base}/uom/ManagedSystem/{system_id}"
               f"/LogicalPartition/{lpar_id}/{path}")
        try:
            r = self.session.post(url, headers={
                "X-API-Session": self.session_id or "",
                "Content-Type": "application/vnd.ibm.powervm.uom+xml",
            }, timeout=30)
            if r.status_code in (200, 204):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ──────────────────────────────────────────────────────

    @staticmethod
    def _extract(text: str, tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>([^<]+)</{tag}>", text)
        return m.group(1).strip() if m else ""
