"""
DeployAIX - HMC & Power Server Management Web Application
Flask backend with SSH and HMC REST API support
"""

import os
import json
import logging
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit

from modules.ssh_manager import SSHManager
from modules.hmc_api import HMCApiClient
from modules.hmc_store import HMCStore
from modules.san_store import SANStore
from modules.san_manager import SANManager


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "deployaix-dev-secret-change-in-prod")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

ssh_manager = SSHManager()
hmc_store = HMCStore()
san_store = SANStore()
san_manager = SANManager(ssh_manager)


# ──────────────────────────────────────────────────────────
# Page routes
# ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/connect")
def connect_page():
    return render_template("connect.html")


@app.route("/lpars")
def lpars_page():
    return render_template("lpars.html")


@app.route("/console/<hmc_id>/<system_id>/<lpar_name>")
def console_page(hmc_id, system_id, lpar_name):
    """Standalone popup page for the LPAR vterm console."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return "HMC not found", 404
    return render_template(
        "console.html",
        hmc_id=hmc_id,
        system_id=system_id,
        lpar_name=lpar_name,
    )

@app.route("/topology")
def topology_page():
    return render_template("topology.html")


@app.route("/create_lpar", methods=["GET", "POST"])
def create_lpar():
    """Render the Create LPAR form (GET) or execute mksyscfg via SSH (POST)."""
    if request.method == "GET":
        return render_template("create_lpar.html")

    f = request.form

    # ── Identify the HMC and managed system ──────────────────
    hmc_id    = f.get("hmc_id")       # passed as hidden field (see below)
    system_id = f.get("managed_systems")
    hmc = hmc_store.get(hmc_id) if hmc_id else None

    # Fall back to any connected HMC when hmc_id not supplied via form
    if not hmc:
        all_hmcs = hmc_store.list()
        hmc = all_hmcs[0] if all_hmcs else None

    if not hmc:
        return jsonify({"error": "No HMC selected or configured"}), 400
    if not system_id:
        return jsonify({"error": "No managed system selected"}), 400

    # ── Build virtual_eth_adapters list ──────────────────────
    # mksyscfg format: slot/ieee/pvid/addl_vlans/is_trunk/is_required/vswitch///
    veth_parts = []
    slots      = f.getlist("veth_slot[]")
    pvids      = f.getlist("veth_pvid[]")
    vswitches  = f.getlist("veth_vswitch[]")
    addl_vlans = f.getlist("veth_addl_vlans[]")

    for i, slot in enumerate(slots):
        if not slot:
            continue
        pvid    = pvids[i]      if i < len(pvids)      else ""
        vswitch = vswitches[i]  if i < len(vswitches)  else ""
        addl    = addl_vlans[i] if i < len(addl_vlans) else ""
        veth_parts.append(f"{slot}/0/{pvid}/{addl}/0/0/{vswitch}///")

    virtual_eth_str = veth_parts   # list — ssh_manager wraps each spec individually

    # ── Build virtual_fc_adapters list ───────────────────────
    # Each spec: slot/client/vios_lpar_id/vios_lpar_name/vios_slot/wwpn1,wwpn2/is_required
    # Passed as a list so ssh_manager wraps each spec in ""..."" without
    # accidentally splitting on the comma inside the wwpn1,wwpn2 pair.
    vfc_parts     = []
    vfc_slots     = f.getlist("vfc_slot[]")
    vfc_vios      = f.getlist("vfc_vios[]")
    vfc_vios_slot = f.getlist("vfc_vios_slot[]")
    vfc_wwpn1     = f.getlist("vfc_wwpn1[]")
    vfc_wwpn2     = f.getlist("vfc_wwpn2[]")
    vfc_req_ded   = f.getlist("vfc_require_dedicated[]")

    for i, slot in enumerate(vfc_slots):
        if not slot:
            continue
        vios_name = vfc_vios[i]      if i < len(vfc_vios)      else ""
        vios_slot = vfc_vios_slot[i] if i < len(vfc_vios_slot) else ""
        wwpn1_raw = (vfc_wwpn1[i]    if i < len(vfc_wwpn1)     else "").replace(":", "").lower()
        wwpn2_raw = (vfc_wwpn2[i]    if i < len(vfc_wwpn2)     else "").replace(":", "").lower()
        req_ded   = vfc_req_ded[i]   if i < len(vfc_req_ded)   else "0"
        vios_id   = _resolve_vios_id(hmc, system_id, vios_name)
        # Format: slot/client/vios_id/vios_name/vios_slot/wwpn1,wwpn2/is_required
        vfc_parts.append(
            f"{slot}/client/{vios_id}/{vios_name}/{vios_slot}/{wwpn1_raw},{wwpn2_raw}/{req_ded}"
        )

    # Keep as list — ssh_manager wraps each entry in ""..."" individually
    virtual_fc_str = vfc_parts

    # ── Build virtual_scsi_adapters string ───────────────────
    # mksyscfg format: slot/client/vios_lpar_id/vios_lpar_name/vios_slot/0
    vscsi_parts     = []
    vscsi_slots     = f.getlist("vscsi_slot[]")
    vscsi_vios      = f.getlist("vscsi_vios[]")
    vscsi_vios_slot = f.getlist("vscsi_vios_slot[]")

    for i, slot in enumerate(vscsi_slots):
        if not slot:
            continue
        vios_name = vscsi_vios[i]      if i < len(vscsi_vios)      else ""
        vios_slot = vscsi_vios_slot[i] if i < len(vscsi_vios_slot) else ""
        vios_id   = _resolve_vios_id(hmc, system_id, vios_name)
        vscsi_parts.append(f"{slot}/client/{vios_id}/{vios_name}/{vios_slot}/0")

    virtual_scsi_str = vscsi_parts   # list — ssh_manager wraps each spec individually

    # ── Assemble mksyscfg parameter dict ─────────────────────
    params = {
        "name":                       f.get("name"),
        "lpar_id":                    f.get("lpar_id"),
        "lpar_env":                   f.get("lpar_env", "aixlinux"),
        "profile_name":               f.get("profile_name", "default_profile"),
        "boot_mode":                  f.get("boot_mode", "norm"),
        "lpar_proc_compat_mode":      f.get("lpar_proc_compat_mode", "default"),
        "max_virtual_slots":          f.get("max_virtual_slots", "100"),
        "conn_monitoring":            "1" if f.get("conn_monitoring") else "0",
        "sync_curr_profile":          "1" if f.get("sync_curr_profile") else "0",
        "allow_perf_collection":      "1" if f.get("shared_proc_pool_util_auth") else "0",
        "proc_mode":                  f.get("proc_mode", "shared"),
        "sharing_mode":               f.get("sharing_mode", "uncap"),
        "min_proc_units":             f.get("min_proc_units"),
        "desired_proc_units":         f.get("desired_proc_units"),
        "max_proc_units":             f.get("max_proc_units"),
        "min_procs":                  f.get("min_procs"),
        "desired_procs":              f.get("desired_procs"),
        "max_procs":                  f.get("max_procs"),
        "uncap_weight":               f.get("uncap_weight"),
        "min_mem":                    f.get("min_mem"),
        "desired_mem":                f.get("desired_mem"),
        "max_mem":                    f.get("max_mem"),
        "virtual_eth_adapters":       virtual_eth_str,
        "virtual_fc_adapters":        virtual_fc_str,
        "virtual_scsi_adapters":      virtual_scsi_str,
    }

    result = ssh_manager.create_lpar(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        managed_system=system_id,
        params=params,
    )

    if result.get("ok"):
        return jsonify({
            "ok":      True,
            "message": result.get("message", "LPAR created successfully."),
            "command": result.get("command", ""),
        }), 201
    return jsonify({
        "ok":      False,
        "error":   result.get("error", "mksyscfg failed"),
        "stderr":  result.get("stderr", ""),
        "command": result.get("command", ""),
    }), 400


def _resolve_vios_id(hmc: dict, system_id: str, vios_name: str) -> str:
    """Look up the numeric lpar_id of a named VIOS via lssyscfg. Returns '0' on failure."""
    if not vios_name:
        return "0"
    result = ssh_manager.run_hmc_command(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=(f'lssyscfg -r lpar -m "{system_id}" '
                 f'--filter "lpar_names={vios_name}" -F lpar_id'),
    )
    if result.get("ok"):
        return result["output"].strip().splitlines()[0].strip() or "0"
    return "0"

@app.route("/managed-systems")
def managed_systems_page():
    return render_template("managed_systems.html")


@app.route("/virtual-networks")
def virtual_networks_page():
    return render_template("virtual_networks.html")


@app.route("/storage")
def storage_page():
    return render_template("storage.html")


@app.route("/jobs")
def jobs_page():
    return render_template("jobs.html")


@app.route("/san-switches")
def san_switches_page():
    return render_template("san_switches.html")


@app.route("/zoning")
def zoning_page():
    return render_template("zoning.html")


@app.route("/vfc-map")
def vfc_map_page():
    return render_template("vfc_map.html")



# ──────────────────────────────────────────────────────────
# HMC connection management API
# ──────────────────────────────────────────────────────────

@app.route("/api/hmcs", methods=["GET"])
def list_hmcs():
    """Return all saved HMC connections."""
    return jsonify(hmc_store.list())


@app.route("/api/hmcs", methods=["POST"])
def add_hmc():
    """Save a new HMC entry (no connection attempt yet)."""
    data = request.get_json(force=True)
    required = ["name", "host"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    entry = hmc_store.add(data)
    return jsonify(entry), 201


@app.route("/api/hmcs/<hmc_id>", methods=["DELETE"])
def delete_hmc(hmc_id):
    hmc_store.remove(hmc_id)
    return jsonify({"ok": True})


@app.route("/api/hmcs/<hmc_id>/test-ssh", methods=["POST"])
def test_ssh(hmc_id):
    """Test SSH connectivity to an HMC."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    result = ssh_manager.test_connection(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=data.get("username", hmc.get("username", "hscroot")),
        key_path=data.get("key_path") or hmc.get("key_path"),
        password=data.get("password"),
    )
    return jsonify(result)


