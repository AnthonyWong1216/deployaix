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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "deployaix-dev-secret-change-in-prod")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

ssh_manager = SSHManager()
hmc_store = HMCStore()

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
            )
        }
    )
    cpu_r    = raw["cpu"]
    mem_r    = raw["mem"]
    veth_r   = raw["veth"]
    vscsi_r  = raw["vscsi"]
    vfc_r    = raw["vfc"]
    phyio_r  = raw["phyio"]

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

    # Collect per-resource errors (None = success/no-data, string = error msg)
    raw_results = [
        ("cpu",    cpu_r),  ("mem",  mem_r),
        ("veth",   veth_r), ("vscsi",vscsi_r), ("vfc",  vfc_r),
        ("phyio", phyio_r)
    ]
    errors = {k: v.get("error") for k, v in raw_results if not v.get("ok")}

    # Always include raw output in debug mode so the UI can show it
    debug = request.args.get("debug") == "1"

    result = {
        "ok":    True,
        "cpu":   parse_lines(cpu_r,    cpu_fields),
        "mem":   parse_lines(mem_r,    mem_fields),
        "veth":  parse_lines(veth_r,   veth_fields),
        "vscsi": parse_lines(vscsi_r,  vscsi_fields),
        "vfc":   parse_lines(vfc_r,    vfc_fields),
        "phyio": parse_lines(phyio_r, phyio_fields),
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


@app.route("/api/hmcs/<hmc_id>/managed-systems/<system_id>/lpars/<lpar_id>/action",
           methods=["POST"])
def lpar_action(hmc_id, system_id, lpar_id):

    hmc = hmc_store.get(hmc_id)
    if not hmc:
        return jsonify({"error": "HMC not found"}), 404
    data = request.get_json(force=True) or {}
    action = data.get("action")  # activate | shutdown | restart | softstop
    if not action:
        return jsonify({"error": "action required"}), 400
    client = HMCApiClient(
        host=hmc["host"],
        port=int(hmc.get("api_port", 443)),
        session_id=hmc.get("session_id"),
    )
    return jsonify(client.lpar_action(system_id, lpar_id, action))


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

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)
