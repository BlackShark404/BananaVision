# `11_ai_settings_flow.md` — Module 11: AI Settings (YOLOv26 Confidence Threshold, Detection Cutoff & Auto-Flag Fusion) Full-Stack Execution & Code Trace

---

## 1. Master File Path Map

| Relative File Path | Layer / Role in Module 11 (AI Settings / YOLOv26) |
| :--- | :--- |
| `frontend/src/pages/admin/SystemConfig.tsx` | **Detection Review Tab UI (`<TabsContent value="ai">`):** Renders the `"Review Confidence Threshold"` `<Slider>` (`min={1}`, `max={100}`, `step={1}`), live percentage label (`{localConfig.confidenceThreshold}%`), collapsible `"Model information"` details showing `config.detectionConfidenceThreshold`, and the sticky `"Save Changes"` bar. |
| `frontend/src/context/AdminContext.tsx` | **Config State & Diff Sender (`updateConfig`):** Compares `cfg.confidenceThreshold !== config.confidenceThreshold`, sends `PATCH /api/v1/config` with `{ expected_revision, confidence_threshold }`, and updates `config.confidenceThreshold` and `config.detectionConfidenceThreshold`. |
| `frontend/src/lib/api.ts` | **HTTP Fetch Client:** Sends `PATCH /api/v1/config` with `Authorization: Bearer <token>`. |
| `backend/app/schemas/common.py` | **Pydantic Validation (`SystemConfigUpdate` & `SystemConfigResponse`):** Enforces `confidence_threshold: StrictInt | None = Field(None, ge=1, le=100)` and returns `confidence_threshold: int` and `detection_confidence_threshold: float`. |
| `backend/app/api/v1/config.py` | **Config Controller (`PATCH /api/v1/config`):** Saves `confidence_threshold` without acquiring `station_lock` (so threshold edits never block or wait on active camera scans) and records `AuditAction.CONFIG_CHANGED` (`"Config revision X → Y: confidence_threshold 80 → 85"`). |
| `backend/app/services/configuration.py` | **Effective Detection Cutoff Calculator (`config_response` & `update_config`):** Updates `system_config.confidence_threshold` and computes `detection_confidence_threshold = min(config.confidence_threshold, get_settings().yolo_confidence_threshold * 100)`. |
| `backend/app/config.py` | **YOLOv26 Model & Inference Environment Settings (`Settings`):** Configures `yolo_model_path = "app/ml/weights/banana_yolov26n.pt"`, `yolo_confidence_threshold = 0.50`, `yolo_iou_threshold = 0.45`, and `yolo_inference_head = "one_to_many_nms"`. |
| `backend/app/services/scan_service.py` | **Scan Pipeline Threshold Consumer (`_execute_scan_pipeline`):** Reads `config = await get_config(db)`, computes `review_confidence_threshold = config.confidence_threshold / 100.0` and `confidence_threshold = min(review_confidence_threshold, get_settings().yolo_confidence_threshold)`, passes `confidence_threshold` to `banana_classifier.predict()`, and passes `review_confidence_threshold` to `fusion_engine.fuse()`. |
| `backend/app/services/classification.py` | **YOLOv26 Classifier Wrapper (`BananaClassifier`):** Loads `banana_yolov26n.pt`, locks the `"one_to_many_nms"` detection head before warmup (`_apply_inference_head`), verifies checkpoint SHA-256 against `TOP_CALIBRATED_CHECKPOINTS`, runs Ultralytics `self._model.predict(image, conf=confidence_threshold, iou=iou_threshold, ...)`, filters non-banana boxes, and returns `ClassificationResult`. |
| `backend/app/services/fusion_engine.py` | **Multi-Camera Fusion & Auto-Flag Engine (`FusionEngine.fuse`):** Computes `final_confidence` across supporting camera views and sets `auto_flagged = final_confidence < threshold_percent` (`flag_reason = "Confidence X% is below the Y% threshold"`). |
| `backend/app/models/system_config.py` | **SQLAlchemy ORM Model (`system_config`):** Persists `confidence_threshold` (`Integer, default=80`) and `revision`. |

---

## 2. Step-by-Step Code Execution Trace (With Full Inline Code)

---

