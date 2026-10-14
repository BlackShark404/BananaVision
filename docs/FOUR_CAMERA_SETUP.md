# Four-camera setup

The supplied log says `Cameras: [0, 1]` and `Cameras online: 2/2`.
Only two slots were configured; this is not a discovery result for all Windows devices.
The previous calibration screen could only rearrange those existing slots.

System Configuration now supports adding slots up to four and editing each physical
device index. Names and indices are saved together through the existing revision-checked
configuration API. Saved configuration remains authoritative across backend restarts;
`CAMERA_DEVICE_IDS` only seeds a station without saved configuration.

## Apply at the station

1. Restart the backend to use the updated Windows capture initialization; refresh the UI.
2. As administrator, open **System Configuration → Scanner Config**.
3. Click **Add Camera** until **4/4 camera slots configured** appears.
4. Enter a distinct device index for each scanner camera and click **Save Changes**.
   **Detected camera devices** lists native Windows names and indices from the capture
   backend. Choose a named device in each slot's dropdown, or retain manual index entry.
   Use **Refresh Device List** after reconnecting a camera. Identical camera models have
   short device identifiers so their entries remain distinguishable.
   Windows Device Manager ordering does not establish OpenCV indices. The supplied
   screenshot includes a built-in ACER webcam plus four external cameras. If the built-in
   camera is index 0, the external indices may be `1, 2, 3, 4`; verify rather than assume.
5. Open **Calibrate Camera Positions** to check the four feeds and swap positions as
   needed. If an index selects the laptop webcam or an offline feed, close calibration,
   correct that index in Scanner Config, save, and check again.
   Calibration also displays each configured device's index, name and identifier.
6. Confirm four online cameras in Devices/Kiosk. Each scan uses the configured online
   cameras. A partial hardware result stays partial; a configured slot is not proof that
   the camera is producing frames. Use **Retry Applying Cameras** after reconnecting.

## Windows driver settings

The supplied logs also contain MSMF frame-read errors. `CAMERA_BACKEND=auto` now
selects DirectShow on Windows, and initialization requests MJPG at 15 FPS before
warmup. These are driver requests, not guarantees; usable frame checks still determine
Online status. Non-Windows automatic backend selection is unchanged.

The request order is FPS, resolution, then MJPG format last. DirectShow can rebuild
the stream when FPS changes; making compression the final format request avoids
losing the requested format during that rebuild.

The user confirmed four simultaneous live feeds after connecting the cameras directly
to laptop USB ports instead of sharing the original hub. Keep that working connection
arrangement. The correct saved mapping remains `0, 1, 3, 2`; index `4` is the OBS
virtual camera on this station and should not replace the fourth physical camera.

The interrupted fallback/recovery experiment has been removed. No automatic resolution
reduction or newly introduced fallback settings are required for this working setup.

Deployment overrides, requiring backend restart:

```dotenv
CAMERA_BACKEND=auto
CAMERA_FOURCC=MJPG
CAMERA_FPS=15
```

`CAMERA_BACKEND=msmf` remains available if a device requires Media Foundation.
Verify indices again after changing capture backend. If four correct indices cannot
stream together, close other camera applications and check USB power/controller
capacity; try a lower configured capture resolution such as 640×480. No physical
camera or USB compatibility test was performed as part of this code change.

If the log shows working indices `0, 1, 3` and an offline index `4`, check the device
list for index `2`. The unused index may be the missing scanner camera; select it by
name and verify its feed. Device Manager can list devices that are not exposed by the
selected capture backend, so its list alone cannot establish a valid index `4`.

Name discovery requires `cv2-enumerate-cameras==1.4.0` on Windows, included in
`backend/requirements.txt` and installed in the local backend virtual environment.
On another Windows installation, install the backend requirements before restarting.
The administrative `/api/v1/cameras/discovery` endpoint enumerates metadata without
opening streams or changing saved mapping. Enumeration uses the same backend as capture;
raw device paths are hashed into short identifiers. If discovery fails or is unsupported,
manual mapping remains available and the screen shows an error rather than guessing names.

The enumeration library's [source and API reference](https://github.com/lukehugh/cv2_enumerate_cameras)
describe the backend-specific indices and Windows device metadata.

OpenCV documents the backend and capture-property controls in its
[video I/O reference](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html).

## Verification

- Hardware-mocked tests cover four persistent handles, four captures, logical mapping,
  DirectShow/Media Foundation selection, failed-open cleanup, and non-Windows behavior.
- Isolated API tests cover expansion from two slots to four, persistence, and listing.
- Browser fixtures cover adding four slots, device-only edits, retaining drafts during
  refresh, rejecting duplicate/empty indices, selecting an unused named device, and
  keeping manual edits after failed discovery. No live database, camera, captures,
  sensor, printer, or OS power operation is used by these checks.

The model issue is outside this camera-only change, per the user's narrowed request.
