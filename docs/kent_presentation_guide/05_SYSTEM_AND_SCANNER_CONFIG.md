# ⚙️ Deep Dive: System Configuration, Hardware Mapping & Station Power

> **Features Covered:**  
> - Feature 9: System Configuration  
> - Feature 10: Scanner Hardware Configuration (4-Camera Setup & Calibration)  
> **Backend Files:** [`backend/app/api/v1/config.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/config.py), [`backend/app/api/v1/cameras.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/cameras.py), [`backend/app/services/camera_manager.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/camera_manager.py), [`backend/app/services/configuration.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/configuration.py)  
> **Frontend Files:** [`frontend/src/pages/admin/SystemConfig.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/admin/SystemConfig.tsx), [`frontend/src/components/CameraCalibrationModal.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/components/CameraCalibrationModal.tsx)

---

## 1. Why Did We Implement This System?

BananaVision is deployed on a dedicated physical Mini PC connected to **4 USB industrial webcams** positioned inside a scanning enclosure:
1. **Top Camera:** Overhead view for cluster geometry, finger separation, and length.
2. **Left Camera:** Side profile for curvature and finger tip ripeness.
3. **Right Camera:** Opposite side profile for hidden finger coverage.
4. **Rear Camera:** Backside view to inspect the crown and stem.

Because Linux and Windows OS enumerate USB video devices dynamically on reboot (e.g. `/dev/video0`, `/dev/video2`, or Windows DirectShow indices `0, 1, 2, 3`), device indices can swap!
Administrators need:
- A live **Camera Calibration tool** to view MJPEG streams and assign the correct physical device index to each logical view.
- Strict **Station Concurrency Locks** so a user cannot remap cameras while another operator is actively triggering a scan.
- Safe **OS Power Controls** (reboot/shutdown) directly from the browser touch screen.

---

## 2. Security & Hardware Vulnerabilities Fixed

| Vulnerability ID | Historical Flaw | How Kent's Code Fixed It |
|---|---|---|
| **SCANNER-01** | POST `/cameras/mapping` had no authentication check, allowing any network caller to reassign or disable station cameras. | Protected with `admin: AdminUser`, strictly requiring administrative JWT authentication. |
| **SCANNER-02** | Renaming camera IDs in the UI fabricated an "Online" status without actually probing hardware handles. | Synchronized with `camera_manager.online_cameras` so only cameras with open, verified video streams report as `Online`. |
| **SCANNER-03** | Remapping device indices left in-memory singleton caches stale, causing subsequent captures to read from old camera indices. | Coordinated via `configuration.apply_camera_config()` which releases existing OpenCV VideoCapture handles and re-initializes `camera_manager._device_ids` atomically. |
| **CONFIG-01** | Saving settings simulated a delay and claimed success before the HTTP request finished. | Connected to real async PATCH requests with optimistic concurrency revision checks (`expected_revision`). |

---

## 3. Hardware Architecture: The 4-Camera Physical Pipeline

```
[ Physical Station Enclosure ]
 ├── Top Camera   (USB Index 0) ──┐
 ├── Left Camera  (USB Index 1) ──┼──> [ OpenCV VideoCapture Pool ]
 ├── Right Camera (USB Index 2) ──┤                │
 └── Rear Camera  (USB Index 3) ──┘                ▼
                                      [ camera_manager.py ]
                                         │            │
                           (Live Previews)            (Active Scan)
                                 │                          │
                        MJPEG Generator             Parallel Capture
                      (15 FPS downscaled)           (Full Resolution)
                                 │                          │
                        Admin Calibration          Two-Stage YOLO AI
```

---

## 4. Code Breakdown: Part-by-Part

### Part A: Concurrency Protection via `station_lock` (`config.py:40` & `cameras.py:157`)

