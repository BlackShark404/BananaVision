# BananaVision Kiosk Auto-Start Guide

This guide explains how to configure your Edge Node (Mini PC) so that it automatically boots into the BananaVision full-screen scanning kiosk the moment power is turned on.

Because our startup scripts (`start.bat` for Windows and `start.sh` for Linux) launch a visual Chrome window, they require the operating system to boot into the desktop environment first. This means you cannot run them as headless background services.

Follow these steps for your respective Operating System.

---

## 1. Prerequisites (For Both OS)
You must configure the Mini PC to **Auto-Login** when it turns on. If the PC stops at a password or welcome screen, the script cannot run and the kiosk will not appear.
* **Windows:** Press `Win + R`, type `netplwiz`, uncheck "Users must enter a user name and password", and click Apply.
* **Linux (Ubuntu):** Go to Settings -> Users -> Unlock the panel -> Toggle "Automatic Login" to ON.

---

## 2. Windows Configuration
If you are using a Windows Mini PC, you will use the `start.bat` file and the Windows Startup folder.

1. Ensure your `start.bat` file is correctly located in the root of the `BananaVision` project folder.
2. Press `Win + R` to open the Run dialog.
3. Type `shell:startup` and press **Enter**. This opens the special folder where Windows looks for apps to launch upon login.
4. Locate your `start.bat` file in your project folder, **Right-Click** it, and select **Copy**.
5. Go back to the `shell:startup` folder window, right-click anywhere in the empty space, and select **"Paste Shortcut"** (Do not "Paste" the file itself, only a shortcut).

**Result:** The next time the PC is plugged in, Windows will auto-login, execute the shortcut, start the FastAPI and Frontend servers, and force Google Chrome into fullscreen kiosk mode.

---

## 3. Linux Configuration (Ubuntu / Debian)
If you are using a Linux Mini PC (with a Desktop Environment like GNOME or KDE), you will use the `start.sh` file. 

*First, make sure the script is executable by running `chmod +x /path/to/BananaVision/start.sh` in the terminal.*

### Method A: Using GUI (Recommended)
1. Open your Applications menu and search for **"Startup Applications"**.
2. Click **Add**.
3. Fill out the fields:
   * **Name:** BananaVision Kiosk
   * **Command:** Click "Browse" and locate your `start.sh` file (e.g., `/home/warehouse/BananaVision/start.sh`).
   * **Comment:** Launches Edge Node and UI.
4. Click **Save** or **Add**.

### Method B: Using Terminal (Headless Setup)
If you prefer configuring via terminal, you can create a `.desktop` entry in your autostart folder.

1. Open a terminal and create the file:
   ```bash
   nano ~/.config/autostart/bananavision.desktop
   ```
2. Paste the following configuration (Ensure you change `/path/to/` to your actual absolute path):
   ```ini
   [Desktop Entry]
   Type=Application
   Exec=/path/to/BananaVision/start.sh
   Hidden=false
   NoDisplay=false
   X-GNOME-Autostart-enabled=true
   Name=BananaVision Kiosk
   ```
3. Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

**Result:** When the Linux PC reboots, it logs in the user automatically, runs the backend and frontend in the background, and launches Chromium/Google Chrome in kiosk mode over the desktop.