### Phase A & B: Detection Tab UI, Slider Interaction & Save Dispatch

#### Step A1: `"Detection Review"` Tab (`<TabsContent value="ai">`) & Slider State (`SystemConfig.tsx`)
* **Step Title & Trigger:** Administrator clicks the `"Detection"` tab (`value="ai"`) on `/admin/config`, drags the `"Review Confidence Threshold"` `<Slider>` between `1%` and `100%`, and clicks `"Save Changes"` (`handleSave`).
* **Exact File Path & Line Numbers:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 101, 153–172, 372–408, 525–538)
* **Complete Uncut Code Block:**
```tsx
  const hasChanges = configReady && (localConfig.cameraIds !== config.cameraIds || JSON.stringify(localConfig.cameraDeviceIds) !== JSON.stringify(config.cameraDeviceIds) || localConfig.confidenceThreshold !== config.confidenceThreshold || localConfig.dataRetentionEnabled !== config.dataRetentionEnabled)
```
```tsx
  const handleSave = async () => {
    if (disabled || configFlight.current) return
    const deviceIds = localConfig.cameraDeviceIds ?? []
    if (deviceIds.length !== activeCameraIds.length || new Set(deviceIds).size !== deviceIds.length || deviceIds.some(id => !Number.isSafeInteger(id) || id < 0)) {
      toast.error("Assign a distinct nonnegative device index to every camera")
      return
    }
    configFlight.current = true
    setSaving(true)
    try {
      const saved = await updateConfig(localConfig)
      setLocalConfig(saved)
      toast.success("Settings saved successfully", { description: saved.applicationError ?? "Applied to subsequent operations" })
    } catch (error) {
      toast.error("Settings could not be saved", { description: error instanceof Error ? error.message : "Please try again." })
    } finally {
      configFlight.current = false
      setSaving(false)
    }
  }
```
```tsx
        <TabsContent value="ai" className="m-0 border-0 outline-none">
          <Card className="rounded-xl sm:rounded-2xl">
            <CardHeader className="px-4 sm:px-6 pt-4 sm:pt-6">
              <CardTitle className="text-base sm:text-lg">Detection Review</CardTitle>
              <CardDescription className="text-xs sm:text-sm">Choose when scan results need a closer look.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 px-4 sm:px-6">
              <div className="space-y-4">
                <div className="flex justify-between">
                  <Label id="review-confidence-label" className="text-sm">Review Confidence Threshold</Label>
                  <span className="font-bold text-primary">{localConfig.confidenceThreshold}%</span>
                </div>
                <Slider aria-labelledby="review-confidence-label"
                  value={[localConfig.confidenceThreshold]} 
                  onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}
                  min={1}
                  disabled={saving || disabled}
                  max={100} 
                  step={1} 
                  className="w-full"
                />
                <p className="text-xs text-muted-foreground">
                  Results below {localConfig.confidenceThreshold}% are flagged for review.
                  <span className="block mt-1">Applies to the next scan after saving.</span>
                </p>
              </div>
              <details className="border-t pt-4 text-xs text-muted-foreground">
                <summary className="cursor-pointer w-fit rounded focus-visible:outline-ring">Model information</summary>
                <div className="mt-3 space-y-2">
                  <p>YOLO26 detections keep their original confidence scores. The current detection cutoff below reflects the saved configuration.</p>
                  {config.detectionConfidenceThreshold !== undefined && <p>Current YOLO detection cutoff: {config.detectionConfidenceThreshold}%</p>}
                  <p>Deployment model changes require a backend restart.</p>
                </div>
              </details>
            </CardContent>
          </Card>
        </TabsContent>
```
```tsx
      {hasChanges && (
        <div role="region" aria-label="Unsaved configuration changes" className="sticky bottom-0 z-20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border rounded-xl bg-background p-4 shadow-lg">
          <div>
            <p className="text-sm font-medium">Unsaved changes</p>
            <p className="text-xs text-muted-foreground">Save applies pending edits across all settings tabs.</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button variant="outline" onClick={handleUndo} disabled={saving || disabled} className="flex-1 sm:flex-none">Discard</Button>
            <Button onClick={handleSave} disabled={saving || disabled} className="flex-1 sm:flex-none">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      )}
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Lines 384–392 (`<Slider>`):** Radix `<Slider>` takes a 1-element array `value={[localConfig.confidenceThreshold]}` and emits `onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}` in integer steps of `1` from `1` to `100`.
  * **Lines 398–405 (`Model information`):** Displays `config.detectionConfidenceThreshold` (`Current YOLO detection cutoff: X%`). As computed on the backend, if `confidenceThreshold` is `80%` and `yolo_confidence_threshold` is `0.50` (`50%`), the YOLO box admission cutoff stays at `50%` so moderate-confidence boxes (`50%–79%`) are still captured and fused, while scans whose final fused confidence falls below `80%` are automatically flagged for Quality Control review. If an admin lowers `confidenceThreshold` below `50%` (e.g., `35%`), `detectionConfidenceThreshold` lowers to `35%` as well.

---

### Phase C & D: Backend Config Update & Effective YOLO Detection Cutoff Calculation

#### Step C1: `PATCH /api/v1/config` & `config_response()` (`config.py`, `common.py`, `configuration.py`)
* **Step Title & Trigger:** `updateConfig` sends `PATCH /api/v1/config` with `{ expected_revision, confidence_threshold }`.
* **Exact File Path & Line Numbers:** `backend/app/schemas/common.py` (Lines 219–250), `backend/app/api/v1/config.py` (Lines 45–72), and `backend/app/services/configuration.py` (Lines 168–194)
* **Complete Uncut Code Block (`backend/app/schemas/common.py`, Lines 219–250):**
```python
class SystemConfigResponse(BaseModel):
    camera_ids: str
    camera_device_ids: list[int]
    confidence_threshold: int
    detection_confidence_threshold: float
    data_retention_enabled: bool
    revision: int
    applied_camera_ids: str | None
    applied_camera_device_ids: list[int]
    applied_revision: int | None
    application_status: str
    application_error: str | None
    restart_required: bool
    retention_days: int
    retention_policy: str
    legacy_conflict: bool


class SystemConfigUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    expected_revision: StrictInt = Field(ge=1)
    camera_ids: str | None = None
    camera_device_ids: list[StrictInt] | None = Field(None, min_length=1, max_length=4)
    confidence_threshold: StrictInt | None = Field(None, ge=1, le=100)
    data_retention_enabled: StrictBool | None = None

    @model_validator(mode='before')
    @classmethod
    def reject_explicit_null(cls, values):
        if isinstance(values, dict) and any(value is None for value in values.values()):
            raise ValueError('Configuration fields cannot be null')
        return values
```
* **Complete Uncut Code Block (`backend/app/services/configuration.py`, Lines 168–194):**
```python
def config_response(config) -> dict:
    camera_ids, device_ids = camera_slot_values(config.camera_slots)
    applied_ids = list(camera_manager._logical_ids)
    physical_ids = list(camera_manager._device_ids) if camera_manager.is_initialized else []
    matches = applied_ids == camera_ids.split(', ') and physical_ids == device_ids
    online = set(camera_manager.online_cameras)
    all_online = matches and all(value in online for value in device_ids)
    error = camera_manager.application_error
    status = 'applied' if all_online else ('partial' if matches and online else 'failed' if matches else 'pending')
    return {
        'camera_ids': camera_ids, 'camera_device_ids': device_ids,
        'confidence_threshold': config.confidence_threshold,
        'detection_confidence_threshold': min(
            config.confidence_threshold, get_settings().yolo_confidence_threshold * 100,
        ),
        'data_retention_enabled': config.data_retention_enabled, 'revision': config.revision,
        'legacy_conflict': config.legacy_conflict,
        'applied_camera_ids': ', '.join(applied_ids) if camera_manager.is_initialized else None,
        'applied_camera_device_ids': physical_ids,
        'applied_revision': config.revision if all_online else None,
        'application_status': status,
        'application_error': error or (None if all_online else 'Saved cameras have not all produced usable frames'),
        'restart_required': False,
        'retention_days': get_settings().max_captures_retention_days,
        'retention_policy': 'orphan_captures_only',
    }