@app.route("/api/hmcs/<hmc_id>/push-key", methods=["POST"])
def push_ssh_key(hmc_id):
    """Copy an SSH public key to the HMC (ssh-copy-id equivalent)."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    result = ssh_manager.push_public_key(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=data.get("username", hmc.get("username", "hscroot")),
        password=data.get("password", ""),
        public_key_path=data.get("public_key_path", "~/.ssh/id_rsa.pub"),
    )
    return jsonify(result)


@app.route("/api/ssh-keys", methods=["GET"])
def list_ssh_keys():
    """Return SSH keys found in ~/.ssh/."""
    return jsonify(ssh_manager.list_local_keys())


@app.route("/api/ssh-keys/generate", methods=["POST"])
def generate_ssh_key():
    """Generate a new RSA/ED25519 key pair."""
    data = request.get_json(force=True) or {}
    result = ssh_manager.generate_key(
        key_type=data.get("key_type", "ed25519"),
        key_name=data.get("key_name", "id_deployaix"),
        passphrase=data.get("passphrase", ""),
        comment=data.get("comment", "deployaix"),
    )
    return jsonify(result)


# ──────────────────────────────────────────────────────────
# HMC REST API
# ──────────────────────────────────────────────────────────

@app.route("/api/hmcs/<hmc_id>/api-login", methods=["POST"])
def api_login(hmc_id):
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        username=data.get("username", hmc.get("username", "hscroot")),
        password=data.get("password", hmc.get("api_password", "")),
    )
    result = client.login()
    if result.get("session_id"):
        hmc_store.update(hmc_id, {"session_id": result["session_id"],
                                   "api_client": True})
    return jsonify(result)


@app.route("/api/hmcs/<hmc_id>/api-logout", methods=["POST"])
def api_logout(hmc_id):
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    if hmc.get("session_id"):
        client = HMCApiClient(
            host=hmc["host"],
            port=int(hmc.get("api_port", 443)),
            session_id=hmc["session_id"],
        )
        client.logout()
        hmc_store.update(hmc_id, {"session_id": "", "api_client": False})
    return jsonify({"ok": True})


@app.route("/api/hmcs/<hmc_id>/api-status", methods=["GET"])
def api_status(hmc_id):
    """Probe whether the stored session token is still alive."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    sid = hmc.get("session_id", "")
    if not sid:
        return jsonify({"active": False, "reason": "no_session"})
    # Lightweight probe: fetch the top-level /rest/api/uom feed (tiny response)
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        session_id=sid,
    )
    try:
        r = client._get(f"{client.base}/uom", timeout=8)
        if r.status_code == 200:
            return jsonify({"active": True})
        if r.status_code == 401:
            hmc_store.update(hmc_id, {"session_id": "", "api_client": False})
            return jsonify({"active": False, "reason": "expired"})
        return jsonify({"active": False, "reason": f"HTTP {r.status_code}"})
    except Exception as exc:
        return jsonify({"active": False, "reason": str(exc)})


@app.route("/api/hmcs/<hmc_id>/managed-systems", methods=["GET"])
def get_managed_systems(hmc_id):
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404

    method = request.args.get("method", "auto")  # auto | ssh | api

    # ── SSH fast-path ──────────────────────────────────────────────
    use_ssh = (method == "ssh") or (method == "auto" and not hmc.get("session_id"))
    if use_ssh:
        result = ssh_manager.run_hmc_command(
            host=hmc["host"],
            port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            command="lssyscfg -r sys -F name:state:type_model",
        )
        if result.get("ok"):
            systems = []
            for line in result["output"].splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                name  = parts[0] if len(parts) > 0 else "—"
                state = parts[1] if len(parts) > 1 else "—"
                model = parts[2] if len(parts) > 2 else "—"
                systems.append({"id": name, "name": name,
                                 "state": state, "model": model})
            return jsonify({"ok": True, "data": systems, "method": "ssh"})
        # SSH failed — fall through to API if session available
        if not hmc.get("session_id"):
            return jsonify({"ok": False,
                            "error": result.get("error", "SSH failed"),
                            "need_login": True, "method": "ssh_failed"})

    # ── REST API path ──────────────────────────────────────────────
    if not hmc.get("session_id"):
        return jsonify({"ok": False,
                        "error": "No API session — click 'API Login' on the Connect page first",
                        "need_login": True})
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        session_id=hmc.get("session_id"),
    )
    result = client.get_managed_systems()
    logger.debug("ManagedSystem raw XML:\n%s", result.get("raw", "")[:2000])
    result.pop("raw", None)
    result["method"] = "api"
    return jsonify(result)


@app.route("/api/hmcs/<hmc_id>/managed-systems/raw", methods=["GET"])
def get_managed_systems_raw(hmc_id):
    """Debug endpoint — returns the raw XML from the HMC."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    if not hmc.get("session_id"):
        return jsonify({"error": "No API session"}), 401
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        session_id=hmc.get("session_id"),
    )
    result = client.get_managed_systems()
    return app.response_class(result.get("raw", ""), mimetype="text/xml")


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/lpars", methods=["GET"])
def get_lpars(hmc_id, system_id):
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404

    method = request.args.get("method", "auto")
    use_ssh = (method == "ssh") or (method == "auto" and not hmc.get("session_id"))

    if use_ssh:
        # lssyscfg -r lpar -m <system> -F name:lpar_id:state:lpar_env:rmc_ipaddr:os_version
        cmd = (f'lssyscfg -r lpar -m "{system_id}" '
               f'-F name:lpar_id:state:lpar_env:rmc_ipaddr:os_version')
        result = ssh_manager.run_hmc_command(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            command=cmd,
        )
        if result.get("ok"):
            lpars = []
            for line in result["output"].splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                lpars.append({
                    "name":       parts[0] if len(parts) > 0 else "—",
                    "lpar_id":    parts[1] if len(parts) > 1 else "—",
                    "id":         parts[0] if len(parts) > 0 else "—",
                    "state":      parts[2] if len(parts) > 2 else "—",
                    "type":       parts[3] if len(parts) > 3 else "—",
                    "ip_address": parts[4] if len(parts) > 4 else "—",
                    "os_version": parts[5] if len(parts) > 5 else "—",
                    "profile":    "—",
                })
            return jsonify({"ok": True, "data": lpars, "method": "ssh"})
        if not hmc.get("session_id"):
            return jsonify({"ok": False, "error": result.get("error", "SSH failed"),
                            "need_login": True})

    # REST API fallback
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        session_id=hmc.get("session_id"),
    )
    result = client.get_lpars(system_id)
    result.pop("raw", None)
    result["method"] = "api"
    return jsonify(result)


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/lpars/<path:lpar_id>/detail",
           methods=["GET"])
def get_lpar_detail(hmc_id, system_id, lpar_id):
    """Return CPU, memory, virtual adapters for a single LPAR via SSH lssyscfg."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404

    # Run ALL queries on a single SSH connection to avoid the HMC
    # dropping subsequent connections after the first exec_command.
    m = f'"{system_id}"'
    f = f'"lpar_names={lpar_id}"'
    raw = ssh_manager.run_hmc_commands_batch(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        commands={
            "cpu": (
                f'lshwres -r proc --level lpar -m {m} --filter {f} '
                f'-F lpar_name:curr_procs:curr_proc_units:curr_sharing_mode:'
                f'curr_min_procs:curr_max_procs:curr_min_proc_units:curr_max_proc_units:'
                f'run_procs:pend_procs:run_uncap_weight'
            ),
            "mem": (
                f'lshwres -r mem --level lpar -m {m} --filter {f} '
                f'-F lpar_name:curr_mem:run_mem:pend_mem:run_min_mem:curr_max_mem'
            ),
            "veth": (
                f'lshwres -r virtualio --rsubtype eth --level lpar -m {m} --filter {f} '
                f'-F lpar_name:slot_num:port_vlan_id:addl_vlan_ids:ieee_virtual_eth:mac_addr'
            ),
            "vscsi": (
                f'lshwres -r virtualio --rsubtype scsi --level lpar -m {m} --filter {f} '
                f'-F lpar_name:slot_num:remote_lpar_name:remote_slot_num'
            ),
            "vfc": (
                f'lshwres -r virtualio --rsubtype fc --level lpar -m {m} --filter {f} '
                f'-F lpar_name:slot_num:wwpns:remote_lpar_name:remote_slot_num'
            ),
            "phyio": (
                f'lshwres -r io --rsubtype slot -m {m} --filter {f} '
                f'-F lpar_name:drc_name:description:feature_codes'
            ),
            # Physical Fibre Channel HBAs assigned to the LPAR.
            # lshwres -r io --rsubtype slot returns the physical location
            # (drc_name / phys_loc) and description of every physical adapter
            # owned by the partition; we later filter for Fibre Channel ones
            # and pull each port's WWPN from lsnportlogin.
            "phyfc": (
                f'lshwres -r io --rsubtype slot -m {m} --filter {f} '
                f'-F lpar_name:drc_index:drc_name:description:phys_loc'
            )
        }
    )
    cpu_r    = raw["cpu"]
    mem_r    = raw["mem"]
    veth_r   = raw["veth"]
    vscsi_r  = raw["vscsi"]
    vfc_r    = raw["vfc"]
    phyio_r  = raw["phyio"]
    phyfc_r  = raw["phyfc"]


    def parse_lines(res, fields):
        """Parse colon-separated lines; skip lines that start with error text."""
        if not res.get("ok"):
            return []
        rows = []
        for line in res["output"].splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip header or error lines that don't look like data
            if line.startswith("No results") or line.lower().startswith("error"):
                continue
            parts = line.split(":")
            rows.append(dict(zip(fields, parts)))
        return rows

    cpu_fields    = ["lpar_name","curr_procs","curr_proc_units","curr_sharing_mode",
                     "curr_min_procs","curr_max_procs","curr_min_proc_units","curr_max_proc_units",
                     "run_procs","pend_procs","uncap_weight"]
    mem_fields    = ["lpar_name","curr_mem","run_mem","pend_mem","min_mem","max_mem"]
    veth_fields   = ["lpar_name","slot","pvid","addl_vlans","ieee","mac"]
    vscsi_fields  = ["lpar_name","slot","remote_lpar","remote_slot"]
    vfc_fields    = ["lpar_name","slot","wwpns","remote_lpar","remote_slot"]
    phyio_fields  = ["lpar_name","drc_name","description","feature_codes"]
    phyfc_fields  = ["lpar_name","drc_index","drc_name","description","phys_loc"]

    def parse_phyfc(res):
        """Parse physical I/O slots and keep only Fibre Channel HBAs.

        The HMC ``lshwres -r io --rsubtype slot`` output gives us the physical
        location code (``drc_name`` / ``phys_loc``) and the adapter description
        for every physical adapter owned by the partition.  We keep only the
        Fibre Channel ones.  The port WWPN is *not* available from lshwres and
        is filled in later (see ``_enrich_phyfc_wwpn``) by querying the VIOS.

        Returns a list of dicts shaped for the frontend:
            {lpar_name, adapter_id, port_index, location, description, wwpn}
        """
        rows = parse_lines(res, phyfc_fields)
        out = []
        for i, r in enumerate(rows):
            desc = (r.get("description") or "").lower()
            # Only keep physical Fibre Channel adapters
            if "fibre" not in desc and "fiber" not in desc and "fc" not in desc:
                continue
            location = r.get("phys_loc") or r.get("drc_name") or ""
            # Derive a stable adapter id / port index from the location code.
            # e.g. U78D5.001.ABC-P1-C2-T1  → adapter "C2", port "T1"
            adapter_id = ""
            port_index = ""
            for token in location.split("-"):
                token = token.strip()
                if token.upper().startswith("C") and token[1:].isdigit():
                    adapter_id = token
                elif token.upper().startswith("T") and token[1:].isdigit():
                    port_index = token
            out.append({
                "lpar_name":   r.get("lpar_name", ""),
                "adapter_id":  adapter_id or r.get("drc_index", str(i)),
                "port_index":  port_index or "—",
                "location":    location or "—",
                "description": r.get("description", ""),
                "wwpn":        "",   # filled in by _enrich_phyfc_wwpn
            })
        return out

    def _norm_loc(loc):
        """Normalise a physical location code for matching between the HMC
        (lshwres phys_loc) and the VIOS (lscfg second column).

        The HMC often prefixes the code with the machine/serial (e.g.
        ``U78C9.001.WXYZ123-P1-C11-T1``) while lscfg reports the same trailing
        ``...-P1-C11-T1``.  Compare on the ``-P.../-C.../-T...`` tail so both
        representations line up.
        """
        loc = (loc or "").strip().upper()
        # Keep everything from the first '-P' onwards; that tail is stable
        idx = loc.find("-P")
        return loc[idx:] if idx != -1 else loc

    def _enrich_phyfc_wwpn(phyfc_rows):
        """Fill in each physical FC port's WWPN + link status by querying the VIOS.

        Collection method (as confirmed on the VIOS):

            viosvrcmd -m <system> -p <VIOS_lpar> -c "fcstat fcsX"

        The fcstat output contains::

            ...
            World Wide Node Name: 0x2000F4C7AA652388   <-- WWPN (node name)
            ...
            Attention Type:   Link Up                  <-- link status

        Because ``fcstat`` does not print the physical location code, we also
        run ``lscfg -vl fcsX`` for every device to obtain the location code and
        match it back to the ``lshwres`` phyfc rows.

        We:
          1. list the fcs* devices on the VIOS (lsdev),
          2. run ``lscfg -vl fcsX`` (location) and ``fcstat fcsX`` (WWPN + link)
             for each device over a single batched SSH connection,
          3. match each device's location code to the lshwres phyfc row and
             copy in the World Wide Node Name and link status.
        """
        if not phyfc_rows:
            return phyfc_rows

        # The detail view is per-LPAR; treat that LPAR as the VIOS to query.
        vios = lpar_id

        # ── 1. list fcs* devices on the VIOS ──
        lsdev_cmd = (f'viosvrcmd -m {m} -p "{vios}" '
                     f'-c "lsdev -type adapter -field name" | grep -i fcs')
        lsdev_res = ssh_manager.run_hmc_command(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            command=lsdev_cmd,
        )
        fcs_devs = []
        if lsdev_res.get("ok"):
            for line in lsdev_res["output"].splitlines():
                tok = line.strip().split()
                if tok and tok[0].lower().startswith("fcs"):
                    if tok[0] not in fcs_devs:
                        fcs_devs.append(tok[0])
        if not fcs_devs:
            return phyfc_rows

        # ── 2. lscfg (location) + fcstat (WWPN & link) per device, one batch ──
        batch_cmds = {}
        for dev in fcs_devs:
            batch_cmds[f"loc::{dev}"] = (
                f'viosvrcmd -m {m} -p "{vios}" -c "lscfg -vl {dev}"')
            batch_cmds[f"stat::{dev}"] = (
                f'viosvrcmd -m {m} -p "{vios}" '
                f'-c "fcstat {dev}" | grep -iE "World Wide Node Name|Attention Type"')
        batch_raw = ssh_manager.run_hmc_commands_batch(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            commands=batch_cmds,
        )

        # ── 3. per device: location code (from lscfg) + wwpn/link (from fcstat)
        loc_to_info = {}
        for dev in fcs_devs:
            # location code from lscfg header line
            dev_loc = ""
            loc_res = batch_raw.get(f"loc::{dev}", {})
            if loc_res.get("ok"):
                for line in loc_res["output"].splitlines():
                    s = line.strip()
                    if s.lower().startswith(dev.lower()):
                        parts = s.split()
                        if len(parts) >= 2:
                            dev_loc = parts[1]
                            break

            # WWPN (World Wide Node Name) + link status from fcstat
            wwpn = ""
            link = ""
            stat_res = batch_raw.get(f"stat::{dev}", {})
            if stat_res.get("ok"):
                for line in stat_res["output"].splitlines():
                    s = line.strip()
                    low = s.lower()
                    if "world wide node name" in low:
                        val = s.split(":", 1)[-1].strip()
                        # strip a leading 0x and keep hex digits only
                        val = val[2:] if val.lower().startswith("0x") else val
                        wwpn = "".join(ch for ch in val
                                       if ch in "0123456789abcdefABCDEF")
                    elif "attention type" in low:
                        link = s.split(":", 1)[-1].strip()

            if dev_loc:
                loc_to_info[_norm_loc(dev_loc)] = {
                    "dev": dev, "wwpn": wwpn, "link": link,
                }

        # ── 4. merge WWPN + link status into the lshwres phyfc rows by location
        for row in phyfc_rows:
            info = loc_to_info.get(_norm_loc(row.get("location", "")))
            if info:
                row["wwpn"] = info["wwpn"]
                row["device"] = info["dev"]
                row["link_status"] = info["link"]
        return phyfc_rows



    # Collect per-resource errors (None = success/no-data, string = error msg)
    raw_results = [
        ("cpu",    cpu_r),  ("mem",  mem_r),
        ("veth",   veth_r), ("vscsi",vscsi_r), ("vfc",  vfc_r),
        ("phyio", phyio_r), ("phyfc", phyfc_r)
    ]
    errors = {k: v.get("error") for k, v in raw_results if not v.get("ok")}


    # Always include raw output in debug mode so the UI can show it
    debug = request.args.get("debug") == "1"

    # Build the physical FC list from lshwres, then enrich each port's WWPN
    # by querying the VIOS with "lscfg -vl fcsX" (matched by location code).
    phyfc_rows = _enrich_phyfc_wwpn(parse_phyfc(phyfc_r))

    result = {
        "ok":    True,
        "cpu":   parse_lines(cpu_r,    cpu_fields),
        "mem":   parse_lines(mem_r,    mem_fields),
        "veth":  parse_lines(veth_r,   veth_fields),
        "vscsi": parse_lines(vscsi_r,  vscsi_fields),
        "vfc":   parse_lines(vfc_r,    vfc_fields),
        "phyio": parse_lines(phyio_r, phyio_fields),
        "phyfc": phyfc_rows,
        "errors": errors,
    }

    if debug:
        result["raw"] = {k: v for k, v in raw.items()}
    return jsonify(result)



