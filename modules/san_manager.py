"""
SAN Manager — vendor-aware, read-only fabric inspection for SAN switches.

Currently supports Brocade FOS and Cisco MDS/NX-OS. Reuses the existing
SSHManager to run CLI commands over SSH, then parses the raw output into
structured aliases / zones / zonesets for the UI.

This module is intentionally READ-ONLY for now (list operations only).
Editing (alicreate/zonecreate/cfgsave/etc.) can be layered on later using
the same command-builder + run_hmc_command pattern.
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class SANManager:
    def __init__(self, ssh_manager):
        # Reuse the shared SSHManager (run_hmc_command works for any SSH host)
        self.ssh = ssh_manager

    # ──────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────

    def fetch_zoning(self, switch: dict, debug: bool = False) -> dict:
        """Return {ok, aliases, zones, zonesets, active_zoneset, raw?, error?}."""
        vendor = (switch.get("vendor") or "brocade").lower()
        if vendor == "cisco":
            return self._fetch_cisco(switch, debug)
        return self._fetch_brocade(switch, debug)

    def fetch_ports(self, switch: dict, debug: bool = False) -> dict:
        """Return {ok, switch_name, ports:[{index,state,status,speed,wwn,type}], raw?}."""
        vendor = (switch.get("vendor") or "brocade").lower()
        if vendor == "cisco":
            return self._fetch_ports_cisco(switch, debug)
        return self._fetch_ports_brocade(switch, debug)


    # ──────────────────────────────────────────────────────
    # SSH helper
    # ──────────────────────────────────────────────────────

    def _run(self, switch: dict, command: str) -> dict:
        return self.ssh.run_hmc_command(
            host=switch["host"],
            port=int(switch.get("ssh_port", 22)),
            username=switch.get("username", "admin"),
            key_path=switch.get("key_path") or None,
            password=switch.get("password") or None,
            command=command,
        )

    # ──────────────────────────────────────────────────────
    # Brocade FOS
    # ──────────────────────────────────────────────────────

    def _fetch_brocade(self, switch: dict, debug: bool) -> dict:
        commands = {
            "cfgshow":     "cfgshow",
            "cfgactvshow": "cfgactvshow",
        }
        raw = self.ssh.run_hmc_commands_batch(
            host=switch["host"],
            port=int(switch.get("ssh_port", 22)),
            username=switch.get("username", "admin"),
            key_path=switch.get("key_path") or None,
            password=switch.get("password") or None,
            commands=commands,
        )

        cfg = raw.get("cfgshow", {})
        if not cfg.get("ok") and not cfg.get("output"):
            result = {"ok": False,
                      "error": cfg.get("error", "cfgshow returned no data")}
            if debug:
                result["raw"] = raw
            return result

        parsed = self._parse_brocade_cfgshow(cfg.get("output", ""))
        active = self._parse_brocade_active(raw.get("cfgactvshow", {}).get("output", ""))
        parsed["active_zoneset"] = active or parsed.get("active_zoneset", "")
        parsed["ok"] = True
        if debug:
            parsed["raw"] = raw
        return parsed

    @staticmethod
    def _parse_brocade_cfgshow(text: str) -> dict:
        """Parse `cfgshow` output.

        Typical layout:
            Defined configuration:
             cfg:   PROD_CFG   zone1; zone2
             zone:  zone1      alias1; alias2
             alias: alias1     10:00:00:...
            Effective configuration:
             cfg:   PROD_CFG
             ...
        """
        aliases: List[Dict] = []
        zones: List[Dict] = []
        zonesets: List[Dict] = []
        active_zoneset = ""

        section = None          # "defined" | "effective"
        cur_kind = None         # "alias" | "zone" | "cfg"
        cur_name = None
        cur_members: List[str] = []

        def flush():
            nonlocal cur_kind, cur_name, cur_members
            if not cur_name:
                return
            members = [m.strip() for m in cur_members if m.strip()]
            if cur_kind == "alias":
                aliases.append({"name": cur_name, "members": members})
            elif cur_kind == "zone":
                zones.append({"name": cur_name, "members": members})
            elif cur_kind == "cfg":
                zonesets.append({"name": cur_name, "members": members})
            cur_kind = cur_name = None
            cur_members = []

        for line in text.splitlines():
            stripped = line.strip()
            low = stripped.lower()
            if low.startswith("defined configuration"):
                flush(); section = "defined"; continue
            if low.startswith("effective configuration"):
                flush(); section = "effective"; continue
            if not stripped:
                continue

            m = re.match(r"^(cfg|zone|alias):\s+(\S+)\s*(.*)$", stripped, re.IGNORECASE)
            if m:
                flush()
                kind = m.group(1).lower()
                name = m.group(2)
                rest = m.group(3)
                if section == "effective" and kind == "cfg":
                    active_zoneset = name
                    # effective section lists members too; skip re-adding cfg
                    cur_kind = None
                    continue
                cur_kind = kind
                cur_name = name
                cur_members = [x for x in re.split(r"[;\s]+", rest) if x]
            else:
                # continuation line — more members for the current object
                if cur_kind:
                    cur_members += [x for x in re.split(r"[;\s]+", stripped) if x]

        flush()
        return {
            "aliases": aliases,
            "zones": zones,
            "zonesets": zonesets,
            "active_zoneset": active_zoneset,
        }

    @staticmethod
    def _parse_brocade_active(text: str) -> str:
        """Extract the active cfg name from `cfgactvshow`."""
        for line in text.splitlines():
            m = re.search(r"cfg:\s+(\S+)", line, re.IGNORECASE)
            if m:
                return m.group(1)
        return ""

    # ──────────────────────────────────────────────────────
    # Cisco MDS / NX-OS
    # ──────────────────────────────────────────────────────

    def _fetch_cisco(self, switch: dict, debug: bool) -> dict:
        commands = {
            "device_alias": "show device-alias database",
            "zoneset":      "show zoneset",
            "zoneset_active": "show zoneset active",
        }
        raw = self.ssh.run_hmc_commands_batch(
            host=switch["host"],
            port=int(switch.get("ssh_port", 22)),
            username=switch.get("username", "admin"),
            key_path=switch.get("key_path") or None,
            password=switch.get("password") or None,
            commands=commands,
        )

        aliases = self._parse_cisco_aliases(raw.get("device_alias", {}).get("output", ""))
        zones, zonesets = self._parse_cisco_zoneset(raw.get("zoneset", {}).get("output", ""))
        active = self._parse_cisco_active(raw.get("zoneset_active", {}).get("output", ""))

        result = {
            "ok": True,
            "aliases": aliases,
            "zones": zones,
            "zonesets": zonesets,
            "active_zoneset": active,
        }
        if debug:
            result["raw"] = raw
        return result

    @staticmethod
    def _parse_cisco_aliases(text: str) -> List[Dict]:
        aliases = []
        for line in text.splitlines():
            m = re.search(r"device-alias name\s+(\S+)\s+pwwn\s+(\S+)", line, re.IGNORECASE)
            if m:
                aliases.append({"name": m.group(1), "members": [m.group(2)]})
        return aliases

    @staticmethod
    def _parse_cisco_zoneset(text: str) -> tuple:
        zones: List[Dict] = []
        zonesets: List[Dict] = []
        cur_set = None
        cur_zone = None
        for line in text.splitlines():
            stripped = line.strip()
            ms = re.match(r"zoneset name\s+(\S+)", stripped, re.IGNORECASE)
            if ms:
                cur_set = {"name": ms.group(1), "members": []}
                zonesets.append(cur_set)
                continue
            mz = re.match(r"zone name\s+(\S+)", stripped, re.IGNORECASE)
            if mz:
                cur_zone = {"name": mz.group(1), "members": []}
                zones.append(cur_zone)
                if cur_set is not None:
                    cur_set["members"].append(mz.group(1))
                continue
            mm = re.search(r"(?:pwwn|device-alias)\s+(\S+)", stripped, re.IGNORECASE)
            if mm and cur_zone is not None:
                cur_zone["members"].append(mm.group(1))
        return zones, zonesets

    @staticmethod
    def _parse_cisco_active(text: str) -> str:
        m = re.search(r"zoneset name\s+(\S+)", text, re.IGNORECASE)
        return m.group(1) if m else ""

    # ──────────────────────────────────────────────────────
    # Port status — Brocade (switchshow)
    # ──────────────────────────────────────────────────────

    def _fetch_ports_brocade(self, switch: dict, debug: bool) -> dict:
        raw = self.ssh.run_hmc_commands_batch(
            host=switch["host"],
            port=int(switch.get("ssh_port", 22)),
            username=switch.get("username", "admin"),
            key_path=switch.get("key_path") or None,
            password=switch.get("password") or None,
            commands={"switchshow": "switchshow"},
        )
        sw = raw.get("switchshow", {})
        if not sw.get("ok") and not sw.get("output"):
            result = {"ok": False, "error": sw.get("error", "switchshow returned no data")}
            if debug:
                result["raw"] = raw
            return result

        name, ports = self._parse_brocade_switchshow(sw.get("output", ""))
        result = {"ok": True, "switch_name": name or switch.get("name", ""),
                  "ports": ports}
        if debug:
            result["raw"] = raw
        return result

    @staticmethod
    def _parse_brocade_switchshow(text: str):
        """Parse `switchshow` port table.

        The port section looks like (columns vary slightly by FOS version):
            Index Port Address Media Speed State     Proto
            =============================================
              0   0   010000   id    N16   Online    FC  F-Port 10:00:...
              1   1   010100   id    --    No_Light   FC
        We extract index, speed, state and the trailing WWN/type if present.
        """
        name = ""
        ports = []
        in_table = False
        for line in text.splitlines():
            raw_line = line.rstrip()
            stripped = raw_line.strip()
            if not stripped:
                continue

            mn = re.match(r"switchName:\s*(\S+)", stripped, re.IGNORECASE)
            if mn:
                name = mn.group(1)
                continue

            low = stripped.lower()
            # Header row marks the start of the port table
            if low.startswith("index") and "state" in low:
                in_table = True
                continue
            if set(stripped) <= set("=-") and len(stripped) > 3:
                # separator line
                continue
            if not in_table:
                continue

            parts = stripped.split()
            if len(parts) < 2 or not parts[0].isdigit():
                continue

            index = parts[0]
            # State is the first token that looks like a known state keyword
            state = ""
            speed = ""
            for tok in parts[1:]:
                if re.match(r"^(Online|No_Light|No_Module|No_Sync|In_Sync|Laser_Flt|"
                            r"Port_Flt|Offline|Testing|Faulty|Mod_Val|No_SigDet|Disabled)$",
                            tok, re.IGNORECASE):
                    state = tok
                    break
            # Speed token looks like N16 / 16G / 32G / --
            for tok in parts[1:]:
                if re.match(r"^(N?\d+G?|--|AN|auto)$", tok, re.IGNORECASE) and tok not in (index,):
                    speed = tok
                    break

            # WWN if present anywhere on the line (Online F-Ports)
            wwn = ""
            mw = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){7})", stripped)
            if mw:
                wwn = mw.group(1)

            # Port type: F-Port / E-Port / etc.
            ptype = ""
            mt = re.search(r"\b([EFNGU]-?Port)\b", stripped, re.IGNORECASE)
            if mt:
                ptype = mt.group(1)

            up = bool(state) and state.lower() == "online"
            ports.append({
                "index":  index,
                "state":  state or "—",
                "speed":  speed or "—",
                "wwn":    wwn,
                "type":   ptype or "—",
                "up":     up,
            })
        return name, ports

    # ──────────────────────────────────────────────────────
    # Port status — Cisco (show interface brief)
    # ──────────────────────────────────────────────────────

    def _fetch_ports_cisco(self, switch: dict, debug: bool) -> dict:
        raw = self.ssh.run_hmc_commands_batch(
            host=switch["host"],
            port=int(switch.get("ssh_port", 22)),
            username=switch.get("username", "admin"),
            key_path=switch.get("key_path") or None,
            password=switch.get("password") or None,
            commands={"intf": "show interface brief"},
        )
        intf = raw.get("intf", {})
        if not intf.get("ok") and not intf.get("output"):
            result = {"ok": False, "error": intf.get("error", "show interface brief returned no data")}
            if debug:
                result["raw"] = raw
            return result

        ports = self._parse_cisco_intf_brief(intf.get("output", ""))
        result = {"ok": True, "switch_name": switch.get("name", ""), "ports": ports}
        if debug:
            result["raw"] = raw
        return result

    @staticmethod
    def _parse_cisco_intf_brief(text: str) -> List[Dict]:
        """Parse `show interface brief`.

        Rows look like:
            fc1/1   1   auto  on  up      swl   F  16    --
        Interface, VSAN, ..., Status column contains up/down/trunking/notConnected.
        """
        ports = []
        for line in text.splitlines():
            stripped = line.strip()
            m = re.match(r"^(fc\d+/\d+)\s+(.*)$", stripped, re.IGNORECASE)
            if not m:
                continue
            iface = m.group(1)
            rest = m.group(2).split()
            # Find the status token (up/down/trunking/notConnected/sfpAbsent/errDisabled)
            status = ""
            for tok in rest:
                if re.match(r"^(up|down|trunking|notConnected|sfpAbsent|errDisabled|"
                            r"init|offline|linkFailure)$", tok, re.IGNORECASE):
                    status = tok
                    break
            # Speed token like 16, 32, auto
            speed = ""
            for tok in rest:
                if re.match(r"^(\d+G?|auto)$", tok, re.IGNORECASE):
                    speed = tok
                    break
            # Port mode (F/E/TE/NP) — single letter tokens
            ptype = ""
            for tok in rest:
                if re.match(r"^(F|E|TE|NP|TF|SD|Fx)$", tok):
                    ptype = tok + "-Port"
                    break

            ports.append({
                "index":  iface,
                "state":  status or "—",
                "speed":  speed or "—",
                "wwn":    "",
                "type":   ptype or "—",
                "up":     status.lower() in ("up", "trunking"),
            })
        return ports