```
* **Line-by-Line Connection & Trace Explanation:**
  * **`common.py` Line 242:** Validates `confidence_threshold: StrictInt | None = Field(None, ge=1, le=100)`. Passing `0`, `101`, a float, or `null` raises HTTP 422.
  * **`configuration.py` Lines 180–182:** Computes `'detection_confidence_threshold': min(config.confidence_threshold, get_settings().yolo_confidence_threshold * 100)`.

---

### Phase E & F: How YOLOv26 & the Saved Confidence Threshold Execute During a Live Scan

#### Step E1: YOLOv26 Configuration (`config.py`), Model Loading & Head Selection (`classification.py`), Pipeline Invocation (`scan_service.py`), and Auto-Flagging (`fusion_engine.py`)
* **Step Title & Trigger:** When an operator triggers a scan (`POST /api/v1/scans/trigger`), `_execute_scan_pipeline` loads the saved `SystemConfig`, computes `review_confidence_threshold` and `confidence_threshold`, runs `banana_classifier.predict()` on the YOLOv26 checkpoint (`banana_yolov26n.pt`), and passes `review_confidence_threshold` to `fusion_engine.fuse()`.
* **Exact File Path & Line Numbers:**
  * `backend/app/config.py` (Lines 79–112)
  * `backend/app/services/classification.py` (Lines 27–44, 87–147, 812–943)
  * `backend/app/services/scan_service.py` (Lines 202–210, 313–321, 373–396)
  * `backend/app/services/fusion_engine.py` (Lines 309–319)
* **Complete Uncut Code Block (`backend/app/config.py`, Lines 79–112):**
```python
    # ── ML Models ────────────────────────────────────────────────────────────
    yolo_model_path: str = "app/ml/weights/banana_yolov26n.pt"
    yolo_confidence_threshold: float = Field(0.50, gt=0, le=1)
    yolo_iou_threshold: float = 0.45
    yolo_top_overlap_refinement: bool = True
    yolo_top_rotation_fallback: bool = True
    yolo_peripheral_background_filter: bool = True
    # YOLO26 checkpoints carry two detection heads. one_to_many_nms runs the head with
    # NMS, which every count audit measured and which the IoU settings above act on;
    # one_to_one is the NMS-free head (IoU settings and test-time augmentation have no
    # effect there); checkpoint keeps whatever the file and Ultralytics version default to.
    yolo_inference_head: Literal["one_to_many_nms", "one_to_one", "checkpoint"] = (
        "one_to_many_nms"
    )
    # Finger-count rules (docs/knowledge/AI Models.md). Each restores the earlier
    # behaviour when set to false.
    yolo_axis_aware_rotation_dedup: bool = True
    yolo_hand_box_split: bool = True
    yolo_ripeness_outlier_filter: bool = True
    # Low-threshold second pass: only fingers inside the hand, and the platter lip is
    # filtered on every side camera (earlier: Rear only).
    yolo_recovery_within_hand: bool = True
    yolo_side_view_lip_filter: bool = True
    # Drop boxes whose centre is mostly not banana colour: dark background or the
    # bluish-grey cut crown (measured on station screenshots, docs/knowledge/AI Models.md).
    yolo_colour_check: bool = True
    yolo_colour_check_max_non_banana: float = Field(0.55, gt=0, le=1)
    # Measurement only: let the recovery pass admit fingers one ripeness stage away.
    yolo_recovery_adjacent_ripeness: bool = False
    top_camera_cultivar_anchor: bool = True
    # Legacy setting retained for compatibility; counts no longer add cross-view sightings.
    multi_camera_finger_fusion: bool = True
    rfr_model_path: str = "app/ml/weights/spoilage_rfr.joblib"
