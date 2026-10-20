-- ============================================================
-- BananaVision: Feature Engineering & Batch Lifecycle Migration
-- ============================================================
-- Adds chemical feature engineering columns to scan_classification
-- and batch lifecycle / treatment fields to delivery_intake.
--
-- Historical manual script: includes a calculated historical-data backfill below.
-- Do not use it for current setup or seeding. The maintained migration is
-- backend/migrations/versions/0002_feature_engineering.py, which preserves missing
-- historical VPD as NULL. Use python -m app.core.migrations for current upgrades.
-- ============================================================

-- ── 1. Add treatment enum type ──────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE treatmentenum AS ENUM ('Natural', 'Ethephon');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ── 2. Extend delivery_intake with batch lifecycle fields ───────────────────

ALTER TABLE delivery_intake
    ADD COLUMN IF NOT EXISTS treatment   treatmentenum DEFAULT 'Natural',
    ADD COLUMN IF NOT EXISTS harvested_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS treated_at  timestamp with time zone,
    ADD COLUMN IF NOT EXISTS spoiled_at  timestamp with time zone;

-- ── 3. Extend scan_classification with engineered chemical features ─────────

ALTER TABLE scan_classification
    ADD COLUMN IF NOT EXISTS dew_point   decimal(6,3),
    ADD COLUMN IF NOT EXISTS vpd         decimal(6,3),
    ADD COLUMN IF NOT EXISTS heat_index  decimal(5,2),
    ADD COLUMN IF NOT EXISTS treatment   treatmentenum;

-- ── 4. Backfill existing scan_classification rows ───────────────────────────
-- Compute dew_point, vpd, heat_index from stored temperature/humidity
-- using the same formulas as feature_engineering.py

UPDATE scan_classification
SET
    dew_point = CASE
        WHEN humidity IS NOT NULL AND humidity > 0 AND temperature IS NOT NULL
        THEN ROUND(
            (237.7 * (((17.27 * temperature) / (237.7 + temperature)) + LN(humidity / 100.0)))
            / (17.27 - (((17.27 * temperature) / (237.7 + temperature)) + LN(humidity / 100.0)))
        , 3)
        ELSE NULL
    END,
    vpd = CASE
        WHEN humidity IS NOT NULL AND temperature IS NOT NULL
        THEN ROUND(
            (0.61078 * EXP((17.27 * temperature) / (temperature + 237.3)))
            - ((humidity / 100.0) * 0.61078 * EXP((17.27 * temperature) / (temperature + 237.3)))
        , 3)
        ELSE NULL
    END,
    heat_index = CASE
        WHEN humidity IS NOT NULL AND temperature IS NOT NULL
        THEN ROUND(
            ((0.5 * (((temperature * 9.0/5.0) + 32) + 61.0
                + (((temperature * 9.0/5.0) + 32 - 68.0) * 1.2)
                + (humidity * 0.094))) - 32) * 5.0/9.0
        , 2)
        ELSE NULL
    END
WHERE temperature IS NOT NULL AND humidity IS NOT NULL
  AND dew_point IS NULL;

-- ============================================================
-- Migration complete.
-- ============================================================