@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/vfc-topology",
           methods=["GET"])
def get_vfc_topology(hmc_id, system_id):
    """Return the Virtual Fibre Channel (NPIV) topology for a managed system.

    Runs, over a single SSH connection to the HMC:
      1. lshwres -r virtualio --rsubtype fc --level lpar -m <system>
         → every virtual FC adapter mapping (client + server side).
      2. viosvrcmd -m <system> -p <VIOS> -c "lsmap -all -npiv -fmt ,"
         → the vfchost ↔ fcs ↔ client mapping as seen from each VIOS.

    The raw command text is returned verbatim so the UI can render it above
    the topology graph, together with parsed rows used to draw the graph.
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    m = f'"{system_id}"'

    # ── Step 1: lshwres for every virtual FC adapter on the system ──
    lshwres_cmd = (
        f'lshwres -r virtualio --rsubtype fc --level lpar -m {m} '
        f'-F lpar_name:lpar_id:slot_num:adapter_type:remote_lpar_name:'
        f'remote_lpar_id:remote_slot_num:wwpns'
    )
    lshwres_res = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=lshwres_cmd,
    )

    # Parse lshwres rows and discover the VIOS partitions (adapter_type=server)
    fc_fields = ["lpar_name", "lpar_id", "slot_num", "adapter_type",
                 "remote_lpar_name", "remote_lpar_id", "remote_slot_num", "wwpns"]
    fc_rows = []
    vios_names = []
    if lshwres_res.get("ok"):
        for line in lshwres_res["output"].splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("No results") or line.lower().startswith("error"):
                continue
            parts = line.split(":")
            row = dict(zip(fc_fields, parts))
            fc_rows.append(row)
            if row.get("adapter_type") == "server" and row.get("lpar_name"):
                if row["lpar_name"] not in vios_names:
                    vios_names.append(row["lpar_name"])

    # ── Step 2: lsmap -all -npiv on each discovered VIOS ──
    lsmap_cmds = {
        name: (f'viosvrcmd -m {m} -p "{name}" '
               f'-c "lsmap -all -npiv -fmt ,"')
        for name in vios_names
    }
    lsmap_raw = {}
    if lsmap_cmds:
        lsmap_raw = ssh_manager.run_hmc_commands_batch(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            commands=lsmap_cmds,
        )

    # lsmap -fmt , output columns (comma-separated):
    #   1st value  = vfchost name/number (server virtual FC adapter)
    #   2nd value  = physloc of the vfchost; the number after "-C" is the
    #                VIOS slot number that hosts this vfchost
    #   ...
    #   last value = physloc of the remote (client) virtual FC adapter; the
    #                number after "-C" is the client LPAR slot number
    # name,physloc,clntid,clntname,clntos,status,fc,fcphysloc,ports,flags,vfcclient,vfcclientdrc
    lsmap_fields = ["vfchost", "physloc", "clntid", "clntname", "clntos",
                    "status", "fc", "fcphysloc", "ports", "flags",
                    "vfcclient", "vfcclientdrc"]

    def slot_after_c(physloc: str) -> str:
        """Extract the slot number that follows '-C' in a physical location code.

        e.g. 'U8286.42A.XXXXXXX-V2-C12' -> '12'. Returns '' if not present.
        """
        if not physloc:
            return ""
        for token in physloc.split("-"):
            token = token.strip()
            if token.upper().startswith("C") and token[1:].isdigit():
                return token[1:]
        return ""

    lsmap_parsed = {}
    for name, res in lsmap_raw.items():
        rows = []
        if res.get("ok"):
            for line in res["output"].splitlines():
                line = line.strip()
                if not line or line.startswith(("name,", "No results")):
                    continue
                if line.lower().startswith("error"):
                    continue
                parts = line.split(",")
                row = dict(zip(lsmap_fields, parts))
                # Strip whitespace from every field so that blank/space-only
                # values (e.g. clntname=" " for NOT_LOGGED_IN entries) are
                # normalised to empty strings and won't create phantom nodes.
                for k in row:
                    row[k] = row[k].strip()
                # Derive the VIOS slot (from vfchost physloc) and the client
                # LPAR slot (from the remote/client vfc physloc).
                row["vios_slot"] = slot_after_c(row.get("physloc", ""))
                row["client_slot"] = slot_after_c(
                    row.get("vfcclientdrc") or row.get("fcphysloc") or "")
                rows.append(row)
        lsmap_parsed[name] = rows


    # ── Assemble raw command text for display above the graph ──
    commands = []
    commands.append({
        "title": "lshwres — virtual FC adapters",
        "command": lshwres_cmd,
        "output": (lshwres_res.get("output") if lshwres_res.get("ok")
                   else lshwres_res.get("error", "command failed")) or "(no output)",
        "ok": bool(lshwres_res.get("ok")),
    })
    for name in vios_names:
        res = lsmap_raw.get(name, {})
        commands.append({
            "title": f"lsmap -all -npiv on VIOS {name}",
            "command": lsmap_cmds[name],
            "output": (res.get("output") if res.get("ok")
                       else res.get("error", "command failed")) or "(no output)",
            "ok": bool(res.get("ok")),
        })

    return jsonify({
        "ok": True,
        "system_id": system_id,
        "vios": vios_names,
        "fc_adapters": fc_rows,
        "lsmap": lsmap_parsed,
        "commands": commands,
    })


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/vscsi-topology",
           methods=["GET"])
def get_vscsi_topology(hmc_id, system_id):
    """Return the virtual SCSI topology for a managed system.

    Runs, over a single SSH connection to the HMC:
      1. lshwres -r virtualio --rsubtype scsi --level lpar -m <system>
         → every vSCSI adapter mapping (server VIOS side + client LPAR side).
      2. viosvrcmd -m <system> -p <VIOS> -c "lsmap -all -fmt ,"
         → the vhostX ↔ backing-device ↔ client-slot mapping from each VIOS.

    JOIN KEY: lshwres row slot_num (server adapter) == lsmap row svr_slot
    The joined data drives the VIOS → vSCSI Target → Client LPAR graph.
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    m = f'"{system_id}"'

    # ── Step 1: lshwres for every virtual SCSI adapter on the system ──
    lshwres_cmd = (
        f'lshwres -r virtualio --rsubtype scsi --level lpar -m {m} '
        f'-F lpar_name:lpar_id:slot_num:adapter_type:'
        f'remote_lpar_name:remote_lpar_id:remote_slot_num'
    )
    lshwres_res = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=lshwres_cmd,
    )

    # Parse lshwres rows; collect VIOS names from server-side adapter rows
    scsi_fields = ["lpar_name", "lpar_id", "slot_num", "adapter_type",
                   "remote_lpar_name", "remote_lpar_id", "remote_slot_num"]
    scsi_rows = []
    vios_names = []
    if lshwres_res.get("ok"):
        for line in lshwres_res["output"].splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("No results") or line.lower().startswith("error"):
                continue
            parts = line.split(":")
            row = dict(zip(scsi_fields, parts))
            scsi_rows.append(row)
            if row.get("adapter_type") == "server" and row.get("lpar_name"):
                if row["lpar_name"] not in vios_names:
                    vios_names.append(row["lpar_name"])

    # ── Step 2: lsmap -all on each discovered VIOS ──
    # lsmap -fmt , output (comma-separated):
    #   vhostX, physloc, svr_vtd, backing_device, backing_type, status
    # The physloc "-C<N>" slot number is the VIOS server-adapter slot (join key).
    lsmap_cmds = {
        name: (f'viosvrcmd -m {m} -p "{name}" '
               f'-c "lsmap -all -fmt ,"')
        for name in vios_names
    }
    lsmap_raw = {}
    if lsmap_cmds:
        lsmap_raw = ssh_manager.run_hmc_commands_batch(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            commands=lsmap_cmds,
        )

    def slot_after_c(physloc: str) -> str:
        """Extract slot number after '-C' in a physical location code."""
        if not physloc:
            return ""
        for token in physloc.split("-"):
            token = token.strip()
            if token.upper().startswith("C") and token[1:].isdigit():
                return token[1:]
        return ""

    # lsmap -all -fmt , columns (space- or comma-separated — actual order varies
    # by VIOS version; the most common layout is):
    #   vhost, physloc, vtd, backing, backing_type, status, [clntid, clntname, ...]
    lsmap_fields = ["vhost", "physloc", "vtd", "backing", "backing_type", "status",
                    "clntid", "clntname"]

    lsmap_parsed = {}
    for name, res in lsmap_raw.items():
        rows = []
        if res.get("ok"):
            for line in res["output"].splitlines():
                line = line.strip()
                if not line or line.startswith(("vhost,", "No results")):
                    continue
                if line.lower().startswith("error"):
                    continue
                parts = line.split(",")
                row = dict(zip(lsmap_fields, parts))
                # svr_slot = the slot number in the VIOS physloc ("-C<N>")
                # This is the JOIN KEY that matches lshwres slot_num.
                row["svr_slot"] = slot_after_c(row.get("physloc", ""))
                rows.append(row)
        lsmap_parsed[name] = rows

    # ── Assemble raw command text for display above the graph ──
    commands = []
    commands.append({
        "title":   "lshwres — virtual SCSI adapters",
        "command": lshwres_cmd,
        "output":  (lshwres_res.get("output") if lshwres_res.get("ok")
                    else lshwres_res.get("error", "command failed")) or "(no output)",
        "ok":      bool(lshwres_res.get("ok")),
    })
    for name in vios_names:
        res = lsmap_raw.get(name, {})
        commands.append({
            "title":   f"lsmap -all on VIOS {name}",
            "command": lsmap_cmds[name],
            "output":  (res.get("output") if res.get("ok")
                        else res.get("error", "command failed")) or "(no output)",
            "ok":      bool(res.get("ok")),
        })

    return jsonify({
        "ok":            True,
        "system_id":     system_id,
        "vios":          vios_names,
        "scsi_adapters": scsi_rows,
        "lsmap":         lsmap_parsed,
        "commands":      commands,
    })


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/vnet-topology",
           methods=["GET"])
