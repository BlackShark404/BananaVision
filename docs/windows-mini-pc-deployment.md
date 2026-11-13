# Windows Mini PC Deployment — Public HTTPS

This is the linear runbook for publishing BananaVision from the Windows Mini PC at the scanning station. The result:

```
Internet -> Tailscale Funnel (HTTPS) -> Caddy 127.0.0.1:8080
         -> frontend/dist + /api, /captures, /health -> uvicorn 127.0.0.1:8000
```

Users open a normal HTTPS link, install nothing, and sign in with their BananaVision account. The kiosk, cameras, sensor, printer and local database stay on the station.

For background, alternatives and the macOS dry run, see [remote-access.md](remote-access.md). This page only covers the Windows station.

> **Status:** the application, Caddy configuration and HTTPS path were exercised on macOS over Tailscale Serve. The Windows commands below use the same configuration, but this runbook has not yet been run on the actual Mini PC.

## At a glance

1. Prepare Tailscale, name the machine and enable HTTPS + Funnel. (Section 1)
2. Save the final `https://<machine>.<tailnet>.ts.net` URL. (Section 2)
3. Set production values in `backend\.env` and restart the app. (Section 3)
4. Build the frontend with that URL. (Section 4)
5. Run Caddy on `127.0.0.1:8080` and register its scheduled task. (Sections 5–6)
6. Publish with `tailscale funnel` and verify from mobile data. (Sections 7–8)

Sections 9–11 cover operations, rollback and troubleshooting.

---

## 0. Before you start

Confirm all of these on the Mini PC:

- [ ] The station works locally: `start.bat` opens the kiosk, a test scan succeeds, all four cameras show previews, the sensor reports temperature and humidity, and a label prints.
- [ ] PostgreSQL is installed, running, and the station database exists.
- [ ] The repository is at `C:\BananaVision` (this runbook assumes that path; adjust every command if yours differs).
- [ ] `backend\venv` exists and the backend starts.
- [ ] `frontend\node_modules` exists.
- [ ] At least one BananaVision administrator account exists. You can sign in on the station.
- [ ] You can sign in to the [Tailscale admin console](https://login.tailscale.com/admin) for the account that owns the station.
- [ ] You have about 30 minutes and can reboot the station once.

Do not start yet if the station itself is not working. Fix local scanning first; public access only adds a proxy in front of it.

---

## 1. Prepare Tailscale on the station (one-time)

1. Install Tailscale for Windows from <https://tailscale.com/download/windows> and sign in. This creates or joins your tailnet.
2. In the admin console:
   - **DNS** -> enable **MagicDNS**.
   - **DNS** -> enable **HTTPS Certificates**.
   - **Machines** -> rename the Mini PC to `bananavision-pc`.
   - **Machines** -> the Mini PC -> **Disable key expiry**.
   - Allow **Funnel** for the tailnet. If you cannot find the switch, run the Funnel command in step 7 once; Tailscale prints the exact enable link.
3. In an Administrator PowerShell, keep the station awake:

   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   powercfg /hibernate off
   ```

4. A BIOS/UEFI setting named **Restore on AC Power Loss**, **State After G3** or **After Power Failure** should be set to **Power On**, so the station returns after an outage.

**Firewall:** the public path needs **no inbound firewall rule**. Funnel traffic reaches Caddy through the local Tailscale service on loopback. Do not open port `8080` on the firewall or the router.

The existing Windows firewall rule for ports `5173` and `8000` is only for Option 1 (direct tailnet or LAN access). Keep it if operators still use the plain-HTTP page; the public HTTPS link does not need it. Never forward port `8000` from the router.

The kiosk itself must still start automatically. Follow [kiosk-autostart-guide.md](kiosk-autostart-guide.md) for auto-login and the startup shortcut.

Verify:

```powershell
tailscale status
tailscale ip -4
```

---

## 2. Confirm the final public URL

Finalize the machine name **before** building the frontend. Renaming the machine later changes the URL and requires a rebuild.

In PowerShell on the station:

```powershell
$dns = (tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.')
$publicUrl = "https://$dns"
$publicUrl
```

Example output:

```text
https://bananavision-pc.tailabc123.ts.net
```

Write this value down. It is used in steps 4 and 8.

If the command fails, copy the **DNS name** from the admin console: **Machines** -> `bananavision-pc`. Add `https://` in front.

---

## 3. Configure the backend for production

The template lists every key that differs from the development configuration:

[deploy/backend.env.production.example](../deploy/backend.env.production.example)

1. Back up the current file first:

   ```powershell
   Copy-Item C:\BananaVision\backend\.env C:\BananaVision\backend\.env.backup
   ```

2. Open `C:\BananaVision\backend\.env` in a text editor and merge the template values. Minimum required changes:

   ```dotenv
   APP_ENV=production
   APP_DEBUG=false
   APP_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
   TRUSTED_PROXIES=["127.0.0.1","::1"]
   APP_SECRET_KEY=<generated below>
   JWT_SECRET_KEY=<generated separately below>
   ```

   Keep the station's real `DATABASE_URL`, `CAMERA_DEVICE_IDS`, `SENSOR_SERIAL_PORT`, `CAPTURE_DIR`, model paths and printer settings.

3. Generate two different secrets. Run this command **twice** in PowerShell and use one output for each key:

   ```powershell
   $bytes = New-Object byte[] 48
   [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
   [Convert]::ToBase64String($bytes)
   ```

4. If the database is **empty**, also set a unique temporary administrator password (12–72 UTF-8 bytes):

   ```dotenv
   BOOTSTRAP_ADMIN_USERNAME=admin
   BOOTSTRAP_ADMIN_PASSWORD=<temporary password>
   ```

   If the station database already has an administrator, do not set these. Remove `BOOTSTRAP_ADMIN_PASSWORD` after the first administrator login replaces the temporary password.

5. Save the file. Never commit `backend\.env`; it contains real secrets.

6. Restart BananaVision: close the backend window opened by `start.bat`, then run `start.bat` again.

7. Confirm the backend is healthy:

   ```powershell
   curl.exe -s http://127.0.0.1:8000/health
   ```

   Expected: JSON with `"status":"healthy"`, models loaded and the database working. If the backend window closes immediately, it rejected a production setting; read the error in that window. The usual cause is a missing or placeholder secret.

With `APP_ENV=production`, Swagger, ReDoc and `/openapi.json` are disabled automatically.

---

## 4. Build the frontend for the public URL

1. Create `C:\BananaVision\frontend\.env.production`. If a template exists, copy it:

   ```powershell
   Copy-Item C:\BananaVision\frontend\.env.production.example C:\BananaVision\frontend\.env.production
   ```

2. Set the URL from step 2:

   ```dotenv
   VITE_PUBLIC_BASE_URL=https://bananavision-pc.tailabc123.ts.net
   ```

   Do **not** set `VITE_API_URL` or `VITE_WS_URL`. The HTTPS build calls its own origin automatically.

3. Build:

   ```powershell
   cd C:\BananaVision\frontend
   npm run build
   ```

The build writes `C:\BananaVision\frontend\dist`. Caddy serves that folder.

Rebuild whenever the public URL changes. Otherwise printed QR labels keep the old origin.

---

## 5. Run Caddy locally

1. Download the Windows **amd64** build of Caddy from <https://caddyserver.com/download>. Put the single `caddy.exe` at `C:\BananaVision\caddy.exe`.

2. Open PowerShell at the repository root and verify the binary:

   ```powershell
   cd C:\BananaVision
   .\caddy.exe version
   ```

3. Validate the configuration:

   ```powershell
   .\caddy.exe validate --config C:\BananaVision\deploy\Caddyfile --adapter caddyfile
   ```

   Expected: `Valid configuration`.

4. Start Caddy in the foreground:

   ```powershell
   .\caddy.exe run --config C:\BananaVision\deploy\Caddyfile --adapter caddyfile
   ```

   Keep this window open while testing.

5. In a second PowerShell window, test the local hop:

   ```powershell
   curl.exe -s http://127.0.0.1:8080/health
   curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/docs
   ```

   Expected: health JSON, then `404` for `/docs`.

The [Caddyfile](../deploy/Caddyfile) binds only to `127.0.0.1:8080`, serves `frontend/dist`, proxies `/api`, `/captures` and `/health`, blocks API docs and adds security headers. Caddy must run from `C:\BananaVision` so the relative `frontend/dist` path resolves.

If Caddy does not start, check that the backend is running and that nothing else owns port `8080`:

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

---

## 6. Start Caddy automatically

In an **Administrator** PowerShell:

```powershell
$action = New-ScheduledTaskAction `
  -Execute "C:\BananaVision\caddy.exe" `
  -Argument 'run --config "C:\BananaVision\deploy\Caddyfile" --adapter caddyfile' `
  -WorkingDirectory "C:\BananaVision"

$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Without this, Task Scheduler stops a long-running task after 3 days by default.
$settings = New-ScheduledTaskSettingsSet `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew `
  -StartWhenAvailable

Register-ScheduledTask `
  -TaskName "BananaVision Caddy" `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Description "BananaVision HTTPS reverse proxy" `
  -Force
```

Stop the foreground Caddy window from step 5 first (Ctrl+C), then start the task:

```powershell
Start-ScheduledTask -TaskName "BananaVision Caddy"
Get-ScheduledTask -TaskName "BananaVision Caddy" | Get-ScheduledTaskInfo
curl.exe -s http://127.0.0.1:8080/health
```

Caddy now starts at boot. The backend still starts when `start.bat` runs at login. After a reboot the public link may return `502` for a short time until the backend is up; this is normal.

The scheduled task has no console window. For troubleshooting, stop the task and run the foreground command from step 5.

---

## 7. Publish with Tailscale Funnel

On the station:

```powershell
tailscale funnel --bg --https=443 http://127.0.0.1:8080
tailscale funnel status
```

The status output shows the public URL. It should match step 2.

- If a Serve mapping already exists on port `443`, remove it first: `tailscale serve --https=443 off`.
- If Tailscale says Funnel is not enabled, open the link it prints or enable Funnel in the admin console, then rerun the command.
- `--bg` keeps the mapping across reboots. Run this command once; it is not needed on every start.
- To stop publishing: `tailscale funnel reset`.

Funnel accepts only ports `443`, `8443` and `10000`. Use `443`.

---

## 8. Verify the public link

From a phone on **mobile data**, not the station Wi-Fi and not the tailnet:

1. Open `https://<public-url>/health`. It returns JSON.
2. Open `https://<public-url>/`. The dashboard loads.
3. Sign in with a BananaVision account. The connection indicator shows WebSocket activity.
4. Open a camera view. The preview appears only after signing in.
5. Print or open a QR label. `https://<public-url>/track/<scan-id>` loads from mobile data.
6. `https://<public-url>/docs`, `/redoc` and `/openapi.json` return `404`.
7. On the station, the kiosk and a local scan still work normally.

If steps 1–6 work, the deployment is usable.

---

## 9. Day-2 operations

| Task | Command |
|---|---|
| Start or restart the app | Close its windows, then run `start.bat` (or reboot) |
| Restart Caddy | `Restart-ScheduledTask -TaskName "BananaVision Caddy"` |
| Check the public mapping | `tailscale funnel status` |
| Stop publishing | `tailscale funnel reset` |
| Stop the proxy | `Stop-ScheduledTask -TaskName "BananaVision Caddy"` |

After a code update:

1. Restart the backend through `start.bat` if backend files changed.
2. Rebuild the frontend if frontend files or the public URL changed:

   ```powershell
   cd C:\BananaVision\frontend
   npm run build
   ```

   Caddy serves the new `dist` immediately; no Caddy restart is required.

Rotating `APP_SECRET_KEY` or `JWT_SECRET_KEY` signs every user out. That is expected.

---

## 10. Rollback

To return the station to local-only access:

```powershell
tailscale funnel reset
Stop-ScheduledTask -TaskName "BananaVision Caddy"
Unregister-ScheduledTask -TaskName "BananaVision Caddy" -Confirm:$false
```

Then:

1. Restore the backend configuration:

   ```powershell
   Copy-Item C:\BananaVision\backend\.env.backup C:\BananaVision\backend\.env
   ```

2. Restart BananaVision with `start.bat`.
3. Remove `frontend\.env.production` and rebuild if you want the old QR behavior:

   ```powershell
   Remove-Item C:\BananaVision\frontend\.env.production
   cd C:\BananaVision\frontend
   npm run build
   ```

The kiosk, LAN access and station data are not affected by the public-link rollback.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Caddy exits immediately | Port `8080` already in use, or wrong config path | `Get-NetTCPConnection -LocalPort 8080 -State Listen`; run Caddy from `C:\BananaVision` |
| `caddy validate` fails | Wrong binary, wrong path, or config edited | Use the Windows amd64 binary; run the exact command in step 5 |
| Public URL returns `502` | Backend not running, or not on `127.0.0.1:8000` | Start `start.bat`; test `curl.exe http://127.0.0.1:8000/health` |
| Public URL shows a blank page | `frontend\dist` missing or stale | Run `npm run build`; confirm `frontend\dist\index.html` exists |
| Login fails with "Network error" | Build is old, or Caddy is not forwarding `/api` | Rebuild the frontend; test `/api/v1/...` through port `8080` |
| QR label opens the old address | Frontend was built before the URL change | Fix `frontend\.env.production`, rebuild |
| `tailscale funnel` says Funnel is not enabled | Tailnet policy or HTTPS certificates | Enable both in the admin console, then rerun the command |
| Public link stops after reboot | Caddy task not running, or backend never started | Check `Get-ScheduledTaskInfo`; confirm kiosk auto-login and `start.bat` |
| Camera preview is blank remotely | Camera offline, or not signed in | Sign in; check the camera on the station kiosk; previews require a session |
| Live view reconnects every few seconds | Funnel drops idle WebSockets | The client sends a heartbeat every 25 seconds; if drops persist, use the Cloudflare Tunnel fallback in [remote-access.md](remote-access.md) |
| Backend exits on startup after enabling production | Missing, placeholder or short secrets | Read the backend window error; regenerate both secrets and restart |

---

## Security checklist

- [ ] `APP_ENV=production` and `APP_DEBUG=false`.
- [ ] `APP_SECRET_KEY` and `JWT_SECRET_KEY` are different, random, at least 32 bytes.
- [ ] `backend\.env` is not committed and is not inside a synced public folder.
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` is removed after the first administrator login.
- [ ] Ports `8000` and `5173` are not forwarded by the router.
- [ ] Port `8080` is not opened in Windows Firewall; Caddy binds loopback only.
- [ ] Tailscale key expiry for the station is disabled, and the Tailscale account has a strong password and MFA.
- [ ] `/docs`, `/redoc` and `/openapi.json` return `404` through the public URL.
- [ ] Camera previews and scan evidence require a BananaVision login.
- [ ] The station database and `captures` folder are backed up before the first public deployment.

The login page is reachable by anyone on the internet. Expect automated scanning. Accounts lock for 5 minutes after 5 failed attempts; the app has no MFA. Consider Cloudflare Tunnel with Cloudflare Access if you need an outer email-based gate.

---

## Related documentation

- [remote-access.md](remote-access.md) — both remote-access options, security notes and troubleshooting.
- [kiosk-autostart-guide.md](kiosk-autostart-guide.md) — auto-login and app startup.
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) — station hardware and software installation.
- [backend/README.md](../backend/README.md) — migrations, database upgrades and backend operations.
- [deploy/Caddyfile](../deploy/Caddyfile) — proxy configuration.
