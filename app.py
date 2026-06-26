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
        # lssyscfg -r lpar returns one CSV line per LPAR
        cmd = (f'lssyscfg -r lpar -m "{system_id}" '
               f'-F name:lpar_id:state:lpar_env')
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
                    "name":     parts[0] if len(parts) > 0 else "—",
                    "lpar_id":  parts[1] if len(parts) > 1 else "—",
                    "id":       parts[0] if len(parts) > 0 else "—",
                    "state":    parts[2] if len(parts) > 2 else "—",
                    "type":     parts[3] if len(parts) > 3 else "—",
                    "profile":  "—",
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
                f'run_procs:pend_procs:uncap_weight'
            ),
            "mem": (
                f'lshwres -r mem --level lpar -m {m} --filter {f} '
                f'-F lpar_name:curr_mem:run_mem:pend_mem:min_mem:max_mem'
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
            "phyeth": (
                f'lshwres -r hea --level port -m {m} --filter {f} '
                f'-F lpar_name:adapter_id:port_group:lhea_port_id:mac_addr'
            ),
            "sriov": (
                f'lshwres -r sriov --rsubtype logport --level lpar -m {m} --filter {f} '
                f'-F lpar_name:adapter_id:logical_port_id:mac_addr:capacity'
            ),
            "phyfc": (
                f'lshwres -r hca --level port -m {m} --filter {f} '
                f'-F lpar_name:adapter_id:port_index:wwpn'
            ),
        }
    )
    cpu_r    = raw["cpu"]
    mem_r    = raw["mem"]
    veth_r   = raw["veth"]
    vscsi_r  = raw["vscsi"]
    vfc_r    = raw["vfc"]
    phyeth_r = raw["phyeth"]
    sriov_r  = raw["sriov"]
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

    cpu_fields    = ["lpar_name","curr_procs","curr_proc_units","sharing_mode",
                     "min_procs","max_procs","min_proc_units","max_proc_units",
                     "run_procs","pend_procs","uncap_weight"]
    mem_fields    = ["lpar_name","curr_mem","run_mem","pend_mem","min_mem","max_mem"]
    veth_fields   = ["lpar_name","slot","pvid","addl_vlans","ieee","mac"]
    vscsi_fields  = ["lpar_name","slot","remote_lpar","remote_slot"]
    vfc_fields    = ["lpar_name","slot","wwpns","remote_lpar","remote_slot"]
    phyeth_fields = ["lpar_name","adapter_id","port_group","port_id","mac"]
    sriov_fields  = ["lpar_name","adapter_id","logical_port_id","mac","capacity"]
    phyfc_fields  = ["lpar_name","adapter_id","port_index","wwpn"]

    # Collect per-resource errors (None = success/no-data, string = error msg)
    raw_results = [
        ("cpu",    cpu_r),  ("mem",  mem_r),
        ("veth",   veth_r), ("vscsi",vscsi_r), ("vfc",  vfc_r),
        ("phyeth", phyeth_r),("sriov",sriov_r), ("phyfc",phyfc_r),
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
        "phyeth":parse_lines(phyeth_r, phyeth_fields),
        "sriov": parse_lines(sriov_r,  sriov_fields),
        "phyfc": parse_lines(phyfc_r,  phyfc_fields),
        "errors": errors,
    }
    if debug:
        result["raw"] = {k: v for k, v in raw.items()}
    return jsonify(result)


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
