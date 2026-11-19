# BananaVision Remote Access Guide

BananaVision is an Edge Computing system: the backend, AI models, cameras, sensors and database all run on the Mini PC inside the scanning area. By default the dashboard is only reachable from devices on the same local WiFi.

This guide explains how to grant **remote access** so administrators and managers can use the dashboard from home, another office, or mobile data. It covers:

- [How the app behaves when accessed remotely](#how-the-app-behaves-when-accessed-remotely)
- [Option 1: Tailscale private network](#option-1-tailscale-private-network)
- [Option 2 (this deployment): Public HTTPS link](#option-2-this-deployment-public-https-link-no-installs-for-users)
- [Troubleshooting](#troubleshooting)

| Option | Users install anything? | Exposed to public internet? | App changes required? |
|---|---|---|---|
| Tailscale VPN | Yes, once per device | No — private tailnet only | No |
| Public HTTPS link (Tailscale Funnel / Cloudflare Tunnel) | No | Yes | Bundled: HTTPS build + Caddy proxy |

---

## How the app behaves when accessed remotely

Understanding this avoids most setup surprises:

- The frontend is served on port `5173`, the FastAPI backend on port `8000` (API + WebSockets). Both bind `0.0.0.0` in [start.bat](../../start.bat) and [start.sh](../../start.sh).
- On a plain-HTTP page the frontend derives the API address from the browser hostname: `http://<hostname>:8000` (`frontend/src/lib/api.ts`). WebSockets use the same host on port `8000` (`frontend/src/hooks/useWebSocket.ts`).
- On an HTTPS page the frontend calls the **same origin** for both HTTP and WebSocket traffic. A reverse proxy must forward `/api`, `/captures` and `/health` to port `8000`. This is what the bundled [Caddyfile](../../deploy/Caddyfile) does.
- **Consequence:** Tailscale private-network access still works as before: opening `http://bananavision-pc:5173` sends API and WebSocket calls to `http://bananavision-pc:8000` through the tailnet. No rebuild is needed.
- **Consequence:** a public `https://` link needs the proxy path below. Pointing a funnel directly at port `5173` cannot work: the page would call the HTTPS origin for `/api`, and the funnel does not expose port `8000`.
- CORS: the built-in default is `http://localhost:5173` and `http://127.0.0.1:5173` (`backend/app/config.py`). Plain-HTTP LAN and Tailscale pages call the station hostname, so the shipped example keeps `["*"]`. The public setup is same-origin and needs no CORS entry. Never expose port `8000` to the internet.
- WebSockets send a heartbeat every 25 seconds so proxies do not close idle connections.

---

## Option 1: Tailscale private network

Tailscale creates a private WireGuard network (a "tailnet") between the Mini PC and each authorized device. Only devices signed in to your tailnet can see the Mini PC, and no router ports are opened. All traffic is encrypted in transit.

Once set up, the user simply opens `http://bananavision-pc:5173` from anywhere.

### One-time setup on the Mini PC (Windows)

1. **Install Tailscale.** Download from <https://tailscale.com/download/windows>, install, and sign in (Google, Microsoft, GitHub or email). This creates your tailnet. Tailscale runs as a Windows service and reconnects automatically at boot, before anyone logs in.
2. **Enable MagicDNS.** In the [Tailscale admin console](https://login.tailscale.com/admin) go to **DNS** and enable **MagicDNS**. This lets clients use the machine name instead of a numeric IP.
3. **Rename the machine.** Admin console -> **Machines** -> the Mini PC -> edit the name to `bananavision-pc` (any name works; this guide assumes this one).
4. **Disable key expiry for the station.** Admin console -> **Machines** -> the Mini PC -> **Disable key expiry**. Otherwise the node drops off the tailnet after the default expiry period and needs manual re-authentication.
5. **Allow the app ports through Windows Firewall for tailnet traffic only.** In an Administrator PowerShell:
   ```powershell
   New-NetFirewallRule -DisplayName "BananaVision (Tailscale)" `
     -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5173,8000 `
     -RemoteAddress 100.64.0.0/10,fd7a:115c:a1e0::/48
   ```
   These are Tailscale's address ranges, so the rule does not expose the ports to the local LAN or the internet.
6. **Keep the Mini PC awake and online.** In an Administrator PowerShell:
   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   powercfg /hibernate off
   ```
   Also check the power button / lid settings if applicable.
7. **Auto-start BananaVision.** Tailscale starting is not enough — the app itself must be running. Configure auto-login and the startup shortcut from [kiosk-autostart-guide.md](kiosk-autostart-guide.md).

**Power settings prerequisites.** The `powercfg` commands above only control OS sleep and need three conditions:

- **Administrator elevation.** Run them in an Administrator PowerShell; as a normal user they fail with a permissions error. Changes apply immediately and persist across reboots.
- **BIOS/UEFI AC recovery.** After a power outage many mini PCs stay off until the power button is pressed. Set *Restore on AC Power Loss*, *State After G3* or *After Power Failure* to **Power On** in BIOS so the station returns unattended.
- **Windows Update restarts.** Set active hours so updates do not reboot the station while managers depend on it. On Windows Pro, enable *No auto-restart with logged on users for scheduled automatic updates installations* (Computer Configuration -> Administrative Templates -> Windows Components -> Windows Update).

Confirm in **Settings** -> **System** -> **Power & battery** that Sleep shows **Never** while plugged in, or run `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE`.

Verify on the Mini PC:

```powershell
tailscale status
tailscale ip -4
```

### One-time setup per user device

Tailscale access and BananaVision access are **two separate logins** — users need both.

1. **Join the tailnet.** Either:
   - invite the user's account from the admin console (**Users** -> **Invite external users**; they sign in and accept), or
   - for people outside your organization, share only this machine: admin console -> **Machines** -> **Share** and send them the link. They accept with their own Tailscale account.
2. **Install Tailscale** on their laptop or phone (`https://tailscale.com/download` or the app store) and sign in.
3. **Leave Tailscale connected** — on phones this is a VPN toggle, and battery-saver modes may pause it.
4. **Open the app:** `http://bananavision-pc:5173`
5. **Log in with their BananaVision account** (created by an admin inside the app). Tailscale membership does not create an application account or role.
6. Bookmark the URL.

Daily use after that: turn on the device, confirm Tailscale is connected, open the bookmark. No further setup.

### Optional: restrict what tailnet users can reach

By default, every tailnet member can reach every machine and port in the tailnet. If managers are invited to the tailnet, restrict them to the dashboard ports. In the admin console -> **Access controls**, use this form (adjust names/emails):

```json
{
  "groups": {
    "group:bananavision-users": ["manager1@example.com", "manager2@example.com"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:bananavision-users"],
      "dst": ["bananavision-pc:5173,8000"]
    }
  ]
}
```

Note: ACLs do not restrict nodes shared via **Share**. Choose the tailnet + ACL route when port-level restriction matters.

### Verification checklist

- On the Mini PC: `tailscale status` shows the station as connected.
- From a client on mobile data: `http://bananavision-pc:8000/docs` loads the Swagger UI.
- From the same client: `http://bananavision-pc:5173` loads the dashboard.
- Login works, live camera previews render, and the dashboard connection indicator shows WebSocket activity.
- Reboot the Mini PC while unattended and confirm both Tailscale and the app come back up.

---

## Option 2 (this deployment): Public HTTPS link (no installs for users)

> **Windows Mini PC runbook:** [windows-mini-pc-deployment.md](windows-mini-pc-deployment.md) is the linear, copy-paste checklist version of this section, written for the station computer. This section explains the design and the alternatives.

Publishes the dashboard at a normal website such as `https://bananavision-pc.<tailnet>.ts.net`. Users click the link and sign in with their BananaVision account. They do not install Tailscale, join the tailnet, or accept an invite.

Traffic path:

```
Internet -> Tailscale Funnel (TLS) -> Caddy 127.0.0.1:8080
         -> frontend/dist and /api, /captures, /health -> uvicorn 127.0.0.1:8000
```

The funnel exposes **one** HTTPS port. [Caddy](../../deploy/Caddyfile) provides the single origin, serves the built frontend, forwards the API and WebSocket upgrade, and adds security headers. It does not listen on the LAN.

### Prerequisites

- Complete Option 1 steps 1–7 on the Mini PC (Tailscale, MagicDNS, machine name, no key expiry, firewall, power, auto-start). Skip the per-user device setup. The station must stay awake and online.
- In the [Tailscale admin console](https://login.tailscale.com/admin) enable **HTTPS certificates** (DNS page) and allow **Funnel** for the tailnet.
- Put `caddy.exe` on the Mini PC (single binary from <https://caddyserver.com/download>).

### 1. Production backend settings

Merge [deploy/backend.env.production.example](../../deploy/backend.env.production.example) into `backend/.env`. It lists every key that differs between the development and public deployment configs; the rest keep their current values. Never commit `backend/.env` or real secrets.

```dotenv
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=<48 random bytes, base64>
JWT_SECRET_KEY=<different 48 random bytes, base64>
APP_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
TRUSTED_PROXIES=["127.0.0.1","::1"]
```

- Generate each secret once in PowerShell, and run this twice to get two different values:
  ```powershell
  $bytes = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  [Convert]::ToBase64String($bytes)
  ```
- With `APP_ENV=production`, startup refuses placeholder or shorter-than-32-byte secrets, and Swagger, ReDoc and `/openapi.json` are disabled.
- `TRUSTED_PROXIES` lets the backend record the visitor IP from Caddy instead of `127.0.0.1`.
- Add `http://<station-host>:5173` to `APP_CORS_ORIGINS` only if operators must keep using the plain-HTTP LAN page while `APP_ENV=production`. The public HTTPS page is same-origin and needs no entry.
- On an empty database, set `BOOTSTRAP_ADMIN_PASSWORD` (12–72 bytes) and remove it after the administrator replaces that temporary password at first login.

### 2. Build the frontend for the public origin

Copy [frontend/.env.production.example](../../frontend/.env.production.example) to `frontend/.env.production` and set the final public origin:

```dotenv
VITE_PUBLIC_BASE_URL=https://bananavision-pc.<tailnet>.ts.net
```

Do not set `VITE_API_URL` or `VITE_WS_URL`; the HTTPS build calls the same origin automatically.

```powershell
cd frontend
npm run build
```

The launchers reuse an existing `frontend/dist`. Rebuild after any URL change, otherwise the old build keeps the old QR origin.

### 3. Run Caddy

From the repository root:

```powershell
caddy run --config deploy/Caddyfile
```

For unattended operation, add a Windows scheduled task that runs the same command at startup with the repository root as its working directory. Confirm the local hop works before publishing:

```powershell
curl http://127.0.0.1:8080/health
```

### 4. Publish with Tailscale Funnel

```powershell
tailscale funnel --bg --https=443 http://127.0.0.1:8080
tailscale funnel status
```

The status output shows the public URL. Funnel accepts only ports `443`, `8443` and `10000`; `443` gives the clean link. `--bg` keeps the mapping across restarts. To stop publishing: `tailscale funnel reset`.

### 5. Verify

- `https://<public-url>/health` returns JSON.
- The dashboard loads, login succeeds, and the connection indicator shows WebSocket activity.
- A live camera preview appears after signing in. Previews now require a session; the kiosk gets one after operator PIN entry.
- A QR label printed at the station opens `https://<public-url>/track/<scan-id>` from mobile data.
- `https://<public-url>/docs`, `/redoc` and `/openapi.json` return 404.
- Reboot the Mini PC and confirm Tailscale, Caddy and BananaVision return.

### Security notes

- The login page is reachable by anyone on the internet. Expect automated scanning. A username locks for 5 minutes after 5 failed attempts (`backend/app/core/rate_limiter.py`); this also means an attacker can temporarily lock the admin account. There is no MFA in the app.
- For an outer identity gate without client installs, Cloudflare Tunnel with **Cloudflare Access** (email one-time PIN) is the alternative. It needs a Cloudflare account and a domain.
- Camera previews, scan evidence and the operator list remain application-protected; the public tracking page shows scan data but not camera photos.
- Caddy adds HSTS, CSP, frame protection and content-type protection. It does not log request URIs by default, which keeps WebSocket tokens out of access logs.
- Tailscale's proxy has reported WebSocket drops and query-parameter issues. The client now sends a 25-second heartbeat and reconnects with backoff. If live updates remain unreliable, switch the tunnel to Cloudflare Tunnel.
- Router port forwarding is not an acceptable substitute: it exposes the Mini PC directly, often does not work behind CGNAT, and offers no per-user access control.

---

## macOS tailnet dry run (optional)

Use the scripts on a Mac that is already in the tailnet to exercise the HTTPS path without Funnel, Windows or station hardware.

Prerequisites: Tailscale connected, backend venv prepared, frontend `node_modules` installed, and HTTPS certificates/Serve enabled for the tailnet. The scripts use `backend/.env` and the local model weights as-is, so confirm that file points at a development database, not the station database.

```bash
deploy/start-mac-tailnet.sh              # builds frontend, starts backend + Caddy, enables Serve
deploy/start-mac-tailnet.sh --skip-build # reuse the current frontend/dist
deploy/stop-mac-tailnet.sh               # stops both processes and removes Serve
```

- The start script downloads Caddy into `~/Library/Caches/bananavision` when missing, checks GitHub's published asset digest, and validates `deploy/Caddyfile`.
- Backend and Caddy bind loopback (`127.0.0.1:8000` and `127.0.0.1:8080`). Only Tailscale Serve is reachable by tailnet devices. No macOS firewall rule is needed; the Windows firewall rule in Option 1 applies only to the Mini PC and direct ports `5173`/`8000`.
- The build sets `VITE_PUBLIC_BASE_URL` to the printed `https://<host>.<tailnet>.ts.net` origin, so QR labels resolve during the dry run.
- The script prints the URL. Logs and PID files live in `~/.local/state/bananavision-tailnet`.
- The start script reuses its own existing Serve proxy when the processes were stopped without removing it. If the machine was renamed, the old Serve entry no longer matches the node's DNS name; the script replaces that stale entry with one for the current name. It refuses to overwrite any other Serve configuration.
- The stop script removes the Serve mapping and kills only processes whose stored command matches. It is safe to run twice.
- Renaming the machine changes the URL. Rerun the start script without `--skip-build` so `VITE_PUBLIC_BASE_URL` and the printed QR URLs use the new name.
- This is a verification aid, not the public deployment. It does not enable Funnel.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `bananavision-pc` does not resolve | MagicDNS off, wrong tailnet, or Tailscale disconnected on the client | Enable MagicDNS; confirm both devices show the same tailnet in the admin console; reconnect Tailscale |
| Page loads, but data never loads / spinner forever | Backend not running, or port 8000 blocked | Start BananaVision; test `http://bananavision-pc:8000/health`; re-check the firewall rule |
| Works on the station LAN but not remotely | Mini PC asleep, app not started, or station key expired | Apply the power settings and auto-start steps above; disable key expiry and re-authenticate |
| A phone loses access after a while | Battery saver paused the Tailscale VPN | Keep Tailscale connected / allow background activity |
| Browser warns "Not secure" | Expected: the app is served over plain HTTP inside the encrypted Tailscale tunnel | No action; never use a public plain-HTTP URL |
| Public link returns 502 or an empty page | Caddy is stopped, or uvicorn is not listening on `127.0.0.1:8000` | Start both services; check `curl -I http://127.0.0.1:8080/health` on the Mini PC |
| `tailscale funnel` says Funnel is not enabled | Funnel disabled in the tailnet policy or HTTPS certificates are off | Enable Funnel and HTTPS certificates in the Tailscale admin console, then rerun the command |
| Login says "Network error" on the public link | Caddy is not forwarding `/api`, or the frontend build predates the same-origin change | Confirm `/api/v1/...` reaches the backend; rebuild `frontend/dist` and redeploy it |
| Live view reconnects every few seconds | Tailscale Funnel drops idle WebSockets | Confirm the 25s heartbeat is in the build; if drops persist, use the Cloudflare Tunnel fallback above |
| Login fails with correct credentials | BananaVision account issue, or username temporarily locked after 5 failed attempts | Check the in-app Users page; wait 5 minutes for the lockout to expire |

---

## Related documentation

- [Windows Mini PC Deployment](windows-mini-pc-deployment.md) — linear public HTTPS runbook for the station.
- [Kiosk Auto-Start Guide](kiosk-autostart-guide.md) — auto-login and app startup on the Mini PC.
- [Caddyfile](../../deploy/Caddyfile) — reverse proxy for the public HTTPS deployment.
- [Installation Guide](INSTALLATION_GUIDE.md) — station hardware and software setup.
- [User Guide](USER_GUIDE.md) — application roles and dashboard usage.