```
* **Complete Uncut Code Block (`backend/app/services/classification.py`, Lines 27–44, 87–147, 812–943):**
```python
VOTE_CONFLICT_THRESHOLD = 0.60
# Calibrated on prepared VALID Top photos; see docs/audits/yolo-dataset-audit-2026-10-16.md.
# A different checkpoint or custom confidence/NMS setting needs its own calibration.
TOP_OVERLAP_CHECKPOINT_SHA256 = (
    "e6f4e6825a642063dfd80e0b4251920e022ce85649d477ebde75a00a852f8b89"
)
TOP_CALIBRATED_CHECKPOINTS: dict[str, int] = {
    TOP_OVERLAP_CHECKPOINT_SHA256: 640,
    "96808fa8ed706909237197e8db2510dccabfaeceed85a4d1ab5182cd28c95f7b": 800,   # banana_yolov26n.pt
    "57ae6c0fe5bfe067f50cd8722823168e630fa99d35bc7905cc6a7010c02aaa41": 1024,  # banana_yolov26s.pt
    "dc171845fe353a2147f6c9219b27fa66df88902eb566eb141670cf4ee5d2b204": 640,   # banana_yolovn26V2.pt
    "9e21668e272bae8ea387d836bbc2b087b5fbb3ae90d375353f49105681e2f478": 640,   # banana_yolovsV2.pt
}
TOP_OVERLAP_CONFIDENCE = 0.50
TOP_OVERLAP_BASE_IOU = 0.45
TOP_OVERLAP_IOU = 0.65
TOP_ROTATION_DEDUP_IOU = 0.40
```
```python
def _detection_head(yolo) -> object | None:
    """The Detect layer of an Ultralytics YOLO object, or None for anything else."""
    inner = getattr(yolo, "model", None)
    layers = getattr(inner, "model", None)
    if inner is None or not hasattr(inner, "end2end") or layers is None:
        return None
    try:
        return layers[-1]
    except (IndexError, KeyError, TypeError):
        return None


def _apply_inference_head(yolo, mode: str) -> str:
    """Fix which YOLO26 head runs, before the first prediction; return the head in use.

    Ultralytics 8.4.40 turns on the NMS-free one-to-one head of a YOLO26 checkpoint unless
    the file stores it off. NMS, `iou` and test-time augmentation are then skipped, and the
    first prediction fuses the one-to-many head away, so the choice cannot wait for a
    predict argument. "checkpoint" leaves the file's own behaviour untouched.
    Returns "one_to_many_nms", "one_to_one" or "unknown" (no Ultralytics detection head).
    """
    head = _detection_head(yolo)
    if head is None:
        return "unknown"
    inner = yolo.model
    if mode == "one_to_many_nms":
        if getattr(head, "cv2", None) is None:
            logger.error(
                "The one-to-many detection head was already fused away; reload the model "
                "to run it with NMS. Continuing with the NMS-free one-to-one head."
            )
        else:
            inner.end2end = False
    elif mode == "one_to_one":
        if getattr(head, "one2one_cv2", None) is None:
            logger.warning(
                "This checkpoint has no one-to-one head; it keeps running with NMS."
            )
        else:
            inner.end2end = True
    return "one_to_one" if bool(getattr(inner, "end2end", False)) else "one_to_many_nms"


def _head_predict_kwargs(head: str, mode: str) -> dict[str, bool]:
    """Repeat the chosen head on every predict call where this Ultralytics accepts it."""
    if mode == "checkpoint" or head == "unknown":
        return {}
    try:
        from ultralytics.cfg import DEFAULT_CFG_DICT
    except Exception:
        return {}
    if "end2end" not in DEFAULT_CFG_DICT:
        return {}
    return {"end2end": head == "one_to_one"}


