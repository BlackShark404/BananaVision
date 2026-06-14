# BananaVision Remote Access Guide

Since BananaVision is designed as an Edge Computing system (all software and hardware run locally on a Mini PC in the scanning area), the application is only accessible to users connected to the same local WiFi network by default.

If you ever need to grant **Remote Access** (allowing administrators or managers to view the dashboard from home, another office, or on mobile data), follow this guide. We highly recommend using **Tailscale** for its security, simplicity, and ease of use for non-technical users.

---

## Strategy 1: Tailscale Funnel (Best for Non-Technical Users)
**Use Case:** You want managers to click a simple link (e.g., `https://bananavision.tail1a2b.ts.net`) on their phone or laptop without forcing them to install any VPN software or create accounts.

Tailscale Funnel securely exposes your local Mini PC's port `5173` to the public internet using a secure HTTPS tunnel provided by Tailscale.

### Setup Instructions (Only required on the Mini PC)
1. **Download and Install:** Install [Tailscale for Windows](https://tailscale.com/download/windows) on the Mini PC.
2. **Login:** Log in with an admin account (Google, Microsoft, or GitHub) to create your Tailscale network (Tailnet).
3. **Enable Funnel:** 
   - Open the Tailscale Admin Console in your browser.
   - Go to the **Access Controls** tab and ensure the `funnel` attribute is permitted for your device.
4. **Start the Funnel via Command Line:**
   - Open Command Prompt or PowerShell on the Mini PC.
   - Run the following command to expose the BananaVision frontend:
     ```bash
     tailscale funnel 5173
     ```
5. **Get Your URL:** Tailscale will output a public URL (e.g., `https://bananavision.your-tailnet-name.ts.net`).
6. **Share the Link:** Bookmark this link on the managers' devices or generate a QR code for it. They can now access the system from anywhere in the world!

---

## Strategy 2: Traditional Tailscale VPN (Most Secure)
**Use Case:** You want maximum security and do not want the dashboard accessible on the public internet at all. All users must be authenticated members of your IT organization.

### Setup Instructions
1. **Install on Mini PC:** Install Tailscale on the Edge Node Mini PC and log in.
2. **Install on Client Devices:** Install the Tailscale app on every manager's laptop or smartphone.
3. **Connect:** Users log into the Tailscale app using the same organization domain.
4. **Access the System:** Instead of typing `localhost` or an IP address, users simply type the Mini PC's machine name into their browser.
   - Example: `http://minipc:5173`
   - *Note: This requires Tailscale "MagicDNS" to be enabled in your admin console.*

---

## Strategy 3: Cloudflare Tunnels (Best for Custom Domains)
**Use Case:** You want the dashboard to look extremely professional using your own custom website domain (e.g., `https://dashboard.bananavision.com`) instead of a `.ts.net` address.

### Setup Instructions
1. **Create an Account:** Sign up for a free [Cloudflare](https://dash.cloudflare.com/) account and add your domain name.
2. **Zero Trust Dashboard:** Navigate to the Cloudflare Zero Trust dashboard -> **Networks** -> **Tunnels**.
3. **Create Tunnel:** Click "Create a Tunnel", name it `BananaVision Edge`.
4. **Install Cloudflared Agent:** Cloudflare will give you a specific command to run on your Windows Mini PC. Run it in Command Prompt. It installs a background service that securely dials out to Cloudflare.
5. **Route the Traffic:** In the Cloudflare dashboard, configure the Public Hostname:
   - **Subdomain:** `dashboard`
   - **Domain:** `bananavision.com`
   - **Service:** `http://localhost:5173`
6. **Done:** The tunnel is immediately active. End users just navigate to `https://dashboard.bananavision.com`.

---

## Important Considerations for Edge Deployment

* **Auto-Start:** Tailscale runs as a Windows background service automatically. If the Mini PC loses power and reboots, Tailscale reconnects to the network instantly before you even log in to Windows.
* **Firewalls:** Neither Tailscale nor Cloudflare requires you to open ports on your warehouse internet router. They create *outbound* connections, which means your system remains completely invisible to malicious internet port scanners.
* **Backend Targeting:** By default, the Kiosk UI (running on `5173`) communicates with the backend via `localhost:8000`. If you use Tailscale Funnel, you may need to ensure your frontend's API URL dynamically points to the relative path or the backend is also exposed via the funnel.
