# Development Decisions

Documented architectural, technical, and operational decisions in BananaVision.

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