def get_vnet_topology(hmc_id, system_id):
    """Return the Virtual Network (SEA) topology for a managed system.

    Runs, over a single SSH connection to the HMC:
      1. lshwres -r virtualio --rsubtype eth --level lpar -m <system>
         → every virtual ethernet adapter (client LPARs + VIOS trunk adapters).
      2. viosvrcmd -m <system> -p <VIOS> -c "lsdev -type adapter -field name description state"
         | grep -i shared
         → identifies the SEA device name on each VIOS.
      3. viosvrcmd -m <system> -p <VIOS> -c "entstat -all <sea_device>"
         → extracts Real Adapter, Target Virtual Adapter Slot, link speed/status.

    JOIN KEY (Step 1 ↔ Step 3):
      lshwres server-adapter slot_num  ==  entstat "Target Virtual Adapter Slot"
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    m = f'"{system_id}"'
    commands_out = []

    # ── Step 1: lshwres for every virtual ethernet adapter ──────────────────
    # Use comma-separated field names and comma as the output field delimiter.
    # Note: there is no adapter_type field in this output format.
    # Trunk (VIOS) adapters are identified by is_trunk=1.
    # Client LPAR adapters have is_trunk=0 or empty.
    lshwres_cmd = (
        f'lshwres -r virtualio --rsubtype eth --level lpar -m {m} '
        f'-F lpar_name,lpar_id,slot_num,vswitch,port_vlan_id,addl_vlan_ids,is_trunk,trunk_priority'
    )
    lshwres_res = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=lshwres_cmd,
    )

    # Fields returned (comma-delimited output from -F with comma separators):
    #   lpar_name, lpar_id, slot_num, vswitch, port_vlan_id,
    #   addl_vlan_ids, is_trunk, trunk_priority
    eth_fields = ["lpar_name", "lpar_id", "slot_num", "vswitch",
                  "port_vlan_id", "addl_vlan_ids", "is_trunk", "trunk_priority"]
    eth_rows = []
    vios_names = []
    if lshwres_res.get("ok"):
        for line in lshwres_res["output"].splitlines():
            line = line.strip()
            if not line or line.startswith("No results") or line.lower().startswith("error"):
                continue
            # The -F with comma separator outputs fields separated by commas.
            # addl_vlan_ids may itself contain spaces but not commas, so split is safe.
            parts = line.split(",")
            row = dict(zip(eth_fields, parts))
            # Derive adapter_type from is_trunk: "1" = server/VIOS trunk, else client
            row["adapter_type"] = "server" if row.get("is_trunk") == "1" else "client"
            eth_rows.append(row)
            # Trunk adapters (is_trunk=1) are hosted on VIO Servers
            if row.get("is_trunk") == "1" and row.get("lpar_name"):
                if row["lpar_name"] not in vios_names:
                    vios_names.append(row["lpar_name"])

    commands_out.append({
        "title": "lshwres — virtual ethernet adapters (Step 1)",
        "command": lshwres_cmd,
        "output": (lshwres_res.get("output") if lshwres_res.get("ok")
                   else lshwres_res.get("error", "command failed")) or "(no output)",
        "ok": bool(lshwres_res.get("ok")),
    })

    # ── Step 2: lsdev on each VIOS, pipe through grep -i shared ─────────────
    # Command: viosvrcmd -m <ms> -p <VIOS> -c "lsdev" | grep -i shared
    # The first column of each matching line is the SEA device name (e.g. ent5).
    lsdev_cmds = {
        name: f'viosvrcmd -m {m} -p "{name}" -c "lsdev" | grep -i shared'
        for name in vios_names
    }
    lsdev_raw = {}
    if lsdev_cmds:
        lsdev_raw = ssh_manager.run_hmc_commands_batch(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            commands=lsdev_cmds,
        )

    # Parse: each output line is already filtered to "shared" entries.
    # The first whitespace-delimited token is the device name (entX).
    sea_devices = {}   # vios_name → list of sea device names (e.g. ["ent5"])
    for vios, res in lsdev_raw.items():
        devices = []
        if res.get("ok"):
            for line in res["output"].splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if parts:
                    dev = parts[0]
                    # Sanity-check: device name should look like entX
                    if dev.startswith("ent") and dev not in devices:
                        devices.append(dev)
        sea_devices[vios] = devices
        commands_out.append({
            "title": f"lsdev (grep shared) on VIOS {vios} — find SEA (Step 2)",
            "command": lsdev_cmds[vios],
            "output": (res.get("output") if res.get("ok")
                       else res.get("error", "command failed")) or "(no output)",
            "ok": bool(res.get("ok")),
        })

    # ── Step 3: entstat grep commands per SEA device ─────────────────────────
    # Run targeted grep-filtered entstat commands to extract specific fields
    # reliably from the dense entstat -all output.
    #
    # Fields extracted (matching the user-confirmed real output format):
    #   Real Adapter         → backing physical adapter (e.g. ent0)
    #   Physical Port Link Status → physical link state (Up/Down)
    #   Logical Port Link Status  → logical (SEA) link state
    #   Physical Port Speed  → link speed (e.g. "1Gbps Full Duplex")
    #   Virtual Adapter      → VIOS trunk virtual adapter (e.g. ent4 = trunk slot)
    #   Port VLAN ID         → PVID carried by the trunk adapter
    #   VLAN Tag IDs         → tagged VLANs bridged by the SEA

    # Build one batch of grep commands per SEA device per field.
    # Key format: "<vios>::<dev>::<field_key>"
    entstat_grep_cmds = {}
    for vios, devices in sea_devices.items():
        for dev in devices:
            base = f'viosvrcmd -m {m} -p "{vios}" -c "entstat -all {dev}"'
            prefix = f"{vios}::{dev}"
            entstat_grep_cmds[f"{prefix}::real_adapter"]    = f'{base} |grep -i "Real Adapter"'
            entstat_grep_cmds[f"{prefix}::phys_link"]       = f'{base} |grep -i "Physical Port Link Status"'
            entstat_grep_cmds[f"{prefix}::logical_link"]    = f'{base} |grep -i "Logical Port Link Status"'
            entstat_grep_cmds[f"{prefix}::phys_speed"]      = f'{base} |grep -i "Physical Port Speed"'
            entstat_grep_cmds[f"{prefix}::virtual_adapter"] = f'{base} |grep -i "Virtual Adapter"'
            entstat_grep_cmds[f"{prefix}::port_vlan"]       = f'{base} |grep -i "Port VLAN ID"'
            entstat_grep_cmds[f"{prefix}::vlan_tag_ids"]    = f'{base} |grep -i "VLAN Tag IDs"'

    entstat_grep_raw = {}
    if entstat_grep_cmds:
        entstat_grep_raw = ssh_manager.run_hmc_commands_batch(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            commands=entstat_grep_cmds,
        )

    def _first_val(output: str, key_prefix: str) -> str:
        """Return the value after the first ':' on the first matching output line."""
        for line in (output or "").splitlines():
            line = line.strip()
            if ":" in line:
                return line.split(":", 1)[-1].strip()
        return ""

    def _all_vals(output: str) -> list:
        """Return all values after ':' for repeated fields (e.g. Port VLAN ID)."""
        vals = []
        for line in (output or "").splitlines():
            line = line.strip()
            if ":" in line:
                v = line.split(":", 1)[-1].strip()
                if v and v not in vals:
                    vals.append(v)
        return vals

    # Assemble per-device info dicts and build command records for the panel
    entstat_parsed = {}   # vios::dev → info dict

    # Track which (vios, dev) pairs we've processed to avoid duplicate panel entries
    processed_keys = set()

    for field_key, res in entstat_grep_raw.items():
        parts = field_key.split("::")
        if len(parts) < 3:
            continue
        vios, dev, field = parts[0], parts[1], parts[2]
        sea_key = f"{vios}::{dev}"
        if sea_key not in entstat_parsed:
            entstat_parsed[sea_key] = {
                "real_adapter": "", "phys_link": "", "logical_link": "",
                "phys_speed": "", "virtual_adapter": "", "port_vlan": "",
                "vlan_tag_ids": "",
                # legacy aliases used by buildVnetFromLive
                "link_speed": "", "link_status": "", "trunk_slot": "",
                "phys_ports": "", "bridged_vlans": "",
            }
        info = entstat_parsed[sea_key]
        out  = res.get("output", "") if res.get("ok") else ""

        if field == "real_adapter":
            info["real_adapter"] = _first_val(out, "Real Adapter")
        elif field == "phys_link":
            info["phys_link"] = _first_val(out, "Physical Port Link Status")
            info["link_status"] = info["phys_link"]
        elif field == "logical_link":
            info["logical_link"] = _first_val(out, "Logical Port Link Status")
        elif field == "phys_speed":
            info["phys_speed"] = _first_val(out, "Physical Port Speed")
            info["link_speed"] = info["phys_speed"]
        elif field == "virtual_adapter":
            info["virtual_adapter"] = _first_val(out, "Virtual Adapter")
            # Virtual Adapter (e.g. ent4) maps to the VIOS trunk slot.
            # Cross-reference with lshwres trunk rows to find slot_num.
            va = info["virtual_adapter"]
            if va:
                # Try to find the trunk lshwres row for this VIOS whose
                # vswitch adapter name matches the virtual adapter.
                # As a fallback, trunk_slot stays empty — JS uses lshwres slot_num.
                trunk_rows = [r for r in eth_rows
                              if r.get("lpar_name") == vios and r.get("is_trunk") == "1"]
                if trunk_rows:
                    info["trunk_slot"] = trunk_rows[0].get("slot_num", "")
        elif field == "port_vlan":
            vals = _all_vals(out)
            info["port_vlan"] = ", ".join(vals) if vals else ""
        elif field == "vlan_tag_ids":
            info["vlan_tag_ids"] = _first_val(out, "VLAN Tag IDs")
            # Populate bridged_vlans alias from tag IDs (or port VLAN if no tags)
            if info["vlan_tag_ids"] and info["vlan_tag_ids"].lower() != "none":
                info["bridged_vlans"] = info["vlan_tag_ids"]
            elif info.get("port_vlan"):
                info["bridged_vlans"] = info["port_vlan"]

    # Build command output entries for the panel — one block per SEA device
    # showing all 7 grep commands and their output together.
    for vios, devices in sea_devices.items():
        for dev in devices:
            sea_key = f"{vios}::{dev}"
            field_labels = [
                ("real_adapter",    "Real Adapter"),
                ("phys_link",       "Physical Port Link Status"),
                ("logical_link",    "Logical Port Link Status"),
                ("phys_speed",      "Physical Port Speed"),
                ("virtual_adapter", "Virtual Adapter"),
                ("port_vlan",       "Port VLAN ID"),
                ("vlan_tag_ids",    "VLAN Tag IDs"),
            ]
            # Show each grep command + its output as a separate command block
            for field, label in field_labels:
                fkey = f"{sea_key}::{field}"
                cmd_str = entstat_grep_cmds.get(fkey, "")
                res = entstat_grep_raw.get(fkey, {})
                commands_out.append({
                    "title": f"entstat {dev} · {label} (Step 3, VIOS {vios})",
                    "command": cmd_str,
                    "output": (res.get("output") if res.get("ok")
                               else res.get("error", "command failed")) or "(no output)",
                    "ok": bool(res.get("ok")),
                })

    return jsonify({
        "ok": True,
        "system_id": system_id,
        "vios": vios_names,
        "eth_adapters": eth_rows,
        "sea_devices": sea_devices,
        "entstat": entstat_parsed,
        "commands": commands_out,
    })


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/lpars/<path:lpar_id>/profiles",
           methods=["GET"])
def lpar_profiles(hmc_id, system_id, lpar_id):
    """Return the list of profile names defined for a given LPAR via SSH lssyscfg."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    cmd = (f'lssyscfg -m "{system_id}" -r prof '
           f'--filter "lpar_names={lpar_id}" -F name')
    result = ssh_manager.run_hmc_command(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )

    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "error": (result.get("error") or result.get("stderr")
                      or "lssyscfg failed").strip(),
            "command": cmd,
        }), 400

    profiles = []
    for line in result.get("output", "").splitlines():
        line = line.strip()
        if not line or line.startswith("No results") or line.lower().startswith("error"):
            continue
        if line not in profiles:
            profiles.append(line)

    return jsonify({"ok": True, "data": profiles, "command": cmd})


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/lpars/<path:lpar_id>/action",
           methods=["POST"])
