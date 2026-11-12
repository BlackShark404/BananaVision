# BananaVision Remote Access Guide

BananaVision is an Edge Computing system: the backend, AI models, cameras, sensors and database all run on the Mini PC inside the scanning area. By default the dashboard is only reachable from devices on the same local WiFi.

This guide explains how to grant **remote access** so administrators and managers can use the dashboard from home, another office, or mobile data. It covers:

- [How the app behaves when accessed remotely](#how-the-app-behaves-when-accessed-remotely)
- [Option 1 (recommended): Tailscale private network](#option-1-recommended-tailscale-private-network)
- [Option 2: Public HTTPS link](#option-2-public-https-link-no-installs-for-users)
- [Troubleshooting](#troubleshooting)

| Option | Users install anything? | Exposed to public internet? | App changes required? |
|---|---|---|---|
| Tailscale VPN | Yes, once per device | No — private tailnet only | No |
| Public HTTPS link (Tailscale Funnel / Cloudflare Tunnel) | No | Yes | Yes |

---

## How the app behaves when accessed remotely

Understanding this avoids most setup surprises:

- The frontend is served on port `5173`, the FastAPI backend on port `8000` (API + WebSockets). Both bind `0.0.0.0` in [start.bat](../start.bat) and [start.sh](../start.sh).
- The frontend derives the API address from the hostname in the browser address bar: `http://<hostname>:8000` (`frontend/src/lib/api.ts`). WebSockets use the same host on port `8000` (`frontend/src/hooks/useWebSocket.ts`).
- **Consequence:** if a user opens `http://bananavision-pc:5173` through Tailscale, API and WebSocket calls automatically go to `http://bananavision-pc:8000` over the same Tailscale tunnel. No rebuild or reconfiguration is needed.
- **Consequence:** an `https://` public link does **not** work as-is. The page would try to call `http://<host>:8000`, which is blocked by the browser as mixed content, and port `8000` is not exposed by a funnel anyway.
- CORS: the current station `backend/.env` sets `APP_CORS_ORIGINS=["*"]`, so any origin is allowed. If that is ever tightened to a list, it must include the origin used remotely, e.g. `http://bananavision-pc:5173`.

---

## Option 1 (recommended): Tailscale private network

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

## Option 2: Public HTTPS link (no installs for users)

This publishes the dashboard as a normal website, e.g. `https://bananavision.<tailnet>.ts.net` using Tailscale Funnel, or a custom domain using Cloudflare Tunnel. Users only click a link — no account, no install, no invite.

**This does not work with the current build.** Because the frontend always calls `http://<hostname>:8000` for the API and WebSockets:

- the funnel page (HTTPS) cannot call an HTTP API (mixed content is blocked by the browser), and
- port `8000` is not exposed by a funnel of port `5173` anyway.

Making it work requires all of the following:

1. Build the frontend with explicit URLs, e.g. `VITE_API_URL` and `VITE_WS_URL` pointing at an HTTPS/WSS endpoint (support exists in `frontend/src/lib/api.ts` and `frontend/src/hooks/useWebSocket.ts`).
2. Expose the backend over HTTPS too, either with a second funnel (`tailscale funnel --bg --https=8443 8000`) or a single local reverse proxy (e.g. Caddy) that serves the frontend and forwards `/api` plus WebSocket upgrades to port `8000`, with the funnel pointed at the proxy.
3. Set `APP_CORS_ORIGINS` in `backend/.env` to include the public origin if the current `["*"]` is ever tightened.

Security considerations before choosing this option:

- The login page becomes reachable by anyone on the internet. Protection depends entirely on BananaVision authentication: change the default `admin/admin` credentials first, and note the app already locks a username after 5 failed login attempts for 5 minutes (`backend/app/core/rate_limiter.py`).
- Expect automated scanning and login attempts in the logs.
- Cloudflare Tunnel with **Cloudflare Access** (email one-time PIN) can gate visitors without client installs, at the cost of a Cloudflare account and a domain.
- Router port forwarding is not an acceptable substitute: it exposes the Mini PC directly, often does not work behind CGNAT, and offers no per-user access control.

Recommendation: use Option 1 for a small team of managers. Choose Option 2 only if "users install nothing" is a hard requirement.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `bananavision-pc` does not resolve | MagicDNS off, wrong tailnet, or Tailscale disconnected on the client | Enable MagicDNS; confirm both devices show the same tailnet in the admin console; reconnect Tailscale |
| Page loads, but data never loads / spinner forever | Backend not running, or port 8000 blocked | Start BananaVision; test `http://bananavision-pc:8000/docs`; re-check the firewall rule |
| Works on the station LAN but not remotely | Mini PC asleep, app not started, or station key expired | Apply the power settings and auto-start steps above; disable key expiry and re-authenticate |
| A phone loses access after a while | Battery saver paused the Tailscale VPN | Keep Tailscale connected / allow background activity |
| Browser warns "Not secure" | Expected: the app is served over plain HTTP inside the encrypted Tailscale tunnel | No action; never use a public plain-HTTP URL |
| Funnel/public link loads but login fails | Expected limitation described in Option 2 | Use Option 1, or implement the Option 2 changes |
| Login fails with correct credentials | BananaVision account issue, or username temporarily locked after 5 failed attempts | Check the in-app Users page; wait 5 minutes for the lockout to expire |

---

## Related documentation

- [Kiosk Auto-Start Guide](kiosk-autostart-guide.md) — auto-login and app startup on the Mini PC.
- [Installation Guide](INSTALLATION_GUIDE.md) — station hardware and software setup.
- [User Guide](USER_GUIDE.md) — application roles and dashboard usage.
