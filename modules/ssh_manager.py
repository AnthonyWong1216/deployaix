"""
SSH Manager — handles key listing, generation, key-trust push, test connections,
and interactive shell sessions (used by the WebSocket terminal).
"""

import os
import glob
import threading
import subprocess
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path
import paramiko

logger = logging.getLogger(__name__)

SSH_DIR = Path.home() / ".ssh"


class SSHManager:
    def __init__(self):
        self._shells: dict[str, dict] = {}   # sid -> {channel, client}

    # ──────────────────────────────────────────────────────
    # Key utilities
    # ──────────────────────────────────────────────────────

    def list_local_keys(self) -> List[Dict]:
        """Return private keys found in ~/.ssh/."""
        keys = []
        if not SSH_DIR.exists():
            return keys
        pub_files = {p.stem for p in SSH_DIR.glob("*.pub")}
        for p in SSH_DIR.iterdir():
            if p.suffix == ".pub" or p.name.startswith("known_hosts") \
                    or p.name.startswith("authorized") \
                    or p.name in ("config", "environment"):
                continue
            if p.stem in pub_files and p.is_file():
                pub_path = SSH_DIR / (p.name + ".pub")
                pub_content = ""
                try:
                    pub_content = pub_path.read_text().strip()
                except Exception:
                    pass
                keys.append({
                    "name": p.name,
                    "private_key_path": str(p),
                    "public_key_path": str(pub_path),
                    "public_key": pub_content,
                })
        return keys

    def generate_key(self, key_type="ed25519", key_name="id_deployaix",
                     passphrase="", comment="deployaix") -> dict:
        SSH_DIR.mkdir(mode=0o700, exist_ok=True)
        key_path = SSH_DIR / key_name
        if key_path.exists():
            return {"error": f"Key '{key_name}' already exists at {key_path}"}
        cmd = [
            "ssh-keygen", "-t", key_type, "-f", str(key_path),
            "-C", comment, "-N", passphrase,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"error": result.stderr.strip()}
            pub = (key_path.with_suffix("") if key_type != "ed25519"
                   else Path(str(key_path) + ".pub"))
            pub_path = SSH_DIR / (key_name + ".pub")
            return {
                "ok": True,
                "private_key_path": str(key_path),
                "public_key_path": str(pub_path),
                "public_key": pub_path.read_text().strip() if pub_path.exists() else "",
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ──────────────────────────────────────────────────────
    # SSH helpers
    # ──────────────────────────────────────────────────────

    def _connect(self, host, port, username, key_path, password):
        """Return a connected SSHClient."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kw = dict(hostname=host, port=port, username=username,
                  timeout=10, banner_timeout=10)
        if key_path:
            kw["key_filename"] = os.path.expanduser(key_path)
        elif password:
            kw["password"] = password
            kw["look_for_keys"] = False
        else:
            kw["look_for_keys"] = True
        client.connect(**kw)
        return client

    def run_hmc_command(self, host, port=22, username="hscroot",
                        key_path=None, password=None,
                        command="") -> dict:
        """Run a single command over its own SSH connection."""
        try:
            client = self._connect(host, port, username, key_path, password)
            _, stdout, stderr = client.exec_command(command, timeout=15)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
            client.close()
            if exit_status != 0 and not out:
                return {"ok": False, "error": err or f"exit {exit_status}"}
            return {"ok": True, "output": out, "stderr": err}
        except paramiko.AuthenticationException:
            return {"ok": False, "error": "SSH authentication failed"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def run_hmc_commands_batch(self, host, port=22, username="hscroot",
                               key_path=None, password=None,
                               commands: dict = None) -> dict:
        """Run multiple commands over a SINGLE SSH connection.

        ``commands`` is an ordered dict of  {key: cmd_string}.
        Returns {key: {"ok": bool, "output": str, "error": str}}.
        Opens one connection, executes each command sequentially,
        closes the connection once at the end.
        """
        results = {k: {"ok": False, "output": "", "error": "not run"}
                   for k in (commands or {})}
        if not commands:
            return results
        try:
            client = self._connect(host, port, username, key_path, password)
        except paramiko.AuthenticationException:
            err = "SSH authentication failed"
            return {k: {"ok": False, "output": "", "error": err} for k in commands}
        except Exception as exc:
            err = str(exc)
            return {k: {"ok": False, "output": "", "error": err} for k in commands}

        for key, cmd in commands.items():
            try:
                _, stdout, stderr = client.exec_command(cmd, timeout=20)
                out = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                exit_status = stdout.channel.recv_exit_status()
                if exit_status != 0 and not out:
                    results[key] = {"ok": False, "output": "", "error": err or f"exit {exit_status}"}
                else:
                    results[key] = {"ok": True, "output": out, "stderr": err}
            except Exception as exc:
                results[key] = {"ok": False, "output": "", "error": str(exc)}

        try:
            client.close()
        except Exception:
            pass
        return results

    # ──────────────────────────────────────────────────────
    # Connection testing
    # ──────────────────────────────────────────────────────

    def test_connection(self, host, port=22, username="hscroot",
                        key_path=None, password=None) -> dict:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = dict(hostname=host, port=port, username=username,
                                  timeout=10, banner_timeout=10)
            if key_path:
                connect_kwargs["key_filename"] = os.path.expanduser(key_path)
            elif password:
                connect_kwargs["password"] = password
                connect_kwargs["look_for_keys"] = False
            else:
                connect_kwargs["look_for_keys"] = True
            client.connect(**connect_kwargs)
            _, stdout, _ = client.exec_command("lshmc -V 2>/dev/null || uname -a")
            version = stdout.read().decode().strip()
            client.close()
            return {"ok": True, "version": version}
        except paramiko.AuthenticationException:
            return {"ok": False, "error": "Authentication failed"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ──────────────────────────────────────────────────────
    # Key trust (ssh-copy-id equivalent)
    # ──────────────────────────────────────────────────────

    def push_public_key(self, host, port=22, username="hscroot",
                        password="", public_key_path="~/.ssh/id_rsa.pub") -> dict:
        pub_path = Path(os.path.expanduser(public_key_path))
        if not pub_path.exists():
            return {"error": f"Public key not found: {pub_path}"}
        pub_key = pub_path.read_text().strip()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=host, port=port, username=username,
                           password=password, look_for_keys=False, timeout=15)
            # HMC restricted shell only supports mkauthkeys.
            # Syntax: mkauthkeys --add [-u user-ID] "string"
            # The key string MUST be the last argument.
            cmd = f'mkauthkeys --add -u {username} "{pub_key}"'
            _, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            exit_status = stdout.channel.recv_exit_status()
            client.close()
            if exit_status != 0:
                return {"ok": False, "error": err or f"mkauthkeys exited {exit_status}"}
            return {"ok": True, "message": "Public key installed on HMC via mkauthkeys"}
        except paramiko.AuthenticationException:
            return {"ok": False, "error": "Authentication failed — check password"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ──────────────────────────────────────────────────────
    # Interactive shell
    # ──────────────────────────────────────────────────────

    def open_shell(self, sid, host, port=22, username="hscroot",
                   key_path=None, password=None, emit_fn=None) -> dict:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = dict(hostname=host, port=port, username=username,
                                  timeout=15)
            if key_path:
                connect_kwargs["key_filename"] = os.path.expanduser(key_path)
            elif password:
                connect_kwargs["password"] = password
                connect_kwargs["look_for_keys"] = False
            else:
                connect_kwargs["look_for_keys"] = True
            client.connect(**connect_kwargs)
            channel = client.invoke_shell(term="xterm", width=220, height=50)
            self._shells[sid] = {"client": client, "channel": channel}
            # Read loop in background thread
            t = threading.Thread(target=self._read_loop,
                                 args=(sid, channel, emit_fn), daemon=True)
            t.start()
            return {"ok": True}
        except paramiko.AuthenticationException:
            return {"ok": False, "error": "Authentication failed"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _read_loop(self, sid, channel, emit_fn):
        try:
            while not channel.closed:
                if channel.recv_ready():
                    data = channel.recv(4096).decode("utf-8", errors="replace")
                    if emit_fn:
                        emit_fn(data)
                elif channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.02)
        except Exception as exc:
            logger.debug("SSH read loop ended for %s: %s", sid, exc)
        finally:
            if emit_fn:
                emit_fn("\r\n[Connection closed]\r\n")

    def send_input(self, sid, data: str):
        shell = self._shells.get(sid)
        if shell and not shell["channel"].closed:
            shell["channel"].send(data)

    def close_shell(self, sid):
        shell = self._shells.pop(sid, None)
        if shell:
            try:
                shell["channel"].close()
                shell["client"].close()
            except Exception:
                pass