def lpar_action(hmc_id, system_id, lpar_id):


    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    action = data.get("action")  # activate | shutdown | restart | softstop
    if not action:
        return jsonify({"error": "action required"}), 400

    # lpar_id from the UI is actually the LPAR name (see get_lpars: id = name).
    lpar_name = lpar_id

    # Build the chsysstate command based on the requested action.
    if action == "activate":
        profile_name = (data.get("profile_name") or "").strip()
        # boot mode: normal | sms | dd (diagnostic) | of (open firmware)
        boot_mode = (data.get("mode") or "norm").strip()
        # Normalise a few friendly aliases to the chsysstate -b values.
        mode_map = {
            "normal": "norm",
            "norm":   "norm",
            "sms":    "sms",
            "dd":     "dd",
            "of":     "of",
            "open_firmware": "of",
        }
        boot_mode = mode_map.get(boot_mode.lower(), boot_mode)

        cmd = (f'chsysstate -m "{system_id}" -o on -n "{lpar_name}" '
               f'-r lpar -b {boot_mode}')
        if profile_name:
            cmd += f' -f "{profile_name}"'
    elif action == "shutdown":
        # Hard power off (immediate)
        cmd = (f'chsysstate -m "{system_id}" -o shutdown -n "{lpar_name}" '
               f'-r lpar --immed')
    elif action == "softstop":
        # Graceful OS shutdown
        cmd = (f'chsysstate -m "{system_id}" -o osshutdown -n "{lpar_name}" '
               f'-r lpar')
    elif action == "restart":
        # Immediate restart
        cmd = (f'chsysstate -m "{system_id}" -o shutdown -n "{lpar_name}" '
               f'-r lpar --immed --restart')
    else:
        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400

    result = ssh_manager.run_hmc_command(
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )

    if result.get("ok"):
        return jsonify({
            "ok":      True,
            "message": result.get("output", "").strip() or "Action submitted.",
            "command": cmd,
        })
    return jsonify({
        "ok":      False,
        "error":   (result.get("error") or result.get("stderr")
                    or "chsysstate failed").strip(),
        "command": cmd,
    }), 400



# ──────────────────────────────────────────────────────────
# SAN switch management API (read-only for now)
# ──────────────────────────────────────────────────────────

@app.route("/api/san/switches", methods=["GET"])
def list_san_switches():
    """Return all saved SAN switches (secrets stripped)."""
    return jsonify(san_store.list())


@app.route("/api/san/switches", methods=["POST"])
def add_san_switch():
    """Save a new SAN switch entry."""
    data = request.get_json(force=True) or {}
    required = ["name", "host"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    entry = san_store.add(data)
    return jsonify(entry), 201


@app.route("/api/san/switches/<switch_id>", methods=["DELETE"])
def delete_san_switch(switch_id):
    san_store.remove(switch_id)
    return jsonify({"ok": True})


@app.route("/api/san/switches/<switch_id>/test", methods=["POST"])
def test_san_switch(switch_id):
    """Test SSH connectivity to a SAN switch."""
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"error": "Switch not found"}), 404
    result = ssh_manager.test_connection(
        host=sw["host"],
        port=int(sw.get("ssh_port", 22)),
        username=sw.get("username", "admin"),
        key_path=sw.get("key_path") or None,
        password=sw.get("password") or None,
    )
    return jsonify(result)


@app.route("/api/san/switches/<switch_id>/zoning", methods=["GET"])
def get_san_zoning(switch_id):
    """Return the read-only fabric view: aliases, zones, zonesets, active cfg."""
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    debug = request.args.get("debug") == "1"
    result = san_manager.fetch_zoning(sw, debug=debug)
    return jsonify(result)


@app.route("/api/san/switches/<switch_id>/ports", methods=["GET"])
def get_san_ports(switch_id):
    """Return the switch port status list (index, state, speed, wwn, type)."""
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    debug = request.args.get("debug") == "1"
    result = san_manager.fetch_ports(sw, debug=debug)
    return jsonify(result)


@app.route("/api/san/switches/<switch_id>/ports/<int:port_index>/login", methods=["GET"])
def get_port_login(switch_id, port_index):
    """Run portloginshow <port> and return connected WWPNs."""
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    result = san_manager.fetch_port_login(sw, port_index)
    return jsonify(result)


@app.route("/api/hmcs/<hmc_id>/managed-systems/<path:system_id>/lpars-list", methods=["GET"])
def lpars_list_for_vfc(hmc_id, system_id):
    """Return a minimal list of LPAR names for a managed system (for VFC map dropdowns)."""
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    cmd = f'lssyscfg -r lpar -m "{system_id}" -F name:lpar_id:lpar_env'
    result = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error", "lssyscfg failed")}), 400
    lpars = []
    for line in result.get("output", "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        lpars.append({
            "name":    parts[0],
            "lpar_id": parts[1] if len(parts) > 1 else "",
            "env":     parts[2] if len(parts) > 2 else "",
        })
    return jsonify({"ok": True, "lpars": lpars})


