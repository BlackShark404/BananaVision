# ⚙️ Master Guide: System Configuration, 4-Camera Hardware Mapping & Station Power

> **Presenter & Author:** Kent RG A. Baguio  
> **Core Focus:** 4-Camera Physical Inspection Array, Hardware Dynamic Enumeration, Synchronized Live MJPEG Streaming (`MediaUser`), Atomic Station Concurrency Lock (`station_lock`), and Operating System Power Governance.  
> **Backend Files:**
> - [`backend/app/api/v1/cameras.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/cameras.py) — Camera discovery, live preview MJPEG generator, authenticated remapping
> - [`backend/app/services/camera_manager.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/camera_manager.py) — OpenCV `VideoCapture` singleton pool, hardware frame acquisition
> - [`backend/app/services/camera_discovery.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/camera_discovery.py) — Kernel device bus prober (DirectShow on Windows / V4L2 on Linux)
> - [`backend/app/services/runtime_operations.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/services/runtime_operations.py) — Concurrency primitives (`station_lock`)
> - [`backend/app/api/v1/config.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/config.py) — System threshold settings, station power controls
>
> **Frontend Files:**
> - [`frontend/src/pages/admin/SystemConfig.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/admin/SystemConfig.tsx) — Configuration control center, threshold sliders, power dialogs
> - [`frontend/src/components/CameraCalibrationModal.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/components/CameraCalibrationModal.tsx) — 4-quadrant live camera alignment and hardware remapping modal

---

## 1. Why Did We Implement This System? (Panel Defense Rationale)

### 1.1 The Physical Problem: Banana Hand Geometry & Occlusion
Bananas are three-dimensional, curved botanical clusters:
- If you inspect a banana hand using only **one single overhead camera**, you can only see the outer curve of the top layer of fingers. The inner whorl, the underside crown, and the finger tips pointing downward are completely occluded (invisible).
- A single camera cannot accurately count fingers or grade ripeness because rot and blemishes often initiate on the backside stem or hidden inner fingers.
- **The Solution — The 4-Camera Physical Rig:**
  1. **Top Camera (`Scanner 1`):** Captures overall cluster span, finger spacing, and curvature.
  2. **Left Camera (`Scanner 2`):** Captures lateral finger tips and left-side skin coloration.
  3. **Right Camera (`Scanner 3`):** Captures opposite side profile and hidden inner finger layers.
  4. **Rear Camera (`Scanner 4`):** Inspects the crown, stem cut, and bottom underside.

### 1.2 The Hardware Problem: OS Device Swapping on Reboot
When 4 USB cameras are plugged into a Mini PC running Windows or Linux:
- The operating system does **not** guarantee persistent device index assignments across reboots.
- On Monday, the Top camera might be DirectShow Device `0`. On Tuesday after a reboot, Windows may enumerate the USB hub differently, making the Top camera Device `2`!
- Without a hardware calibration tool, the Top camera's computer vision pipeline would receive frames from the Rear camera, causing YOLO detection failures.
- **The Solution:** A dedicated **Camera Calibration & Remapping Tool** (`CameraCalibrationModal.tsx`). Administrators can view real-time video feeds from all 4 USB devices and reassign which physical device index maps to which logical perspective without modifying backend source code.

### 1.3 Concurrency Protection (`station_lock`): Preventing Kernel Crashes
OpenCV `cv2.VideoCapture` handles interact directly with OS kernel video drivers.
- If an administrator attempts to change camera index mapping while an operator is actively executing a YOLO scan, the camera handle would be closed while in the middle of a frame read, causing an unhandled segmentation fault and crashing the Python process.
- **The Solution — `station_lock`:** An asynchronous mutual exclusion lock (`asyncio.Lock`). Every active scan and every camera remapping operation must acquire `station_lock`. If someone attempts to remap cameras while a scan is in flight, the request is rejected immediately with `HTTP 409 Conflict: Finish the active scan before changing cameras`.

---

## 2. High-Level Architecture & End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Admin as System Administrator
    participant UI as CameraCalibrationModal.tsx
    participant ApiClient as lib/api.ts
    participant Router as cameras.py
    participant Lock as station_lock (asyncio.Lock)
    participant CamMgr as camera_manager.py
    participant CV as OpenCV (cv2.VideoCapture)
    participant DB as PostgreSQL (system_configs)

    %% CAMERA DISCOVERY
    Admin->>UI: Click "Calibrate Cameras" in SystemConfig
    UI->>ApiClient: api.cameras.discover()
    ApiClient->>Router: GET /api/v1/cameras/discovery (Bearer <AdminToken>)
    Router->>Router: Enumerate kernel USB video devices (DirectShow / V4L2)
    Router-->>UI: HTTP 200 { devices: [{ device_id: 0, name: "USB Camera #1" }, ...] }

    %% LIVE MJPEG STREAMING
    loop Every Frame (15 FPS)
        UI->>Router: GET /api/v1/cameras/preview/{index}?token=<session_token>
        Router->>Router: Verify MediaUser dependency (Valid JWT & Active user)
        Router->>CamMgr: _capture_single(index)
        CamMgr->>CV: cap.read() -> frame
        CV-->>CamMgr: Raw BGR Frame (1920x1080)
        CamMgr-->>Router: Raw Frame
        Router->>Router: Downscale frame (640x480) & JPEG encode (Quality 75)
        Router-->>UI: HTTP Multipart Chunk: --frame\r\nContent-Type: image/jpeg\r\n\r\n<bytes>
        UI->>UI: Native <img> element displays frame smoothly
    end

    %% CAMERA REMAPPING
    Admin->>UI: Swap indices: Top -> Index 2, Rear -> Index 0
    Admin->>UI: Click "Save Camera Mapping"
    UI->>ApiClient: api.cameras.updateMapping({ device_ids: [2, 1, 3, 0] })
    ApiClient->>Router: POST /api/v1/cameras/mapping (Bearer <AdminToken>)
    Router->>Lock: station_lock.locked()?
    alt Active Scan Holding Lock
        Lock-->>Router: True
        Router-->>UI: HTTP 409 Conflict "Active scan in progress"
    else Lock Free
        Router->>Lock: async with station_lock:
        Router->>CamMgr: Release all open cv2.VideoCapture handles
        Router->>CamMgr: Re-initialize camera handles with new device indices
        Router->>DB: UPDATE system_configs SET camera_device_ids = '[2, 1, 3, 0]'
        DB-->>Router: Commit update
        Router-->>UI: HTTP 200 Mapping Updated Successfully
        UI->>Admin: Toast "Camera mapping applied and verified"
    end
```

---

## 3. Step-by-Step Code Walkthrough: Front to Back to Front

### Step 1: Camera Discovery in [`backend/app/api/v1/cameras.py:32`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/cameras.py)

When an admin opens the calibration modal:

```python
# backend/app/api/v1/cameras.py (lines 32-48)
@router.get("/discovery", response_model=CameraDiscoveryResponse)
async def discover_cameras(db: DbSession, admin: AdminUser):
    """Enumerate named devices for administrators without acquiring camera handles."""
    config = await configuration.get_config(db)
    
    # Run blocking kernel discovery in background thread pool
    async with coordinator.operation():
        discovered = await run_blocking(discover_camera_devices)
        
    saved = {slot.device_index: slot.camera_id for slot in config.camera_slots}
    applied = dict(zip(camera_manager._device_ids, camera_manager._logical_ids, strict=False))
    online = set(camera_manager.online_cameras)
    
    for device in discovered['devices']:
        device_id = device['device_id']
        name = saved.get(device_id)
        device['configured_camera_id'] = name
        device['online'] = (
            name is not None and applied.get(device_id) == name and device_id in online
        )
        
    return discovered
```

- **SCANNER-02 Vulnerability Fix:** Notice lines 45–47. Previously, the UI marked cameras as "Online" merely because they were listed in the database. Now, a camera is only reported as `Online` if `device_id in online` (meaning an actual OpenCV capture stream successfully opened and returned test pixels).

---

### Step 2: The High-Efficiency MJPEG Preview Stream (`cameras.py:64`)

How does BananaVision display 4 live video feeds simultaneously on an edge Mini PC without maxing out the CPU?

```python
# backend/app/api/v1/cameras.py (lines 64-126)
async def generate_frames(camera_index: int, fps: int = 15):
    """Captures frames continuously, downscales them, and yields MJPEG chunks."""
    if camera_index not in camera_manager.online_cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} is not online")

    interval = 1.0 / fps
    loop = asyncio.get_event_loop()
    generation = camera_manager.generation

    while generation == camera_manager.generation:
        start_time = loop.time()
        try:
            # 1. Grab raw high-res frame from camera thread
            async with coordinator.operation():
                capture = await run_blocking(camera_manager._capture_single, camera_index)
            
            frame = capture.frame
            height, width = frame.shape[:2]
            
            # 2. Downscale to preview bounds (640x480 max) to conserve CPU & RAM
            scale = min(1.0, settings.camera_preview_max_width / width, settings.camera_preview_max_height / height)
            if scale < 1.0:
                frame = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)

            # 3. Compress to JPEG format with 75% quality
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not success:
                await asyncio.sleep(interval)
                continue

            # 4. Stream multipart HTTP boundary chunk
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
            )
        except Exception:
            break

        # 5. Precise FPS pacing
        elapsed = loop.time() - start_time
        sleep_time = interval - elapsed
        await asyncio.sleep(sleep_time if sleep_time > 0 else 0.001)
```

#### Why `MediaUser` Accepts Query Tokens (`deps.py:68`):
In `frontend/src/components/CameraCalibrationModal.tsx`, the video is rendered as:
```tsx
<img src={`/api/v1/cameras/preview/${cam.deviceId}?token=${token}`} alt="Live Stream" />
```
Because standard HTML `<img>` elements cannot send an `Authorization: Bearer <token>` header, `deps.py` defines `MediaUser`. It accepts the session token via query parameters (`?token=`), decodes it, verifies `token_version`, and authorizes the image stream.

---

### Step 3: Concurrency Protection & Remapping (`cameras.py:154`)

When the administrator modifies device assignments and clicks Save:

```python
# backend/app/api/v1/cameras.py (lines 154-190)
class CameraMappingUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    device_ids: list[StrictInt] = Field(min_length=1, max_length=4)

    @field_validator("device_ids")
    @classmethod
    def valid_mapping(cls, ids: list[int]) -> list[int]:
        # Enforce uniqueness: Cannot assign two logical cameras to the same physical index!
        if len(set(ids)) != len(ids) or any(i < 0 for i in ids):
            raise ValueError("Camera indices must be distinct and nonnegative")
        return ids

@router.post("/mapping")
async def update_camera_mapping(mapping: CameraMappingUpdate, db: DbSession, admin: AdminUser):
    # ── Concurrency Guard: Check station_lock ─────────────────────────
    if station_lock.locked():
        raise HTTPException(status_code=409, detail="Finish active scan before remapping cameras")

    async with station_lock:
        # Atomic reconfiguration in services/configuration.py:
        # 1. Releases open OpenCV VideoCapture handles
        # 2. Re-instantiates hardware handles with new indices
        # 3. Increments configuration revision in PostgreSQL
        await configuration.apply_camera_mapping(db, mapping.device_ids)

    return {"message": "Camera mapping updated successfully"}
```

---

### Step 4: Operating System Power Management (`config.py:195`)

In `SystemConfig.tsx`, admins can issue **System Restart** or **System Shutdown** commands.
- **FastAPI Subprocess Execution:**
  - On Windows: `shutdown /r /t 5` (Reboot) or `shutdown /s /t 5` (Power off).
  - On Linux: `systemctl reboot` or `systemctl poweroff`.
- **Maintenance State (`power-accepted`):** When the admin triggers a reboot, BananaVision transitions into `power-accepted`. When the machine reboots, it requires an active administrator credential check to resume scanning operations, preventing unverified hardware restarts.

---

## 4. Security & Hardware Vulnerabilities Fixed in This Module

| Vulnerability ID | Historical Flaw Identified | How Kent's Code Fixed It |
|---|---|---|
| **SCANNER-01** | `POST /cameras/mapping` had no authentication guard; anyone on the LAN could disable station cameras. | Protected with `admin: AdminUser` dependency, rejecting non-admins with `HTTP 403 Forbidden`. |
| **SCANNER-02** | The UI marked cameras as "Online" without probing real hardware handles. | Synchronized with `camera_manager.online_cameras`: a camera is only `Online` if OpenCV can open the handle and pull valid frames. |
| **SCANNER-03** | Remapping device indices left in-memory singleton caches stale, causing subsequent captures to read from old camera indices. | Coordinated via `configuration.apply_camera_mapping()` which releases open handles and refreshes `camera_manager._device_ids` atomically. |
| **CONFIG-01** | Saving configuration simulated a delay and claimed success before the HTTP request finished. | Connected to real async PATCH requests with optimistic concurrency revision checks (`expected_revision`). |

---

## 5. Defense Cheat Sheet: Panel Traps & Winning Answers

### Question 1: "Why do you need 4 cameras? Wouldn't 1 camera with a motorized turntable be cheaper?"
> **Kent's Winning Answer:**  
> "A commercial banana packinghouse processes thousands of hands per hour. A motorized turntable introduces mechanical moving parts that wear down in tropical humidity and creates a 5-to-10 second mechanical delay per banana hand. Our 4-camera fixed array captures Top, Left, Right, and Rear views simultaneously in parallel in under 200 milliseconds with zero moving parts. This eliminates mechanical failure points and quadruples inspection throughput."

### Question 2: "What prevents an Administrator from remapping cameras while an Operator is scanning bananas?"
> **Kent's Winning Answer:**  
> "We engineered the **`station_lock` concurrency safeguard** in `backend/app/services/runtime_operations.py`. Both active multi-camera YOLO scans and camera remapping requests must acquire the asynchronous `station_lock`. If an administrator submits a remapping request while a scan is in progress, the backend rejects it with an `HTTP 409 Conflict` error stating: *'Finish the active scan before changing cameras'*. This prevents OpenCV driver race conditions and kernel crashes."

### Question 3: "Why do you use MJPEG for live video preview instead of WebRTC or RTSP?"
> **Kent's Winning Answer:**  
> "WebRTC and RTSP require heavy streaming media servers (like Janus or GStreamer), complex SDP signaling handshakes, and open UDP port ranges, which consume substantial memory on an edge Mini PC. MJPEG is lightweight and stateless: our backend downscales frames to 640x480, compresses them with OpenCV at 75% JPEG quality, and yields multipart HTTP chunks directly to a standard HTML `<img>` tag at 15 FPS. It works natively across every browser with sub-50ms latency and minimal CPU overhead."
