# Development Decisions

Documented architectural, technical, and operational decisions in BananaVision.

## 2026-10-16: Live Detection and Result Review

- YOLO retains candidates at `min(YOLO_CONFIDENCE_THRESHOLD, saved confidence_threshold / 100)`. The model setting defaults to 0.50; the saved review setting defaults to 85%. Lower saved settings remain supported.
- Fusion uses the saved setting for confidence review, alongside camera support and conflict checks. A confident box score does not establish agreement across camera views.
- Both thresholds are snapshotted before processing the camera views. Original box confidence scores are retained.
- The configuration response reports the effective saved detection cutoff as read-only `detection_confidence_threshold` in percent. The settings slider controls review; its helper identifies the **current** saved detection cutoff.
- Kiosk scan results expose the existing review flag in the result title. No database schema or model weight change is required.
- Finger count currently means the maximum per-camera YOLO box count, assuming one detection per finger. There is no matching of physical fingers across views. Do not sum view counts or infer a correction multiplier from a reported total; validate per-view detection recall and whole-bunch count error separately. Large overlapping rectangles alone do not establish incorrect training annotations.
- See [[Resolved Bugs]] for the filtering and label-pair regressions. Real-world accuracy still requires labeled offline fixtures; synthetic tests establish pipeline behavior only.

## 2026-10-16: Loading States & Data Consistency

### 1. Distinction Between Initial Load, Action, and Background Refresh
- **Decision**: Initial data loads for structured views (KPIs, tables, details) must render skeleton placeholders to match final layouts. Continuous actions (calibration, printing, backup, intake) display spinners/badges while disabling triggers. Background refreshes preserve the previous valid snapshot rather than blanking the screen.
- **Rationale**: Prevents visual flicker, prevents premature "0 records found" flashes, and provides smooth user experience on mobile and kiosk interfaces.

### 2. Snapshot Retention on Failed Refresh
- **Decision**: When a background refresh or polling fails (network dropout or temporary server unavailability), the frontend retains the previous valid data snapshot, displaying an inline `<Alert>` with explicit Retry rather than replacing the entire view with an error screen or zero counts.
- **Rationale**: Operators and supervisors can still reference active scan details and inventory while attempting recovery.

### 3. Review Queue Scope
- **Decision**: Review links must not pre-filter by `status=Flagged`. They must navigate using `attention=review` alone.
- **Rationale**: Low-confidence or unclassified scans require manual inspection even if not yet formally marked as "Flagged". Filtering by `status=Flagged` inadvertently hid scans that needed review.

## 2026-10-17: Analytics & AI Metric Isolation

### AI Model Confidence Isolation from Mutable Scans
- **Decision**: In `backend/app/services/analytics.py:85-92`, confidence metrics strictly query `ScanOriginalAiResult` (via outer join) rather than mutable `scans` table columns. If a scan was overridden by an operator and lacks an original AI prediction record, it evaluates to `None` and is excluded from model confidence metrics.
- **Rationale**: Prevents human manual overrides or quality control corrections from contaminating AI model metrics. Analytics reflects genuine machine-learning model performance.
- **Role Isolation**: Scoped strictly by role: Operators are isolated to their own scans (`OperatorProfile.account_id == user.id`), whereas Admins view station-wide aggregates.
- **Zero-Count Safety**: Guarded denominators prevent division-by-zero across all metrics when `total_scans == 0`, presenting `"―"` gracefully without NaN or errors.
- **Operator Performance Metrics**: Surfaced backend `flag_rate` (as `Flag Rate (%)`) and `overridden_scans` (as `QC Overrides`) columns for Administrator users in the Operator Performance Table (`Analytics.tsx`), providing supervisory visibility into operator defect flags and manual correction counts.

## 2026-10-17: Scan Classification Overrides & Spoilage Recalculation

### Strict Finger Count Validation & Environmental Spoilage
- **Decision**: In `backend/app/schemas/scan.py`, `ScanOverrideRequest.finger_count` enforces `Field(default=None, ge=1)` with a Pydantic field validator rejecting `< 1` or `null`. In `QualityControl.tsx` and `ScanDetail.tsx`, form submission is blocked and the Save Changes button disabled when `fingerCount` is empty or `< 1`. Changing cultivar or ripeness passes ambient `temperature` and `humidity` to `getSpoilageDays()`.
- **Rationale**: Eliminates the previous silent fallback `parseInt(...) || 0`, which caused non-numeric or cleared inputs to persist 0-finger bunches and pollute downstream batch statistics. Dynamically recalculating shelf-life estimates with environmental factors ensures operational spoilage predictions remain accurate after quality control overrides.