@app.route("/api/hmcs/<hmc_id>/vfc-map/profile", methods=["POST"])
def create_vfc_map_profile(hmc_id):
    """Add VFC adapter to LPAR profile (for stopped LPARs).

    Body: {managed_system, vios_name, vios_slot, client_lpar, profile_name,
           client_slot, wwpn1 (optional), wwpn2 (optional)}
    Step 1: chhwres on VIOS (server side)
    Step 2: chsyscfg -r prof (update LPAR profile)
    """
    import random
    import time as _time

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    vios_name      = (data.get("vios_name") or "").strip()
    vios_slot      = str(data.get("vios_slot") or "").strip()
    client_lpar    = (data.get("client_lpar") or "").strip()
    profile_name   = (data.get("profile_name") or "").strip()
    client_slot    = str(data.get("client_slot") or "").strip()
    wwpn1          = (data.get("wwpn1") or "").strip().replace(":", "").lower()
    wwpn2          = (data.get("wwpn2") or "").strip().replace(":", "").lower()

    missing = [k for k, v in [
        ("managed_system", managed_system), ("vios_name", vios_name),
        ("vios_slot", vios_slot), ("client_lpar", client_lpar),
        ("profile_name", profile_name), ("client_slot", client_slot)
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    def gen_wwpn():
        import time as _t; _t.sleep(0.001)
        b = [random.randint(0, 255) for _ in range(6)]
        return "1000" + "".join(f"{x:02x}" for x in b)

    if not wwpn1: wwpn1 = gen_wwpn()
    if not wwpn2: wwpn2 = gen_wwpn()
    while wwpn2 == wwpn1: wwpn2 = gen_wwpn()

    # Use plain hex (no colons) in the command line
    wwpn1_fmt = wwpn1.lower()
    wwpn2_fmt = wwpn2.lower()

    # ── Step 1: VIOS server side (chhwres) ────────────────────────
    cmd1 = (
        f'chhwres -r virtualio -m "{managed_system}" -o a '
        f'-p "{vios_name}" --rsubtype fc -s {vios_slot} '
        f'-a "adapter_type=server,remote_lpar_name={client_lpar},remote_slot_num={client_slot}"'
    )
    r1 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd1,
    )
    ok1  = r1.get("ok", False)
    out1 = (r1.get("output") or "").strip()
    err1 = (r1.get("error") or r1.get("stderr") or "").strip()
    if not ok1:
        return jsonify({
            "ok": False, "error": f"Step 1 failed: {err1 or out1 or 'chhwres failed'}",
            "steps": [{"step": 1, "label": "VIOS server side (chhwres)",
                        "command": cmd1, "output": out1, "error": err1, "ok": False}],
        }), 400

    # ── Step 2: Update LPAR profile (chsyscfg -r prof) ────────────
    # Correct HMC chsyscfg syntax:
    #   chsyscfg -r prof -m "SYS" -i "lpar_name=X,name=P,\"virtual_fc_adapters+=\"\"spec\"\"\""
    # adapter spec: slot/client//remote_lpar_name/remote_slot/wwpn1,wwpn2/is_required
    adapter_spec = f'{client_slot}/client//{vios_name}/{vios_slot}/{wwpn1_fmt},{wwpn2_fmt}/0'
    cmd2 = (
        f'chsyscfg -r prof -m "{managed_system}" --force '
        f'-i "lpar_name={client_lpar},name={profile_name},'
        f'\\"virtual_fc_adapters+=\\"\\"{adapter_spec}\\"\\"\\""'
    )
    r2 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd2,
    )
    ok2  = r2.get("ok", False)
    out2 = (r2.get("output") or "").strip()
    err2 = (r2.get("error") or r2.get("stderr") or "").strip()

    steps = [
        {"step": 1, "label": "VIOS server side (chhwres)", "command": cmd1,
         "output": out1 or "(no output — success)", "error": "", "ok": True},
        {"step": 2, "label": f"Update LPAR profile '{profile_name}' (chsyscfg)", "command": cmd2,
         "output": out2 or "(no output — success)" if ok2 else out2,
         "error": err2 if not ok2 else "", "ok": ok2},
    ]
    if not ok2:
        return jsonify({
            "ok": False, "error": f"Step 2 failed: {err2 or out2 or 'chsyscfg failed'}",
            "wwpn1": wwpn1_fmt, "wwpn2": wwpn2_fmt, "steps": steps,
        }), 400

    return jsonify({
        "ok": True, "message": "VFC added to VIOS (chhwres) and LPAR profile (chsyscfg).",
        "wwpn1": wwpn1_fmt, "wwpn2": wwpn2_fmt,
        "generated_wwpns": not bool((data.get("wwpn1") or "").strip()),
        "steps": steps,
    })


@app.route("/api/hmcs/<hmc_id>/vfc-map", methods=["POST"])
def create_vfc_map(hmc_id):
    """Create a full VFC mapping — Step 1 (VIOS server side) then Step 2 (client side).

    Body: {managed_system, vios_name, vios_slot, client_lpar, client_slot,
           wwpn1 (optional), wwpn2 (optional)}
    If wwpn1/wwpn2 are omitted, two random WWPNs are generated.
    """
    import random
    import time as _time

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    vios_name      = (data.get("vios_name") or "").strip()
    vios_slot      = str(data.get("vios_slot") or "").strip()
    client_lpar    = (data.get("client_lpar") or "").strip()
    client_slot    = str(data.get("client_slot") or "").strip()
    wwpn1          = (data.get("wwpn1") or "").strip().replace(":", "").lower()
    wwpn2          = (data.get("wwpn2") or "").strip().replace(":", "").lower()

    missing = [k for k, v in [
        ("managed_system", managed_system), ("vios_name", vios_name),
        ("vios_slot", vios_slot), ("client_lpar", client_lpar), ("client_slot", client_slot)
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    # Generate WWPNs if not provided — use 10:00 prefix + random 6 bytes
    def gen_wwpn():
        seed = int(_time.time() * 1000) ^ random.randint(0, 0xFFFFFFFF)
        rand = random.Random(seed)
        b = [rand.randint(0, 255) for _ in range(6)]
        return "1000" + "".join(f"{x:02x}" for x in b)

    if not wwpn1:
        wwpn1 = gen_wwpn()
    if not wwpn2:
        import time as _t2; _t2.sleep(0.001)
        wwpn2 = gen_wwpn()
    # Ensure the two WWPNs differ
    while wwpn2 == wwpn1:
        wwpn2 = gen_wwpn()

    # Use plain hex (no colons) in the command line
    wwpn1_fmt = wwpn1.lower()
    wwpn2_fmt = wwpn2.lower()

    # ── Step 1: VIOS server side ──────────────────────────────────
    cmd1 = (
        f'chhwres -r virtualio -m "{managed_system}" -o a '
        f'-p "{vios_name}" --rsubtype fc -s {vios_slot} '
        f'-a "adapter_type=server,remote_lpar_name={client_lpar},remote_slot_num={client_slot}"'
    )
    r1 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd1,
    )
    ok1  = r1.get("ok", False)
    out1 = (r1.get("output") or "").strip()
    err1 = (r1.get("error") or r1.get("stderr") or "").strip()

    if not ok1:
        return jsonify({
            "ok": False,
            "error": f"Step 1 failed: {err1 or out1 or 'chhwres failed'}",
            "steps": [{"step": 1, "label": "VIOS server side", "command": cmd1,
                        "output": out1, "error": err1, "ok": False}],
        }), 400

    # ── Step 2: Client LPAR side ──────────────────────────────────
    cmd2 = (
        f'chhwres -r virtualio -m "{managed_system}" -o a '
        f'-p "{client_lpar}" --rsubtype fc -s {client_slot} '
        f'-a "adapter_type=client,remote_lpar_name={vios_name},'
        f'remote_slot_num={vios_slot},wwpns={wwpn1_fmt},{wwpn2_fmt}"'
    )
    r2 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd2,
    )
    ok2  = r2.get("ok", False)
    out2 = (r2.get("output") or "").strip()
    err2 = (r2.get("error") or r2.get("stderr") or "").strip()

    steps = [
        {"step": 1, "label": "VIOS server side",  "command": cmd1,
         "output": out1 or "(no output — success)", "error": "", "ok": True},
        {"step": 2, "label": "Client LPAR side",  "command": cmd2,
         "output": out2 or "(no output — success)" if ok2 else out2,
         "error": err2 if not ok2 else "", "ok": ok2},
    ]

    if not ok2:
        return jsonify({
            "ok": False,
            "error": f"Step 2 failed: {err2 or out2 or 'chhwres failed'}",
            "wwpn1": wwpn1_fmt, "wwpn2": wwpn2_fmt,
            "steps": steps,
        }), 400

    return jsonify({
        "ok": True,
        "message": "VFC mapping created (both sides).",
        "wwpn1": wwpn1_fmt,
        "wwpn2": wwpn2_fmt,
        "generated_wwpns": not bool((data.get("wwpn1") or "").strip()),
        "steps": steps,
    })


@app.route("/api/hmcs/<hmc_id>/vfc-map/vfchost-list", methods=["GET"])
def list_vfchost_for_client(hmc_id):
    """Return the list of vfchostX adapters on a VIOS that are mapped to a specific client LPAR.

    Query params: managed_system, vios_name, client_lpar_name
    Steps:
      1. lssyscfg to get numeric lpar_id for client_lpar_name
      2. viosvrcmd lsmap -all -npiv -cpid <lpar_id> -fmt ,
         → first column is the vfchostX name
    """
    import re as _re

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    managed_system    = (request.args.get("managed_system") or "").strip()
    vios_name         = (request.args.get("vios_name") or "").strip()
    client_lpar_name  = (request.args.get("client_lpar_name") or "").strip()

    if not managed_system or not vios_name or not client_lpar_name:
        return jsonify({"ok": False,
                        "error": "managed_system, vios_name and client_lpar_name are required"}), 400

    # ── Step 1: get numeric lpar_id ───────────────────────────────────────
    cmd_lssyscfg = (
        f'lssyscfg -m "{managed_system}" -r lpar '
        f'--filter "lpar_names={client_lpar_name}" -F lpar_id'
    )
    r1 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd_lssyscfg,
    )
    if not r1.get("ok"):
        return jsonify({
            "ok": False,
            "error": (r1.get("error") or r1.get("stderr") or "lssyscfg failed").strip(),
            "command": cmd_lssyscfg,
        }), 400

    lpar_id = ""
    for line in (r1.get("output") or "").splitlines():
        line = line.strip()
        if line and line.isdigit():
            lpar_id = line
            break
        elif line and not line.lower().startswith("error") and not line.startswith("No results"):
            lpar_id = line
            break

    if not lpar_id:
        return jsonify({
            "ok": False,
            "error": f"Could not determine lpar_id for '{client_lpar_name}'",
            "command": cmd_lssyscfg,
        }), 400

    # ── Step 2: lsmap -all -npiv -cpid <lpar_id> ─────────────────────────
    cmd_lsmap = (
        f'viosvrcmd -m {managed_system} -p "{vios_name}" '
        f'-c "lsmap -all -npiv -cpid {lpar_id} -fmt ,"'
    )
    r2 = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd_lsmap,
    )
    if not r2.get("ok"):
        return jsonify({
            "ok": False,
            "error": (r2.get("error") or r2.get("stderr") or "lsmap failed").strip(),
            "command": cmd_lsmap,
            "lpar_id": lpar_id,
        }), 400

    # Parse: first column of each comma-separated line that looks like vfchostX
    vfchosts = []
    for line in (r2.get("output") or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("error") or line.startswith("No results"):
            continue
        col = line.split(",")[0].strip()
        if _re.match(r'^vfchost\d+$', col, _re.IGNORECASE) and col not in vfchosts:
            vfchosts.append(col)

    return jsonify({
        "ok": True,
        "vfchosts": vfchosts,
        "lpar_id": lpar_id,
        "commands": [cmd_lssyscfg, cmd_lsmap],
    })


@app.route("/api/hmcs/<hmc_id>/vfc-map/fcs-adapters", methods=["GET"])
def list_fcs_adapters(hmc_id):
    """Return a list of physical FC adapters (fcsX) on a given VIOS.

    Query params: managed_system, vios_name
    Runs: viosvrcmd -m <managed_system> -p <vios_name> -c "lsdev"
    Returns lines whose first column matches fcsX.
    """
    import re as _re

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404

    managed_system = (request.args.get("managed_system") or "").strip()
    vios_name      = (request.args.get("vios_name") or "").strip()

    if not managed_system or not vios_name:
        return jsonify({"ok": False, "error": "managed_system and vios_name are required"}), 400

    cmd = f'viosvrcmd -m {managed_system} -p "{vios_name}" -c "lsdev"'
    result = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )
    ok  = result.get("ok", False)
    out = (result.get("output") or "").strip()
    err = (result.get("error") or result.get("stderr") or "").strip()

    if not ok:
        return jsonify({"ok": False, "error": err or "lsdev failed", "command": cmd}), 400

    adapters = []
    for line in out.splitlines():
        if "fcs" not in line.lower():
            continue
        parts = line.split()
        if not parts:
            continue
        name = parts[0].strip()
        if _re.match(r'^fcs\d+$', name, _re.IGNORECASE):
            # Grab the rest of the line as description
            desc = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
            adapters.append({"name": name, "description": desc})

    return jsonify({"ok": True, "adapters": adapters, "command": cmd})