def _checkpoint_digest(path: str) -> str:
    """Identify the actual checkpoint once at load; filenames are not model identity."""
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
```
```python
    def load(self) -> None:
        """Load YOLO model from disk. Call once at startup."""
        self._checkpoint_sha256 = None
        self._inference_head = "unknown"
        self._head_kwargs = {}
        try:
            from ultralytics import YOLO

            model_path = settings.yolo_model_path
            self._model_name = _model_name_from_path(model_path)
            logger.info(f"Loading {self._model_name} model from {model_path}")
            self._model = YOLO(model_path)
            # Before warmup: the first prediction fixes the head for this model object.
            mode = getattr(settings, "yolo_inference_head", "one_to_many_nms")
            self._inference_head = _apply_inference_head(self._model, mode)
            self._head_kwargs = _head_predict_kwargs(self._inference_head, mode)
            self._loaded = True
            # Preserve the saved resolution of custom checkpoints as well.
            self._image_size = getattr(self._model, "overrides", {}).get("imgsz", 640)
            try:
                self._checkpoint_sha256 = _checkpoint_digest(model_path)
            except OSError:
                logger.warning(
                    "Checkpoint fingerprint unavailable; using standard overlap filtering"
                )
            logger.info(f"{self._model_name} detection head: {self._inference_head}")
            if (
                self._inference_head == "one_to_one"
                and self._checkpoint_sha256 in TOP_CALIBRATED_CHECKPOINTS
            ):
                logger.warning(
                    "Registered checkpoint runs the NMS-free one-to-one head: the calibrated "
                    "IoU settings and the recovery pass's test-time augmentation have no "
                    "effect. Set YOLO_INFERENCE_HEAD=one_to_many_nms to run it as measured."
                )

            # Try to read extra info from the loaded model
            model_type = getattr(self._model, "task", None) or "detect"
            logger.info(
                f"{self._model_name} model loaded successfully "
                f"(task={model_type}, banana classifier)"
            )
        except FileNotFoundError:
            logger.error(
                f"Model file not found at {settings.yolo_model_path}. "
                "Inference will be unavailable until a valid model is provided."
            )
            self._model = None
            self._loaded = False
            self._inference_head = "unknown"
            self._head_kwargs = {}
        except Exception as exc:
            logger.error(f"Failed to load YOLO model: {exc}")
            self._model = None
            self._loaded = False
            self._inference_head = "unknown"
            self._head_kwargs = {}

    def warmup(self) -> None:
        """Run a dummy inference to warm up the model (reduces first-call latency)."""
        if self._model is not None:
            try:
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                self._model.predict(dummy, verbose=False, **self._head_kwargs)
                logger.info(f"{self._model_name} warmup complete")
            except Exception as exc:
                logger.warning(f"{self._model_name} warmup failed: {exc}")

    def predict(
        self, image: np.ndarray, *, confidence_threshold: float,
        camera_label: str | None = None,
        banana_evidence: list[EvidenceBox] | None = None,
        support_margin: float = 0.25,
    ) -> ClassificationResult:
        """
        Run YOLO inference on a single image.
        """
        start = time.time()

        model_name = getattr(self, '_model_name', 'YOLO')
        if self._model is None:
            raise ModelInferenceError(
                model_name,
                "Model not loaded. Ensure a valid .pt model file is available.",
            )

        if not 0 < confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be in (0, 1]")

        head_kwargs = getattr(self, "_head_kwargs", {})
        iou_threshold = settings.yolo_iou_threshold
        expected_imgsz = TOP_CALIBRATED_CHECKPOINTS.get(self._checkpoint_sha256 or "")
        is_calibrated_top = (
            (camera_label or "").strip().casefold() == "top"
            and expected_imgsz is not None
            and self._image_size == expected_imgsz
            and confidence_threshold == TOP_OVERLAP_CONFIDENCE
            and iou_threshold == TOP_OVERLAP_BASE_IOU
        )
        if settings.yolo_top_overlap_refinement and is_calibrated_top:
            iou_threshold = TOP_OVERLAP_IOU

        try:
            results = self._model.predict(
                image,
                conf=confidence_threshold,
                iou=iou_threshold,
                # Ultralytics retains predictor arguments between calls. Set these
                # explicitly so a Top call cannot alter subsequent camera views.
                imgsz=self._image_size,
                augment=False,
                agnostic_nms=False,
                max_det=300,
                verbose=False,
                **head_kwargs,
            )
        except Exception as exc:
            raise ModelInferenceError(model_name, str(exc))
```
* **Complete Uncut Code Block (`backend/app/services/scan_service.py`, Lines 203–210, 313–317, 373–396):**
```python
        config = await get_config(db)
        review_confidence_threshold = config.confidence_threshold / 100.0
        # Retain moderate-confidence boxes before fusion. The stricter saved
        # threshold governs review, rather than discarding camera evidence.
        confidence_threshold = min(
            review_confidence_threshold, get_settings().yolo_confidence_threshold,
        )
        expected_camera_count = len(config.camera_slots)
```
```python
            result = await run_blocking(
                banana_classifier.predict, cap.frame,
                confidence_threshold=confidence_threshold, camera_label=cap.camera_label,
                **gate_arguments,
            )
