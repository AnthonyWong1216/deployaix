# PowerPilot — HMC & Power Server Management Web App

A Flask web application for managing IBM HMC and Power servers from macOS.

## Features

- **Connect to HMC** — save multiple HMC profiles (SSH + REST API)
- **SSH Key Management** — list, generate, and push public keys to HMC with one click
- **SSH Terminal** — browser-based interactive terminal to any HMC via WebSocket
- **HMC REST API** — authenticate and query managed systems and LPARs
- **LPAR Management** — activate, shutdown, soft-stop, and restart LPARs
- **Managed Systems** — list Power servers managed by the HMC
- Profiles stored in `~/.powerpilot/hmcs.json`

## Quick Start (macOS)

```bash
# 1 — create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2 — install dependencies
pip install -r requirements.txt

# 3 — run the app
python app.py
```

Open **http://localhost:5001** in your browser.

## Project Layout

```
powerpilot/
├── app.py                  Flask application & routes
├── requirements.txt
├── modules/
│   ├── hmc_api.py          HMC REST API client (HTTPS port 443)
│   ├── hmc_store.py        Persistent HMC profile store (~/.powerpilot)
│   └── ssh_manager.py      Paramiko SSH: key gen, push, test, terminal
├── templates/
│   ├── base.html           Layout with left-nav sidebar
│   ├── index.html          Dashboard
│   ├── connect.html        HMC connection + SSH key management
│   ├── lpars.html          LPAR list & power actions
│   ├── managed_systems.html
│   ├── virtual_networks.html
│   ├── storage.html
│   └── jobs.html
└── static/
    ├── css/main.css
    └── js/app.js
```

## HMC Connection Methods

### Method 1 — SSH Key (recommended)
1. Go to **Connect to HMC → SSH Key Pairs → Generate Key** to create a new key pair.
2. Click **Push Key** on your HMC entry, enter the HMC password once.  
   The app runs `mkauthkeys --add` (HMC-native) or falls back to `authorized_keys`.
3. Click **Test SSH** — you should see the HMC version without a password prompt.

### Method 2 — Password
Select *Password* as the auth method when adding the HMC.

### HMC REST API
Click **API Login** and enter the HMC credentials.  
The session token is stored in memory for the duration of the server process.

## Notes

- The HMC uses a self-signed TLS certificate; HTTPS verification is disabled by default.
- SSH port: **22** (standard). REST API port: **12443** (default HMC).
- Tested against HMC V9 and V10. The XML namespace patterns may vary on older versions.
