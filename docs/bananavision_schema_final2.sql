-- ============================================================
-- BANANAVISION DATABASE SCHEMA (FINAL / ALIGNED)
-- ============================================================
-- This schema represents the final alignment between the
-- designed data dictionary and the actual frontend models
-- found in src/types/index.ts and src/context/AppContext.tsx.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- DROP EXISTING TABLES
-- ============================================================

DROP TABLE IF EXISTS APP_NOTIFICATION CASCADE;
DROP TABLE IF EXISTS ACTIVITY_LOG CASCADE;
DROP TABLE IF EXISTS SCAN_NOTE CASCADE;
DROP TABLE IF EXISTS SCAN_CLASSIFICATION CASCADE;
DROP TABLE IF EXISTS SCAN_ORIGINAL_AI_RESULT CASCADE;
DROP TABLE IF EXISTS SCAN_STATUS_LOG CASCADE;
DROP TABLE IF EXISTS SCAN CASCADE;
DROP TABLE IF EXISTS DELIVERY_INTAKE CASCADE;
DROP TABLE IF EXISTS SUPPLIER CASCADE;
DROP TABLE IF EXISTS DEVICE CASCADE;
DROP TABLE IF EXISTS SYSTEM_CONFIG CASCADE;
DROP TABLE IF EXISTS OPERATOR_PROFILE CASCADE;
DROP TABLE IF EXISTS ADMIN_PROFILE CASCADE;
DROP TABLE IF EXISTS USER_ACCOUNT CASCADE;
DROP TABLE IF EXISTS USER_ROLE CASCADE;

-- ============================================================
-- CORE USER & ROLES (Aligned with User type + Profiles for Expansion)
-- ============================================================

CREATE TABLE USER_ROLE (
    UR_ID               SERIAL PRIMARY KEY,
    UR_NAME             VARCHAR(30) UNIQUE NOT NULL,
    UR_DESCRIPTION      VARCHAR(255)
);