```
```python
        fused = fusion_engine.fuse(
            classification_results, expected_camera_count=expected_camera_count,
            review_confidence_threshold=review_confidence_threshold,
        )
```
```python
        auto_flagged = bool(fused.auto_flagged)
        flag_reason = (
            getattr(fused, "flag_reason", None) or "Confidence is below the review threshold"
        ) if auto_flagged else None
        flagged_text = f"flagged for review: {flag_reason}"
```
* **Complete Uncut Code Block (`backend/app/services/fusion_engine.py`, Lines 309–319):**
```python
        # The one auto-flag rule: confidence below the saved review threshold. A result
        # without a label has confidence 0, so it is below any threshold.
        # The saved threshold is an integer percent passed as a fraction; rounding undoes
        # the float error of that round trip (55 / 100 * 100 is 55.00000000000001), so a
        # confidence equal to the threshold is never flagged.
        threshold_percent = round(review_confidence_threshold * 100, 6)
        auto_flagged = final_confidence < threshold_percent
        flag_reason = (
            _below_threshold(final_confidence, threshold_percent) if auto_flagged else None
        )
```
* **Line-by-Line Connection & Trace Explanation:**
  * **Why YOLOv26 Dual-Head Configuration Matters (`classification.py` Lines 99–140):** Ultralytics YOLO26 checkpoints (`banana_yolov26n.pt` / `banana_yolov26s.pt`) contain two detection heads: `one_to_one` (NMS-free, `inner.end2end = True`) and `one_to_many_nms` (`inner.end2end = False`). BananaVision sets `yolo_inference_head = "one_to_many_nms"` before warmup so that calibrated Non-Maximum Suppression (`iou_threshold = 0.45` on side views, `TOP_OVERLAP_IOU = 0.65` on Top view) and Test-Time Augmentation (`augment=True` on occluded finger recovery pass) work accurately.
  * **Two-Tier Threshold Architecture (`scan_service.py` Lines 203–209 & `fusion_engine.py` Lines 314–318):**
    1. `review_confidence_threshold = config.confidence_threshold / 100.0` (e.g., `0.80` for `80%`).
    2. `confidence_threshold = min(review_confidence_threshold, get_settings().yolo_confidence_threshold)` (e.g., `min(0.80, 0.50) = 0.50`).
    3. `banana_classifier.predict()` runs with `conf=confidence_threshold` (`0.50`), so boxes between `50%` and `79%` are not thrown away before multi-camera fusion.
    4. `fusion_engine.fuse()` compares `final_confidence < threshold_percent` (`80%`). If `final_confidence` is `< 80%`, `auto_flagged = True` with `flag_reason = "Confidence X% is below the 80% threshold"`, automatically sending the scan to Quality Control and creating a `"scan_flagged"` notification.

---

## 3. Skill Test & Defense Cheat Sheet

### Trace Reference Table

| Item / Layer | Exact Value / Location |
| :--- | :--- |
| **UI Tab & Slider** | `<TabsContent value="ai">` in `frontend/src/pages/admin/SystemConfig.tsx` (Lines 372–408), range `1` to `100` |
| **DB Column** | `system_config.confidence_threshold` (`Integer`, default `80`) |
| **YOLOv26 Weights Path** | `settings.yolo_model_path = "app/ml/weights/banana_yolov26n.pt"` (`backend/app/config.py` Line 80) |
| **YOLOv26 Detection Head** | `settings.yolo_inference_head = "one_to_many_nms"` (`inner.end2end = False` set in `_apply_inference_head`) |
| **Box Admission Cutoff** | `confidence_threshold = min(config.confidence_threshold / 100.0, settings.yolo_confidence_threshold)` (`scan_service.py` Line 207) |
| **Auto-Flag Condition** | `auto_flagged = final_confidence < round(review_confidence_threshold * 100, 6)` (`fusion_engine.py` Line 315) |

---

### Live-Coding Drill Scenarios

#### Drill Scenario 1: Add Quick-Preset Buttons (`70%`, `80%`, `90%`) Below the Review Confidence Threshold Slider
* **Examiner Prompt:** *"In the Detection Review tab of `SystemConfig.tsx`, add three quick-select preset buttons (`70% - Lenient`, `80% - Recommended`, `90% - Strict`) below the slider that update `localConfig.confidenceThreshold`."*
* **File to Edit:** `frontend/src/pages/admin/SystemConfig.tsx` (Lines 384–397)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 384–397):**
```tsx
                <Slider aria-labelledby="review-confidence-label"
                  value={[localConfig.confidenceThreshold]} 
                  onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}
                  min={1}
                  disabled={saving || disabled}
                  max={100} 
                  step={1} 
                  className="w-full"
                />
                <p className="text-xs text-muted-foreground">
                  Results below {localConfig.confidenceThreshold}% are flagged for review.
                  <span className="block mt-1">Applies to the next scan after saving.</span>
                </p>
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Lines 384–413):**
```tsx
                <Slider aria-labelledby="review-confidence-label"
                  value={[localConfig.confidenceThreshold]} 
                  onValueChange={(v) => setLocalConfig({...localConfig, confidenceThreshold: v[0]})}
                  min={1}
                  disabled={saving || disabled}
                  max={100} 
                  step={1} 
                  className="w-full"
                />
                <div className="flex flex-wrap gap-2 pt-1">
                  {[
                    { label: "70% (Lenient)", value: 70 },
                    { label: "80% (Recommended)", value: 80 },
                    { label: "90% (Strict)", value: 90 },
                  ].map((preset) => (
                    <Button
                      key={preset.value}
                      type="button"
                      size="xs"
                      variant={localConfig.confidenceThreshold === preset.value ? "default" : "outline"}
                      disabled={saving || disabled}
                      onClick={() => setLocalConfig({ ...localConfig, confidenceThreshold: preset.value })}
                    >
                      {preset.label}
                    </Button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Results below {localConfig.confidenceThreshold}% are flagged for review.
                  <span className="block mt-1">Applies to the next scan after saving.</span>
                </p>
```