What happens if an admin changes camera settings while an operator is scanning bananas?
```python
@router.patch("", response_model=SystemConfigResponse)
async def update_config(body: SystemConfigUpdate, db: DbSession, admin: AdminUser, request: Request):
    if body.camera_ids is None and body.camera_device_ids is None:
        return await _update_config(body, db, admin, request)
    
    # ── Concurrency Check ──
    if station_lock.locked():
        raise HTTPException(409, "Finish the active scan or mapping before changing cameras")
    
    async with station_lock:
        return await _update_config(body, db, admin, request)
```
- `station_lock` is an asynchronous mutual exclusion lock (`asyncio.Lock`). It guarantees that hardware reconfiguration and image acquisition can never overlap, preventing race conditions and kernel driver crashes.

---

### Part B: Physical Camera Discovery (`backend/app/api/v1/cameras.py:32`)

```python
@router.get("/discovery", response_model=CameraDiscoveryResponse)
async def discover_cameras(db: DbSession, admin: AdminUser):
    """Enumerate named devices for administrators without acquiring camera handles."""
    config = await configuration.get_config(db)
    async with coordinator.operation():
        discovered = await run_blocking(discover_camera_devices)
        
    saved = dict(zip(config.camera_device_ids, (name.strip() for name in config.camera_ids.split(',')), strict=True))
    applied = dict(zip(camera_manager._device_ids, camera_manager._logical_ids, strict=False))
    online = set(camera_manager.online_cameras)
    
    for device in discovered['devices']:
        device_id = device['device_id']
        name = saved.get(device_id)
        device['configured_camera_id'] = name
        device['online'] = (name is not None and applied.get(device_id) == name and device_id in online)
        
    return discovered
```
- In `SystemConfig.tsx`, clicking "Refresh Device List" triggers this endpoint, allowing admins to see every connected USB video peripheral and its device index.

---

### Part C: Real-Time MJPEG Preview Generator (`cameras.py:65`)

How does BananaVision stream live video to the browser without heavy WebRTC or RTSP servers?
```python
async def generate_frames(camera_index: int, fps: int = 15):
    """Captures frames continuously, downscales them, and yields MJPEG chunks."""
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} is not online")

    interval = 1.0 / fps
    loop = asyncio.get_event_loop()

    while True:
        start_time = loop.time()
        capture = await run_blocking(camera_manager._capture_single, camera_index)
        frame = capture.frame
        
        # Downscale to preview resolution to save network bandwidth & CPU
        height, width = frame.shape[:2]
        scale = min(1.0, 640 / width, 480 / height)
        if scale < 1.0:
            frame = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)

        # Encode frame as JPEG byte buffer
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        
        # Yield multipart HTTP response chunk
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )
        await asyncio.sleep(interval)
```
- The frontend simply points an standard `<img>` tag to `/api/v1/cameras/preview/0`! The browser natively displays the stream at 15 FPS with near-zero latency.

---

### Part D: Authenticated Camera Remapping (`cameras.py:154`)

```python
class CameraMappingUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    operation_id: uuid.UUID
    device_ids: list[StrictInt] = Field(min_length=1, max_length=4)

    @field_validator("device_ids")
    @classmethod
    def valid_mapping(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Camera indices must be distinct and nonnegative")
        return ids

@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate, db: DbSession, admin: AdminUser):
    # Validated: strictly 1-4 distinct, non-negative integer indices
    # Atomically updates environment, closes stale camera handles, and re-probes hardware
    ...
```

---

### Part E: Station Power Management (`config.py` & `SystemConfig.tsx`)

In `SystemConfig.tsx`, admins can issue **System Restart** or **System Shutdown** commands.
- Under the hood, FastAPI spawns the OS shutdown sequence:
  - On Windows: `shutdown /r /t 5` (reboot) or `shutdown /s /t 5` (shutdown).
  - On Linux: `systemctl reboot` or `systemctl poweroff`.
- If an administrator initiates an intentional maintenance reboot, the system registers a `power-accepted` state. When the station boots back up, it requires an active administrator credential check to resume normal operations.

---

## 5. Summary of Key Defense Takeaways

1. **Hardware Flexibility:** BananaVision does not assume fixed hardware IDs; admins can calibrate and remap any camera view on the fly.
2. **Race-Condition Proof:** `station_lock` ensures camera hardware cannot be modified while bananas are being scanned.
3. **Bandwidth Efficient:** Multi-part MJPEG preview streaming allows responsive 15 FPS alignment without bogging down the Mini PC CPU.