@app.route("/api/hmcs/<hmc_id>/vfc-map/vfcmap", methods=["POST"])
def do_vfcmap(hmc_id):
    """Map a vfchost virtual adapter to a physical FC port on the VIOS.

    Step A: viosvrcmd lsdev | grep fcs  → find physical FC adapters (fcsX)
    Step B: viosvrcmd lsmap -all -npiv  → match clntid to client LPAR id, get vfchostX
    Step C: viosvrcmd vfcmap -vadapter <vfchostX> -fcp <fcsX>

    Body: {managed_system, vios_name, client_lpar_id}
      client_lpar_id: numeric partition id of the client LPAR (used to match lsmap clntid)
    """
    import re as _re

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system   = (data.get("managed_system") or "").strip()
    vios_name        = (data.get("vios_name") or "").strip()
    # vfchost_name may be supplied directly by the user from the dropdown;
    # if omitted, auto-detect via lsmap using client_lpar_id (Step B).
    vfchost_name     = (data.get("vfchost_name") or "").strip()
    client_lpar_id   = str(data.get("client_lpar_id") or "").strip()
    # physical_adapter may be supplied by the user from the dropdown;
    # if omitted, auto-detect via lsdev (Step A).
    physical_adapter = (data.get("physical_adapter") or "").strip()

    # Require either vfchost_name or client_lpar_id for Step B
    missing = [k for k, v in [
        ("managed_system", managed_system),
        ("vios_name", vios_name),
    ] if not v]
    if not vfchost_name and not client_lpar_id:
        missing.append("vfchost_name or client_lpar_id")
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    steps = []

    # ── Step A: lsdev on VIOS to find physical FC adapters ────────────────
    # Skipped if the user already selected a physical adapter from the dropdown.
    if physical_adapter:
        # User chose adapter — record as a skipped/informational step
        steps.append({
            "step": "A", "label": "Physical FC adapter (user selected)",
            "command": f"# user selected: {physical_adapter}",
            "output": f"Using user-selected adapter: {physical_adapter}",
            "note": f"Using physical adapter: {physical_adapter}",
            "error": "", "ok": True,
        })
    else:
        cmd_lsdev = f'viosvrcmd -m {managed_system} -p "{vios_name}" -c "lsdev"'
        r_lsdev = ssh_manager.run_hmc_command(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            command=cmd_lsdev,
        )
        ok_lsdev  = r_lsdev.get("ok", False)
        out_lsdev = (r_lsdev.get("output") or "").strip()
        err_lsdev = (r_lsdev.get("error") or r_lsdev.get("stderr") or "").strip()

        steps.append({
            "step": "A", "label": "List physical FC adapters (lsdev | grep fcs)",
            "command": cmd_lsdev + " | grep fcs",
            "output": out_lsdev, "error": err_lsdev if not ok_lsdev else "", "ok": ok_lsdev,
        })

        if not ok_lsdev:
            return jsonify({
                "ok": False,
                "error": f"Step A failed: {err_lsdev or out_lsdev or 'lsdev failed'}",
                "steps": steps,
            }), 400

        # Parse: first column of lines matching "fcs"
        for line in out_lsdev.splitlines():
            if "fcs" in line.lower():
                col = line.split()[0].strip()
                if _re.match(r'^fcs\d+$', col, _re.IGNORECASE):
                    physical_adapter = col
                    break

        if not physical_adapter:
            steps[-1]["error"] = "No fcsX adapter found in lsdev output"
            return jsonify({
                "ok": False,
                "error": "No physical FC adapter (fcsX) found on VIOS via lsdev.",
                "steps": steps,
            }), 400

        steps[-1]["note"] = f"Using physical adapter: {physical_adapter}"

    # ── Step B: lsmap -all -npiv to find vfchostX matching client LPAR id ─
    # Skipped if the user already selected a vfchost from the dropdown.
    if vfchost_name:
        vhost_name = vfchost_name
        steps.append({
            "step": "B", "label": "vfchost adapter (user selected)",
            "command": f"# user selected: {vfchost_name}",
            "output": f"Using user-selected vfchost: {vfchost_name}",
            "note": f"vfchost: {vfchost_name}",
            "error": "", "ok": True,
        })
    else:
        cmd_lsmap = f'viosvrcmd -m {managed_system} -p "{vios_name}" -c "lsmap -all -npiv -fmt ,"'
        r_lsmap = ssh_manager.run_hmc_command(
            host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
            username=hmc.get("username", "hscroot"),
            key_path=hmc.get("key_path") or None,
            command=cmd_lsmap,
        )
        ok_lsmap  = r_lsmap.get("ok", False)
        out_lsmap = (r_lsmap.get("output") or "").strip()
        err_lsmap = (r_lsmap.get("error") or r_lsmap.get("stderr") or "").strip()

        steps.append({
            "step": "B", "label": "List NPIV mappings (lsmap -all -npiv -fmt ,)",
            "command": cmd_lsmap,
            "output": out_lsmap, "error": err_lsmap if not ok_lsmap else "", "ok": ok_lsmap,
        })

        if not ok_lsmap:
            return jsonify({
                "ok": False,
                "error": f"Step B failed: {err_lsmap or out_lsmap or 'lsmap failed'}",
                "steps": steps,
            }), 400

        # lsmap -fmt , columns: vfchostX, physloc, clntid, clntname, clntos, status, ...
        vhost_name = None
        for line in out_lsmap.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            vfchost_col = parts[0].strip()
            clntid_col  = parts[2].strip()
            if clntid_col == client_lpar_id and _re.match(r'^vfchost\d+$', vfchost_col, _re.IGNORECASE):
                vhost_name = vfchost_col
                break

        if not vhost_name:
            steps[-1]["error"] = (
                f"No vfchostX found in lsmap output matching clntid={client_lpar_id}"
            )
            return jsonify({
                "ok": False,
                "error": (
                    f"Could not find vfchostX for client LPAR id {client_lpar_id} "
                    f"in lsmap -all -npiv output."
                ),
                "steps": steps,
            }), 400

        steps[-1]["note"] = f"Found vhost: {vhost_name}"

    # ── Step C: vfcmap -vadapter <vhost> -fcp <fcs> ──────────────────────
    cmd_vfcmap = (
        f'viosvrcmd -m {managed_system} -p "{vios_name}" '
        f'-c "vfcmap -vadapter {vhost_name} -fcp {physical_adapter}"'
    )
    r_vfcmap = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd_vfcmap,
    )
    ok_vfcmap  = r_vfcmap.get("ok", False)
    out_vfcmap = (r_vfcmap.get("output") or "").strip()
    err_vfcmap = (r_vfcmap.get("error") or r_vfcmap.get("stderr") or "").strip()

    steps.append({
        "step": "C", "label": f"Map vfchost to physical FC port (vfcmap)",
        "command": cmd_vfcmap,
        "output": out_vfcmap or "(no output — success)" if ok_vfcmap else out_vfcmap,
        "error": err_vfcmap if not ok_vfcmap else "", "ok": ok_vfcmap,
    })

    if not ok_vfcmap:
        return jsonify({
            "ok": False,
            "error": f"Step C failed: {err_vfcmap or out_vfcmap or 'vfcmap failed'}",
            "vhost": vhost_name, "fcs": physical_adapter, "steps": steps,
        }), 400

    return jsonify({
        "ok": True,
        "message": f"vfcmap: {vhost_name} mapped to {physical_adapter} on VIOS {vios_name}.",
        "vhost": vhost_name,
        "fcs": physical_adapter,
        "steps": steps,
    })


@app.route("/api/hmcs/<hmc_id>/vfc-map/vfcmap-remove", methods=["POST"])
def do_vfcmap_remove(hmc_id):
    """Remove the vfchost → physical FC port mapping on the VIOS (vfcmap -remove).

    Step A: viosvrcmd lsmap -all -npiv → match clntid to client LPAR id, get vfchostX
    Step B: viosvrcmd vfcmap -vadapter <vfchostX> -remove

    Body: {managed_system, vios_name, client_lpar_id}
    """
    import re as _re

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    vios_name      = (data.get("vios_name") or "").strip()
    client_lpar_id = str(data.get("client_lpar_id") or "").strip()

    missing = [k for k, v in [
        ("managed_system", managed_system),
        ("vios_name", vios_name),
        ("client_lpar_id", client_lpar_id),
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    steps = []

    # ── Step A: lsmap -all -npiv to find vfchostX matching client LPAR id ─
    cmd_lsmap = f'viosvrcmd -m {managed_system} -p "{vios_name}" -c "lsmap -all -npiv -fmt ,"'
    r_lsmap = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd_lsmap,
    )
    ok_lsmap  = r_lsmap.get("ok", False)
    out_lsmap = (r_lsmap.get("output") or "").strip()
    err_lsmap = (r_lsmap.get("error") or r_lsmap.get("stderr") or "").strip()

    steps.append({
        "step": "A", "label": "List NPIV mappings (lsmap -all -npiv -fmt ,)",
        "command": cmd_lsmap,
        "output": out_lsmap, "error": err_lsmap if not ok_lsmap else "", "ok": ok_lsmap,
    })

    if not ok_lsmap:
        return jsonify({
            "ok": False,
            "error": f"Step A failed: {err_lsmap or out_lsmap or 'lsmap failed'}",
            "steps": steps,
        }), 400

    # Parse: find vfchostX whose clntid matches client_lpar_id
    vhost_name = None
    for line in out_lsmap.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        vfchost_col = parts[0].strip()
        clntid_col  = parts[2].strip()
        if clntid_col == client_lpar_id and _re.match(r'^vfchost\d+$', vfchost_col, _re.IGNORECASE):
            vhost_name = vfchost_col
            break

    if not vhost_name:
        steps[-1]["error"] = f"No vfchostX found in lsmap output matching clntid={client_lpar_id}"
        return jsonify({
            "ok": False,
            "error": f"Could not find vfchostX for client LPAR id {client_lpar_id} in lsmap output.",
            "steps": steps,
        }), 400

    steps[-1]["note"] = f"Found vhost: {vhost_name}"

    # ── Step B: vfcmap -vadapter <vhost> -remove ──────────────────────────
    cmd_remove = (
        f'viosvrcmd -m {managed_system} -p "{vios_name}" '
        f'-c "vfcmap -vadapter {vhost_name} -remove"'
    )
    r_remove = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd_remove,
    )
    ok_remove  = r_remove.get("ok", False)
    out_remove = (r_remove.get("output") or "").strip()
    err_remove = (r_remove.get("error") or r_remove.get("stderr") or "").strip()

    steps.append({
        "step": "B", "label": f"Remove vfchost mapping (vfcmap -remove)",
        "command": cmd_remove,
        "output": out_remove or "(no output — success)" if ok_remove else out_remove,
        "error": err_remove if not ok_remove else "", "ok": ok_remove,
    })

    if not ok_remove:
        return jsonify({
            "ok": False,
            "error": f"Step B failed: {err_remove or out_remove or 'vfcmap -remove failed'}",
            "vhost": vhost_name, "steps": steps,
        }), 400

    return jsonify({
        "ok": True,
        "message": f"VFC mapping removed: {vhost_name} on VIOS {vios_name}.",
        "vhost": vhost_name,
        "steps": steps,
    })