---

#### Drill Scenario 2: Restrict the Minimum Allowed Review Confidence Threshold to `50%` on Both Frontend and Backend
* **Examiner Prompt:** *"Prevent administrators from setting a Review Confidence Threshold lower than `50%` by updating the `<Slider min={50}>` in `SystemConfig.tsx` and `Field(None, ge=50, le=100)` in `SystemConfigUpdate`."*
* **Files to Edit:**
  1. `frontend/src/pages/admin/SystemConfig.tsx` (Line 387)
  2. `backend/app/schemas/common.py` (Line 242)
* **Before (`frontend/src/pages/admin/SystemConfig.tsx`, Line 387):**
```tsx
                  min={1}
```
* **After (`frontend/src/pages/admin/SystemConfig.tsx`, Line 387):**
```tsx
                  min={50}
```
* **Before (`backend/app/schemas/common.py`, Line 242):**
```python
    confidence_threshold: StrictInt | None = Field(None, ge=1, le=100)
```
* **After (`backend/app/schemas/common.py`, Line 242):**
```python
    confidence_threshold: StrictInt | None = Field(None, ge=50, le=100)
```

---

#### Drill Scenario 3: Switch the YOLOv26 Checkpoint from Nano (`banana_yolov26n.pt`) to Small (`banana_yolov26s.pt`)
* **Examiner Prompt:** *"Explain where the YOLOv26 weights path and calibrated image size are configured if an examiner asks to switch from the Nano model (`banana_yolov26n.pt`, `800px`) to the Small model (`banana_yolov26s.pt`, `1024px`)."*
* **File to Edit:** `backend/app/config.py` (Line 80) (or `YOLO_MODEL_PATH` in `backend/.env`)
* **Before (`backend/app/config.py`, Line 80):**
```python
    yolo_model_path: str = "app/ml/weights/banana_yolov26n.pt"
```
* **After (`backend/app/config.py`, Line 80):**
```python
    yolo_model_path: str = "app/ml/weights/banana_yolov26s.pt"
```
*(In `backend/app/services/classification.py` Line 36, `TOP_CALIBRATED_CHECKPOINTS` already contains `"57ae6c0fe5bfe067f50cd8722823168e630fa99d35bc7905cc6a7010c02aaa41": 1024` for `banana_yolov26s.pt`!)*
