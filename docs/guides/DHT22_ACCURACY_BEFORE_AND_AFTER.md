# DHT22 Temperature, Humidity, and Shelf-Life Improvements (Before & After)

**Hardware kept:** Existing Arduino + DHT22 sensor setup (no new sensors or hardware replacements needed).

This document summarizes what changed to make temperature/humidity readings and banana shelf-life estimates more accurate, written in plain terms without code details.

---

## Quick Overview: Before vs. After

| Area | Before | After |
| :--- | :--- | :--- |
| **Reading freshness** | Older readings could pile up in a queue and lag behind real conditions. | Old queued messages are cleared out so only the newest valid reading is used. |
| **Sensor glitches & spikes** | A single sudden jump or invalid value right at scan time could skew the result. | Startup reads are stabilized, impossible numbers are blocked, sudden jumps must repeat 3 times to count, and recent samples are averaged without extreme outliers. |
| **Calibration** | No easy way to adjust if the DHT22 slightly over-reads or under-reads. | Optional temperature and humidity calibration offsets can be set if needed. |
| **Unplugged or stale sensor** | The last remembered reading could be reused indefinitely as if it were still live, and dropped USB connections stayed offline. | Readings older than 30 seconds are ignored for scans, the system tries to reconnect every 30 seconds, and screens note when the default `25°C / 65%` baseline is used. |
| **Shelf-life tracking after scan** | Remaining days only used the single snapshot taken at scan time. | Hourly sensor readings recorded after the scan continuously speed up or slow down estimated aging across Dashboard, Inventory, Scan Logs, Analytics, exports, Scan Detail, and Public QR. |

---

## Detailed Problem & Fix Breakdown

### 1. Lagging Readings (Queue Backlog & Startup Warm-Up)

- **The Problem (Before):**
  The Arduino sent a new reading roughly every 2 seconds, while the main server checked for messages every 5 seconds. Because messages arrived faster than they were collected, unread readings built up in a waiting line—meaning the system could read an older temperature instead of what the room felt like right then. In addition, the first reading right after powering on the DHT22 can be unstable.
- **How We Fixed It (After):**
  The Arduino now waits 2 seconds after powering on before taking its first reading so the sensor settles. On the computer side, every check clears out older waiting messages in the queue and keeps only the latest valid reading.

---

### 2. Sudden Spikes, Broken Values, and Sensor Drift

- **The Problem (Before):**
  DHT22 sensors can occasionally throw a sudden spike or an invalid value due to electrical noise or air movement. Because scanning captured a single moment, a brief spike right when pressing scan could distort that banana hand's recorded temperature, humidity, and predicted shelf life. There was also no calibration adjustment for slight factory offset.
- **How We Fixed It (After):**
  - **Physical limit checks:** Any reading outside the DHT22's real operating range (`-40°C to 80°C` and `0% to 100%` humidity) or any broken/non-numeric value is thrown out automatically both on the Arduino and in the app.
  - **Spike protection:** On the Arduino, a sudden jump (`more than 4°C` temperature change or `more than 15%` humidity change) is treated as suspicious and must stay consistent across 3 checks in a row before it is accepted.
  - **Outlier-trimmed averaging:** Instead of trusting a single jittery reading, recent valid readings (default 5 samples) have their highest and lowest extremes dropped and the middle readings averaged—giving a steadier measurement at scan time.
  - **Calibration offsets:** Configurable temperature and humidity offsets are available both on the Arduino and in system settings if you compare your DHT22 against a calibrated reference thermometer/hygrometer.

---

### 3. Disconnected or Stale Sensor Handling

- **The Problem (Before):**
  If the Arduino was unplugged or stopped sending updates, the system could continue holding onto the old reading and treat it as live when someone scanned a banana later. Also, once the USB sensor connection dropped, it did not automatically recover on its own.
- **How We Fixed It (After):**
  - **Freshness cutoff:** At scan time, readings older than 30 seconds (configurable) or readings from a disconnected sensor are no longer attached to the scan.
  - **Auto-reconnect:** If the USB connection drops, the system immediately marks the sensor disconnected and checks every 30 seconds to reconnect automatically once plugged back in.
  - **Clear baseline notice:** When a scan happens without a live sensor, the shelf-life predictor safely falls back to its standard `25°C / 65%` baseline and displays a clear note on Kiosk, Scan Detail, and the Public QR page so operators and viewers know a baseline was used rather than a live reading.

---

### 4. One-Time Snapshot vs. Continuous Storage Exposure

- **The Problem (Before):**
  Previously, the system predicted shelf life once using the temperature and humidity at the moment of scanning, then simply subtracted 1 day per calendar day afterward. For example, if bananas were scanned at `24°C` during intake and then stored in a hot `34°C` room for three days, the system still counted down as if they stayed at `24°C` the entire time.
- **How We Fixed It (After):**
  - **Continuous tracking after scan:** As long as the DHT22 keeps logging hourly conditions after a banana hand is scanned, the system compares actual storage temperature and humidity against the conditions at scan time. Warmer or excessively humid storage accelerates estimated biological aging and ripeness progression (within safe biological bounds), while cooler storage modestly slows it down.
  - **Unified across the app:** Dashboard summaries, Inventory FIFO priorities, Scan Logs, Analytics at-risk counts, Excel/PDF exports, Scan Detail, and the Public QR tracking page all stay in sync and roll forward accurately across Manila midnight. Closed inventory statuses (`Sold`, `Spoiled`, `For Processing`) stay frozen for staff records.
  - **Safeguards against false adjustments:** Readings recorded *before* a scan never affect that scan, and continuous adjustment only turns on when at least 25% of the storage period has real sensor coverage—so brief testing bursts or long power outages will not distort multi-day baselines. It can also be turned off in configuration if ever needed.
  - **Visible storage notes:** When continuous sensor data affects a scan, Scan Detail and the Public QR view display the post-scan average temperature, humidity, covered hours, and adjusted biological days vs. calendar days.

---

## Operational Note

- To apply the Arduino-side warmup, spike filter, and smoothing on hardware, re-upload the updated sketch (`arduino/dht22_sensor/dht22_sensor.ino`) to your Arduino board via the Arduino IDE.
- All software changes are backward-compatible and already integrated into the existing backend and frontend without changing the serial cable protocol or database structure.