@app.route("/api/hmcs/<hmc_id>/vfc-map/delete", methods=["POST"])
def delete_vfc_map(hmc_id):
    """Delete a VFC mapping: chhwres -o r (remove server-side vfchost adapter).
    Body: {managed_system, vios_name, vios_slot}
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    vios_name      = (data.get("vios_name") or "").strip()
    vios_slot      = str(data.get("vios_slot") or "").strip()

    missing = [k for k, v in [
        ("managed_system", managed_system), ("vios_name", vios_name), ("vios_slot", vios_slot)
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    cmd = (
        f'chhwres -r virtualio -m "{managed_system}" -o r '
        f'-p "{vios_name}" --rsubtype fc -s {vios_slot}'
    )
    result = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )
    ok  = result.get("ok", False)
    out = (result.get("output") or "").strip()
    err = (result.get("error") or result.get("stderr") or "").strip()
    if ok:
        return jsonify({"ok": True, "message": out or "VFC mapping removed successfully.", "command": cmd})
    return jsonify({"ok": False, "error": err or out or "chhwres failed", "command": cmd}), 400


@app.route("/api/hmcs/<hmc_id>/vfc-adapter/create", methods=["POST"])
def create_vfc_adapter(hmc_id):
    """Create a virtual FC adapter on an LPAR (client side): chhwres -o a --rsubtype fc.
    Body: {managed_system, lpar_name, slot_num, adapter_type (client|server)}
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    lpar_name      = (data.get("lpar_name") or "").strip()
    slot_num       = str(data.get("slot_num") or "").strip()
    adapter_type   = (data.get("adapter_type") or "client").strip()

    missing = [k for k, v in [
        ("managed_system", managed_system), ("lpar_name", lpar_name), ("slot_num", slot_num)
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    cmd = (
        f'chhwres -r virtualio -m "{managed_system}" -o a '
        f'-p "{lpar_name}" --rsubtype fc -s {slot_num} '
        f'-a "adapter_type={adapter_type}"'
    )
    result = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )
    ok  = result.get("ok", False)
    out = (result.get("output") or "").strip()
    err = (result.get("error") or result.get("stderr") or "").strip()
    if ok:
        return jsonify({"ok": True, "message": out or "Virtual FC adapter created.", "command": cmd})
    return jsonify({"ok": False, "error": err or out or "chhwres failed", "command": cmd}), 400


@app.route("/api/hmcs/<hmc_id>/vfc-adapter/delete", methods=["POST"])
def delete_vfc_adapter(hmc_id):
    """Delete a virtual FC adapter from an LPAR: chhwres -o r --rsubtype fc.
    Body: {managed_system, lpar_name, slot_num}
    """
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"ok": False, "error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    managed_system = (data.get("managed_system") or "").strip()
    lpar_name      = (data.get("lpar_name") or "").strip()
    slot_num       = str(data.get("slot_num") or "").strip()

    missing = [k for k, v in [
        ("managed_system", managed_system), ("lpar_name", lpar_name), ("slot_num", slot_num)
    ] if not v]
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    cmd = (
        f'chhwres -r virtualio -m "{managed_system}" -o r '
        f'-p "{lpar_name}" --rsubtype fc -s {slot_num}'
    )
    result = ssh_manager.run_hmc_command(
        host=hmc["host"], port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        command=cmd,
    )
    ok  = result.get("ok", False)
    out = (result.get("output") or "").strip()
    err = (result.get("error") or result.get("stderr") or "").strip()
    if ok:
        return jsonify({"ok": True, "message": out or "Virtual FC adapter deleted.", "command": cmd})
    return jsonify({"ok": False, "error": err or out or "chhwres failed", "command": cmd}), 400


@app.route("/api/san/switches/<switch_id>/alias", methods=["POST"])
def create_san_alias(switch_id):
    """Create a new alias on the switch.
    Body: {name: str, members: [wwpn, ...]}
    """
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    members = [m.strip() for m in (data.get("members") or []) if m.strip()]
    if not name:
        return jsonify({"ok": False, "error": "Alias name is required"}), 400
    if not members:
        return jsonify({"ok": False, "error": "At least one WWPN member is required"}), 400
    result = san_manager.create_alias(sw, name, members)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/san/switches/<switch_id>/zone", methods=["POST"])
def create_san_zone(switch_id):
    """Create a new zone on the switch.
    Body: {name: str, members: [alias_or_wwpn, ...]}
    """
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    members = [m.strip() for m in (data.get("members") or []) if m.strip()]
    if not name:
        return jsonify({"ok": False, "error": "Zone name is required"}), 400
    if not members:
        return jsonify({"ok": False, "error": "At least one member is required"}), 400
    result = san_manager.create_zone(sw, name, members)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/san/switches/<switch_id>/zoneset/add-zones", methods=["POST"])
def add_zones_to_zoneset(switch_id):
    """Add zones to an existing or new zoneset.
    Body: {zoneset: str, zones: [zone_name, ...]}
    """
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    data = request.get_json(force=True) or {}
    zoneset = (data.get("zoneset") or "").strip()
    zones = [z.strip() for z in (data.get("zones") or []) if z.strip()]
    if not zoneset:
        return jsonify({"ok": False, "error": "Zoneset name is required"}), 400
    if not zones:
        return jsonify({"ok": False, "error": "At least one zone is required"}), 400
    result = san_manager.add_zone_to_zoneset(sw, zoneset, zones)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/san/switches/<switch_id>/alias/<path:alias_name>", methods=["DELETE"])
def delete_san_alias(switch_id, alias_name):
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    result = san_manager.delete_alias(sw, alias_name)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.route("/api/san/switches/<switch_id>/zone/<path:zone_name>", methods=["DELETE"])
def delete_san_zone(switch_id, zone_name):
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    result = san_manager.delete_zone(sw, zone_name)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.route("/api/san/switches/<switch_id>/zoneset/activate", methods=["POST"])
def activate_san_zoneset(switch_id):
    """Activate (enable) a zoneset / cfg.
    Body: {zoneset: str}
    """
    sw = san_store.get(switch_id)
    if not sw:
        return jsonify({"ok": False, "error": "Switch not found"}), 404
    data = request.get_json(force=True) or {}
    zoneset = (data.get("zoneset") or "").strip()
    if not zoneset:
        return jsonify({"ok": False, "error": "Zoneset name is required"}), 400
    result = san_manager.activate_zoneset(sw, zoneset)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status



# ──────────────────────────────────────────────────────────
# WebSocket terminal (SSH)
# ──────────────────────────────────────────────────────────

@socketio.on("ssh_connect")
def handle_ssh_connect(data):

    hmc_id = data.get("hmc_id")
    hmc = hmc_store.get(hmc_id)
    if not hmc:
        emit("ssh_error", {"msg": "HMC not found"})
        return
    result = ssh_manager.open_shell(
        sid=request.sid,
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=data.get("username", hmc.get("username", "hscroot")),
        key_path=data.get("key_path") or hmc.get("key_path"),
        password=data.get("password"),
        emit_fn=lambda msg: socketio.emit("ssh_output", {"data": msg},
                                          to=request.sid),
    )
    if not result.get("ok"):
        emit("ssh_error", {"msg": result.get("error", "Connection failed")})


@socketio.on("ssh_input")
def handle_ssh_input(data):
    ssh_manager.send_input(request.sid, data.get("data", ""))


@socketio.on("ssh_disconnect_req")
def handle_ssh_disconnect(data=None):
    ssh_manager.close_shell(request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    ssh_manager.close_shell(request.sid)


# ──────────────────────────────────────────────────────────
# WebSocket LPAR vterm console  (namespace /console)
# ──────────────────────────────────────────────────────────
#
# Flow:
#   1. Browser connects to /console namespace.
#   2. Browser emits "vterm_open" with {hmc_id, system_id, lpar_name}.
#   3. Backend calls SSHManager.open_vterm() which SSHs to the HMC and
#      runs:  mkvterm -m "<system_id>" -p "<lpar_name>"
#   4. A background thread in SSHManager reads the channel and emits
#      "vterm_output" events back to the browser.
#   5. Browser emits "vterm_input" with {data: "<keystrokes>"}.
#   6. On modal close / browser disconnect, "vterm_close" is emitted and
#      the backend tears down the SSH channel (releasing the HMC vterm lock).
# ──────────────────────────────────────────────────────────

@socketio.on("vterm_open", namespace="/console")
def handle_vterm_open(data):
    """Connect to the HMC and start the mkvterm session for the given LPAR."""
    hmc_id     = data.get("hmc_id")
    system_id  = data.get("system_id", "")
    lpar_name  = data.get("lpar_name", "")

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        emit("vterm_error", {"msg": "HMC not found"}, namespace="/console")
        return
    if not system_id or not lpar_name:
        emit("vterm_error", {"msg": "system_id and lpar_name are required"},
             namespace="/console")
        return

    sid = request.sid

    def _emit_output(text):
        """Called from the SSHManager read-thread; forward terminal bytes to browser."""
        socketio.emit("vterm_output", {"data": text}, to=sid, namespace="/console")

    result = ssh_manager.open_vterm(
        sid=sid,
        host=hmc["host"],
        port=int(hmc.get("ssh_port", 22)),
        username=hmc.get("username", "hscroot"),
        key_path=hmc.get("key_path") or None,
        managed_system=system_id,
        lpar_name=lpar_name,
        emit_fn=_emit_output,
    )

    if result.get("ok"):
        logger.info("vterm opened for LPAR %s on %s (sid=%s)", lpar_name, system_id, sid)
        emit("vterm_ready", {"lpar_name": lpar_name, "system_id": system_id},
             namespace="/console")
    else:
        err_msg = result.get("error", "Failed to open vterm")
        logger.warning("vterm open failed for %s: %s", lpar_name, err_msg)
        # Detect the common "vterm already open" error from the HMC.
        if "already" in err_msg.lower() or "locked" in err_msg.lower() or "in use" in err_msg.lower():
            err_msg = (
                f"The vterm for LPAR '{lpar_name}' is already open (or locked) on the HMC. "
                "Close the existing vterm session on the HMC first:\n"
                f"  rmvterm -m \"{system_id}\" -p \"{lpar_name}\"\n"
                "Then try again."
            )
        emit("vterm_error", {"msg": err_msg}, namespace="/console")


@socketio.on("vterm_input", namespace="/console")
def handle_vterm_input(data):
    """Forward keystrokes from the browser terminal to the HMC SSH channel."""
    ssh_manager.send_input(request.sid, data.get("data", ""))


@socketio.on("vterm_resize", namespace="/console")
def handle_vterm_resize(data):
    """Propagate terminal resize (cols x rows) to the PTY on the HMC."""
    try:
        cols = int(data.get("cols", 80))
        rows = int(data.get("rows", 24))
    except (TypeError, ValueError):
        return
    ssh_manager.resize_vterm(request.sid, cols, rows)


@socketio.on("vterm_close", namespace="/console")
def handle_vterm_close(data=None):
    """Explicit close from the browser (modal close button)."""
    ssh_manager.close_shell(request.sid)
    logger.info("vterm closed by client (sid=%s)", request.sid)


@socketio.on("disconnect", namespace="/console")
def handle_vterm_disconnect():
    """Browser disconnected (tab closed, network drop, etc.) — clean up SSH."""
    ssh_manager.close_shell(request.sid)
    logger.info("vterm disconnect cleanup (sid=%s)", request.sid)


# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)