CREATE TABLE USER_ACCOUNT (
    UA_ID                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    UA_USERNAME                 VARCHAR(50) UNIQUE NOT NULL,
    UA_FULL_NAME                VARCHAR(100) NOT NULL,
    UR_ID                       INT NOT NULL REFERENCES USER_ROLE(UR_ID) ON DELETE RESTRICT,
    UA_STATUS                   VARCHAR(20) DEFAULT 'Active' CHECK (UA_STATUS IN ('Active', 'Inactive')),
    UA_AVATAR_URL               TEXT,
    UA_PASSWORD_HASH            VARCHAR(255) NOT NULL,
    UA_REQUIRES_PWD_CHANGE      BOOLEAN DEFAULT FALSE,
    UA_PWD_SETUP_REASON         VARCHAR(50) CHECK (UA_PWD_SETUP_REASON IN ('new_account', 'password_reset')),
    UA_LAST_ACTIVE              TIMESTAMP,
    UA_CREATED_AT               TIMESTAMP NOT NULL DEFAULT NOW(),
    UA_UPDATED_AT               TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Administrator Profile Extension
CREATE TABLE ADMIN_PROFILE (
    AP_ID               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    AP_ACCOUNT_ID       UUID NOT NULL UNIQUE REFERENCES USER_ACCOUNT(UA_ID) ON DELETE CASCADE,
    AP_CREATED_AT       TIMESTAMP NOT NULL DEFAULT NOW(),
    AP_UPDATED_AT       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Operator Profile Extension (Contains Operator-specific properties like PINs and scan counters)
CREATE TABLE OPERATOR_PROFILE (
    OP_ID                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    OP_ACCOUNT_ID           UUID NOT NULL UNIQUE REFERENCES USER_ACCOUNT(UA_ID) ON DELETE CASCADE,
    OP_PIN_HASH             VARCHAR(255),
    OP_REQUIRES_PIN_CHANGE  BOOLEAN DEFAULT FALSE,
    OP_PIN_SETUP_REASON     VARCHAR(50) CHECK (OP_PIN_SETUP_REASON IN ('new_account', 'pin_reset')),
    OP_TOTAL_SCANS          INT DEFAULT 0,
    OP_FLAGGED_SCANS        INT DEFAULT 0,
    OP_CREATED_AT           TIMESTAMP NOT NULL DEFAULT NOW(),
    OP_UPDATED_AT           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SYSTEM CONFIGURATION
-- ============================================================

CREATE TABLE SYSTEM_CONFIG (
    SC_ID                   SERIAL PRIMARY KEY,
    SC_CAMERA_IDS           TEXT NOT NULL,         -- Aligned with config { cameraIds: string }
    SC_CONFIDENCE_THRESHOLD INT NOT NULL,          -- Aligned with config { confidenceThreshold: number }
    SC_UPDATED_AT           TIMESTAMP NOT NULL DEFAULT NOW(),
    SC_UPT_BY_ADMIN         UUID REFERENCES ADMIN_PROFILE(AP_ID) ON DELETE SET NULL
);

-- ============================================================
-- DEVICE MANAGEMENT (Aligned with Device type)
-- ============================================================

CREATE TABLE DEVICE (
    DEV_ID              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    DEV_CAMERA_ID       VARCHAR(50) UNIQUE NOT NULL,
    DEV_LABEL           VARCHAR(100) NOT NULL,
    DEV_STATUS          VARCHAR(20) DEFAULT 'Offline' CHECK (DEV_STATUS IN ('Online', 'Offline')),
    DEV_RESOLUTION      VARCHAR(20) DEFAULT '1920x1080',
    DEV_LAST_SEEN       TIMESTAMP,
    DEV_CREATED_AT      TIMESTAMP NOT NULL DEFAULT NOW(),
    DEV_UPDATED_AT      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SUPPLIER & INTAKE (Aligned with Supplier & DailyIntake types)
-- ============================================================

CREATE TABLE SUPPLIER (
    SUP_ID              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    SUP_NAME            VARCHAR(100) NOT NULL,
    SUP_CONTACT_PERSON  VARCHAR(100),
    SUP_CONTACT_PHONE   VARCHAR(20),
    SUP_STATUS          VARCHAR(20) DEFAULT 'Active' CHECK (SUP_STATUS IN ('Active', 'Inactive')),
    SUP_DATE_ADDED      TIMESTAMP NOT NULL DEFAULT NOW(),
    SUP_UPDATED_AT      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE DELIVERY_INTAKE (
    DI_ID               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    DI_SOURCE           VARCHAR(100) NOT NULL,
    DI_DATE             DATE NOT NULL,
    DI_STATUS           VARCHAR(20) DEFAULT 'Active' CHECK (DI_STATUS IN ('Active', 'Depleted')),
    DI_CREATED_AT       TIMESTAMP NOT NULL DEFAULT NOW(),
    DI_UPDATED_AT       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SCAN TABLES (Aligned with ScanResult & ScanNote types)
-- ============================================================

CREATE TABLE SCAN (
    SC_ID                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    SC_DATE_TIME            TIMESTAMP NOT NULL DEFAULT NOW(),
    SC_FLAGGED              BOOLEAN DEFAULT FALSE,
    SC_IS_OVERRIDDEN        BOOLEAN DEFAULT FALSE,
    SC_OPERATOR_ID          UUID NOT NULL REFERENCES OPERATOR_PROFILE(OP_ID) ON DELETE RESTRICT,
    SC_INTAKE_ID            UUID REFERENCES DELIVERY_INTAKE(DI_ID) ON DELETE SET NULL,
    SC_SOURCE_TEXT          VARCHAR(100), -- Explicit denormalized source for quick lookup
    SC_UPDATED_AT           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE SCAN_CLASSIFICATION (
    SCLS_ID             SERIAL PRIMARY KEY,
    SCLS_SCAN_ID        UUID UNIQUE NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SCLS_CULTIVAR       VARCHAR(20) NOT NULL CHECK (SCLS_CULTIVAR IN ('Lakatan', 'Latundan', 'Saba')),
    SCLS_RIPENESS       VARCHAR(20) NOT NULL CHECK (SCLS_RIPENESS IN ('Unripe', 'Ripe', 'Overripe', 'Rotten')),
    SCLS_CONFIDENCE     DECIMAL(5,2) NOT NULL CHECK (SCLS_CONFIDENCE >= 0 AND SCLS_CONFIDENCE <= 100),
    SCLS_TEMPERATURE    DECIMAL(5,2), -- Added from frontend ScanResult
    SCLS_HUMIDITY       DECIMAL(5,2), -- Added from frontend ScanResult
    SCLS_SPOILAGE_DAYS  VARCHAR(20) NOT NULL,
    SCLS_FINGER_COUNT   INT NOT NULL,
    SCLS_THUMBNAIL_URL  VARCHAR(500)
);

CREATE TABLE SCAN_STATUS_LOG (
    SSLG_ID                 SERIAL PRIMARY KEY,
    SSLG_SCAN_ID            UUID NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SSLG_INVENTORY_STATUS   VARCHAR(30) NOT NULL CHECK (SSLG_INVENTORY_STATUS IN ('In Stock', 'Sold', 'For Processing', 'Spoiled')),
    SSLG_UPDATED_AT         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Represents the `originalAiResult` property structure
CREATE TABLE SCAN_ORIGINAL_AI_RESULT (
    SOAR_ID             SERIAL PRIMARY KEY,
    SOAR_SCAN_ID        UUID UNIQUE NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SOAR_CULTIVAR       VARCHAR(20) NOT NULL CHECK (SOAR_CULTIVAR IN ('Lakatan', 'Latundan', 'Saba')),
    SOAR_RIPENESS       VARCHAR(20) NOT NULL CHECK (SOAR_RIPENESS IN ('Unripe', 'Ripe', 'Overripe', 'Rotten')),
    SOAR_CONFIDENCE     DECIMAL(5,2) NOT NULL,
    SOAR_FINGER_COUNT   INT NOT NULL,
    SOAR_CREATED_AT     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- IoT CAMERA INFRASTRUCTURE (4 Camera Support)
-- ============================================================

CREATE TABLE SCAN_DETECTION (
    SD_ID                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    SD_SCAN_ID              UUID NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SD_CAMERA_ID            VARCHAR(20) NOT NULL,
    SD_CAMERA_LABEL         VARCHAR(30) NOT NULL,
    SD_DETECTED_CULTIVAR    VARCHAR(20),
    SD_DETECTED_RIPENESS    VARCHAR(20),
    SD_CONFIDENCE           DECIMAL(5,2),
    SD_FINGER_COUNT         INT DEFAULT 0,
    SD_BOUNDING_BOXES       JSONB,
    SD_INFERENCE_TIME_MS    DECIMAL(8,2),
    SD_CAPTURED_AT          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE SCAN_IMAGE (
    SI_ID               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    SI_SCAN_ID          UUID NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SI_CAMERA_ID        VARCHAR(20) NOT NULL,
    SI_FILE_PATH        VARCHAR(500) NOT NULL,
    SI_WIDTH            INT,
    SI_HEIGHT           INT,
    SI_FILE_SIZE_BYTES  INT,
    SI_CAPTURED_AT      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Aligned with the ScanNote interface in AppContext.tsx
CREATE TABLE SCAN_NOTE (
    SCNT_ID                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    SCNT_SCAN_ID                UUID NOT NULL REFERENCES SCAN(SC_ID) ON DELETE CASCADE,
    SCNT_TEXT                   TEXT NOT NULL,
    SCNT_AUTHOR_NAME            VARCHAR(100) NOT NULL, -- Storing author explicitly based on interface
    SCNT_TIMESTAMP              TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SYSTEM LOGS & NOTIFICATIONS (Aligned with ActivityLog & AppNotification types)
-- ============================================================

CREATE TABLE ACTIVITY_LOG (
    AL_ID               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    AL_TIMESTAMP        TIMESTAMP NOT NULL DEFAULT NOW(),
    AL_USER_ID          UUID REFERENCES USER_ACCOUNT(UA_ID) ON DELETE SET NULL,
    AL_ACTION           VARCHAR(50) NOT NULL CHECK (AL_ACTION IN (
                            'login', 'logout', 'scan_created', 'scan_edited', 
                            'user_created', 'user_updated', 'config_changed', 'scan_flagged', 
                            'supplier_created', 'supplier_updated', 
                            'intake_created', 'intake_edited',  
                            'intake_status_changed'
                        )),
    AL_DETAILS          TEXT NOT NULL,
    AL_IP_ADDRESS       VARCHAR(45)
);

CREATE TABLE APP_NOTIFICATION (
    NOTIF_ID            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    NOTIF_TYPE          VARCHAR(30) NOT NULL CHECK (NOTIF_TYPE IN ('scan_complete', 'scan_flagged', 'intake_update', 'system_alert', 'quality_warning')),
    NOTIF_TITLE         VARCHAR(200) NOT NULL,
    NOTIF_MESSAGE       TEXT NOT NULL,
    NOTIF_TIMESTAMP     TIMESTAMP NOT NULL DEFAULT NOW(),
    NOTIF_IS_READ       BOOLEAN DEFAULT FALSE,
    NOTIF_HREF          VARCHAR(200),
    NOTIF_USER_ID       UUID REFERENCES USER_ACCOUNT(UA_ID) ON DELETE CASCADE
);

-- ============================================================
