# BananaVision Database Tables

This document describes all tables defined in `bananavision_schema_final2.sql`.

Each table lists primary-key columns first, regular columns next, and foreign-key columns last to match the ERD layout. The `FK Referenced Table` column identifies the related primary key.

## USER_ROLE

| Column      | Data Type    | Null | Default | PK or FK | FK Referenced Table |
| ----------- | ------------ | ---- | ------- | -------- | ------------------- |
| ID          | SERIAL       | No   |         | PK       |                     |
| NAME        | VARCHAR(30)  | No   |         |          |                     |
| DESCRIPTION | VARCHAR(255) | Yes  |         |          |                     |

**Constraints:** `NAME` must be unique.

## USER_ACCOUNT

| Column                   | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ------------------------ | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID                       | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| USERNAME                 | VARCHAR(50)              | No   |                     |          |                     |
| FULL_NAME                | VARCHAR(100)             | No   |                     |          |                     |
| STATUS                   | VARCHAR(20)              | Yes  | `'Active'`          |          |                     |
| AVATAR_URL               | TEXT                     | Yes  |                     |          |                     |
| PASSWORD_HASH            | VARCHAR(255)             | No   |                     |          |                     |
| REQUIRES_PASSWORD_CHANGE | BOOLEAN                  | Yes  | `false`             |          |                     |
| PASSWORD_SETUP_REASON    | VARCHAR(50)              | Yes  |                     |          |                     |
| LAST_ACTIVE              | TIMESTAMP WITH TIME ZONE | Yes  |                     |          |                     |
| CREATED_AT               | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT               | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| ROLE_ID                  | INT                      | No   |                     | FK       | USER_ROLE(ID)       |

**Constraints:** `USERNAME` must be unique. `STATUS` accepts `Active` or `Inactive`. `PASSWORD_SETUP_REASON` accepts `new_account` or `password_reset`.

## ADMIN_PROFILE

| Column     | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ---------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ACCOUNT_ID | UUID                     | No   |                     | PK, FK   | USER_ACCOUNT(ID)    |
| ID         | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| CREATED_AT | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |

**Constraints:** `ACCOUNT_ID` and `ID` form the composite primary key. `ACCOUNT_ID` must be unique. Deleting the account cascades to this profile.

## OPERATOR_PROFILE

| Column              | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ------------------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ACCOUNT_ID          | UUID                     | No   |                     | PK, FK   | USER_ACCOUNT(ID)    |
| ID                  | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| PIN_HASH            | VARCHAR(255)             | Yes  |                     |          |                     |
| REQUIRES_PIN_CHANGE | BOOLEAN                  | Yes  | `false`             |          |                     |
| PIN_SETUP_REASON    | VARCHAR(50)              | Yes  |                     |          |                     |
| TOTAL_SCANS         | INT                      | Yes  | `0`                 |          |                     |
| FLAGGED_SCANS       | INT                      | Yes  | `0`                 |          |                     |
| CREATED_AT          | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT          | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |

**Constraints:** `ACCOUNT_ID` and `ID` form the composite primary key. `ACCOUNT_ID` must be unique. `PIN_SETUP_REASON` accepts `new_account` or `pin_reset`. Deleting the account cascades to this profile.

## DEVICE

| Column     | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ---------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID         | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| CAMERA_ID  | VARCHAR(50)              | No   |                     |          |                     |
| LABEL      | VARCHAR(100)             | No   |                     |          |                     |
| STATUS     | VARCHAR(20)              | Yes  | `'Offline'`         |          |                     |
| RESOLUTION | VARCHAR(20)              | Yes  | `'1920x1080'`       |          |                     |
| LAST_SEEN  | TIMESTAMP WITH TIME ZONE | Yes  |                     |          |                     |
| CREATED_AT | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |

**Constraints:** `CAMERA_ID` must be unique. `STATUS` accepts `Online` or `Offline`.

## SYSTEM_CONFIG

| Column                 | Data Type                | Null | Default | PK or FK | FK Referenced Table |
| ---------------------- | ------------------------ | ---- | ------- | -------- | ------------------- |
| ID                     | SERIAL                   | No   |         | PK       |                     |
| CAMERA_IDS             | TEXT                     | No   |         |          |                     |
| CONFIDENCE_THRESHOLD   | INT                      | No   |         |          |                     |
| DATA_RETENTION_ENABLED | BOOLEAN                  | No   | `true`  |          |                     |
| UPDATED_AT             | TIMESTAMP WITH TIME ZONE | No   | `now()` |          |                     |
| UPDATED_BY_ADMIN       | UUID                     | Yes  |         | FK       | ADMIN_PROFILE(ID)   |

**Constraints:** Deleting the referenced administrator sets `UPDATED_BY_ADMIN` to `NULL`.

## SENSOR_READING

| Column      | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ----------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID          | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| TEMPERATURE | FLOAT                    | No   |                     |          |                     |
| HUMIDITY    | FLOAT                    | No   |                     |          |                     |
| RECORDED_AT | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| SOURCE      | VARCHAR(50)              | Yes  | `'DHT22'`           |          |                     |

## SUPPLIER

| Column         | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| -------------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID             | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| NAME           | VARCHAR(100)             | No   |                     |          |                     |
| CONTACT_PERSON | VARCHAR(100)             | Yes  |                     |          |                     |
| CONTACT_PHONE  | VARCHAR(20)              | Yes  |                     |          |                     |
| STATUS         | VARCHAR(20)              | Yes  | `'Active'`          |          |                     |
| DATE_ADDED     | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT     | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |

**Constraints:** `STATUS` accepts `Active` or `Inactive`.

## DELIVERY_INTAKE

| Column       | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ------------ | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID           | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| SOURCE       | VARCHAR(100)             | No   |                     |          |                     |
| BATCH_NUMBER | VARCHAR(50)              | Yes  |                     |          |                     |
| QR_CODE      | TEXT                     | Yes  |                     |          |                     |
| INTAKE_DATE  | DATE                     | No   |                     |          |                     |
| STATUS       | VARCHAR(20)              | Yes  | `'Active'`          |          |                     |
| TREATMENT    | VARCHAR(20)              | Yes  | `'Natural'`         |          |                     |
| HARVESTED_AT | TIMESTAMP WITH TIME ZONE | Yes  |                     |          |                     |
| TREATED_AT   | TIMESTAMP WITH TIME ZONE | Yes  |                     |          |                     |
| SPOILED_AT   | TIMESTAMP WITH TIME ZONE | Yes  |                     |          |                     |
| CREATED_AT   | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| UPDATED_AT   | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| SUPPLIER_ID  | UUID                     | Yes  |                     | FK       | SUPPLIER(ID)        |

**Constraints:** `STATUS` accepts `Active` or `Depleted`. `TREATMENT` accepts `Natural` or `Ethephon`. Deleting a supplier is restricted.

## SCAN

| Column        | Data Type                | Null | Default             | PK or FK | FK Referenced Table  |
| ------------- | ------------------------ | ---- | ------------------- | -------- | -------------------- |
| ID            | UUID                     | No   | `gen_random_uuid()` | PK       |                      |
| DATE_TIME     | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                      |
| FLAGGED       | BOOLEAN                  | Yes  | `false`             |          |                      |
| IS_OVERRIDDEN | BOOLEAN                  | Yes  | `false`             |          |                      |
| SOURCE_TEXT   | VARCHAR(100)             | Yes  |                     |          |                      |
| UPDATED_AT    | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                      |
| OPERATOR_ID   | UUID                     | No   |                     | FK       | OPERATOR_PROFILE(ID) |
| INTAKE_ID     | UUID                     | Yes  |                     | FK       | DELIVERY_INTAKE(ID)  |

**Constraints:** Deleting an operator is restricted. Deleting an intake sets `INTAKE_ID` to `NULL`.

## SCAN_CLASSIFICATION

| Column        | Data Type    | Null | Default | PK or FK | FK Referenced Table |
| ------------- | ------------ | ---- | ------- | -------- | ------------------- |
| ID            | SERIAL       | No   |         | PK       |                     |
| CULTIVAR      | VARCHAR(20)  | No   |         |          |                     |
| RIPENESS      | VARCHAR(20)  | No   |         |          |                     |
| CONFIDENCE    | DECIMAL(5,2) | No   |         |          |                     |
| TEMPERATURE   | DECIMAL(5,2) | Yes  |         |          |                     |
| HUMIDITY      | DECIMAL(5,2) | Yes  |         |          |                     |
| SPOILAGE_DAYS | VARCHAR(20)  | No   |         |          |                     |
| FINGER_COUNT  | INT          | No   |         |          |                     |
| THUMBNAIL_URL | VARCHAR(500) | Yes  |         |          |                     |
| DEW_POINT     | DECIMAL(6,3) | Yes  |         |          |                     |
| VPD           | DECIMAL(6,3) | Yes  |         |          |                     |
| HEAT_INDEX    | DECIMAL(5,2) | Yes  |         |          |                     |
| TREATMENT     | VARCHAR(20)  | Yes  |         |          |                     |
| SCAN_ID       | UUID         | No   |         | FK       | SCAN(ID)            |

**Constraints:** `SCAN_ID` must be unique. `CULTIVAR` accepts `Lakatan`, `Latundan`, or `Cardaba`. `RIPENESS` accepts `Unripe`, `Semi Ripe`, `Ripe`, or `Overripe`. `CONFIDENCE` must be between 0 and 100. `TREATMENT` accepts `Natural` or `Ethephon`. Deleting a scan cascades to this record.

## SCAN_STATUS_LOG

| Column           | Data Type                | Null | Default | PK or FK | FK Referenced Table |
| ---------------- | ------------------------ | ---- | ------- | -------- | ------------------- |
| ID               | SERIAL                   | No   |         | PK       |                     |
| INVENTORY_STATUS | VARCHAR(30)              | No   |         |          |                     |
| UPDATED_AT       | TIMESTAMP WITH TIME ZONE | No   | `now()` |          |                     |
| SCAN_ID          | UUID                     | No   |         | FK       | SCAN(ID)            |

**Constraints:** `INVENTORY_STATUS` accepts `In Stock`, `Sold`, `For Processing`, or `Spoiled`. Deleting a scan cascades to these records.

## SCAN_ORIGINAL_AI_RESULT

| Column       | Data Type                | Null | Default | PK or FK | FK Referenced Table |
| ------------ | ------------------------ | ---- | ------- | -------- | ------------------- |
| ID           | SERIAL                   | No   |         | PK       |                     |
| CULTIVAR     | VARCHAR(20)              | No   |         |          |                     |
| RIPENESS     | VARCHAR(20)              | No   |         |          |                     |
| CONFIDENCE   | DECIMAL(5,2)             | No   |         |          |                     |
| FINGER_COUNT | INT                      | No   |         |          |                     |
| CREATED_AT   | TIMESTAMP WITH TIME ZONE | No   | `now()` |          |                     |
| SCAN_ID      | UUID                     | No   |         | FK       | SCAN(ID)            |

**Constraints:** `SCAN_ID` must be unique. `CULTIVAR` accepts `Lakatan`, `Latundan`, or `Cardaba`. `RIPENESS` accepts `Unripe`, `Semi Ripe`, `Ripe`, or `Overripe`. Deleting a scan cascades to this record.

## SCAN_DETECTION

| Column            | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ----------------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID                | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| CAMERA_ID         | VARCHAR(20)              | No   |                     |          |                     |
| CAMERA_LABEL      | VARCHAR(30)              | No   |                     |          |                     |
| DETECTED_CULTIVAR | VARCHAR(20)              | Yes  |                     |          |                     |
| DETECTED_RIPENESS | VARCHAR(20)              | Yes  |                     |          |                     |
| CONFIDENCE        | DECIMAL(5,2)             | Yes  |                     |          |                     |
| FINGER_COUNT      | INT                      | Yes  | `0`                 |          |                     |
| BOUNDING_BOXES    | JSONB                    | Yes  |                     |          |                     |
| INFERENCE_TIME_MS | DECIMAL(8,2)             | Yes  |                     |          |                     |
| CAPTURED_AT       | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| SCAN_ID           | UUID                     | No   |                     | FK       | SCAN(ID)            |

**Constraints:** Deleting a scan cascades to these records.

## SCAN_IMAGE

| Column          | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| --------------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID              | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| CAMERA_ID       | VARCHAR(20)              | No   |                     |          |                     |
| FILE_PATH       | VARCHAR(500)             | No   |                     |          |                     |
| WIDTH           | INT                      | Yes  |                     |          |                     |
| HEIGHT          | INT                      | Yes  |                     |          |                     |
| FILE_SIZE_BYTES | INT                      | Yes  |                     |          |                     |
| CAPTURED_AT     | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| SCAN_ID         | UUID                     | No   |                     | FK       | SCAN(ID)            |

**Constraints:** Deleting a scan cascades to these records.

## SCAN_NOTE

| Column      | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ----------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID          | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| TEXT        | TEXT                     | No   |                     |          |                     |
| AUTHOR_NAME | VARCHAR(100)             | No   |                     |          |                     |
| TIMESTAMP   | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| SCAN_ID     | UUID                     | No   |                     | FK       | SCAN(ID)            |

**Constraints:** Deleting a scan cascades to these records.

## ACTIVITY_LOG

| Column     | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| ---------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID         | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| TIMESTAMP  | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| ACTION     | VARCHAR(50)              | No   |                     |          |                     |
| DETAILS    | TEXT                     | Yes  |                     |          |                     |
| IP_ADDRESS | VARCHAR(45)              | Yes  |                     |          |                     |
| USER_ID    | UUID                     | Yes  |                     | FK       | USER_ACCOUNT(ID)    |

**Constraints:** `ACTION` accepts `login`, `logout`, `scan_created`, `scan_edited`, `scan_deleted`, `scan_flagged`, `user_created`, `user_updated`, `config_changed`, `supplier_created`, `supplier_updated`, `supplier_deleted`, `intake_created`, `intake_edited`, `intake_deleted`, `intake_status_changed`, `system_shutdown`, or `system_restart`. Deleting a user sets `USER_ID` to `NULL`.

## APP_NOTIFICATION

| Column    | Data Type                | Null | Default             | PK or FK | FK Referenced Table |
| --------- | ------------------------ | ---- | ------------------- | -------- | ------------------- |
| ID        | UUID                     | No   | `gen_random_uuid()` | PK       |                     |
| TYPE      | VARCHAR(30)              | No   |                     |          |                     |
| TITLE     | VARCHAR(200)             | No   |                     |          |                     |
| MESSAGE   | TEXT                     | No   |                     |          |                     |
| TIMESTAMP | TIMESTAMP WITH TIME ZONE | No   | `now()`             |          |                     |
| IS_READ   | BOOLEAN                  | Yes  | `false`             |          |                     |
| HREF      | VARCHAR(200)             | Yes  |                     |          |                     |
| USER_ID   | UUID                     | Yes  |                     | FK       | USER_ACCOUNT(ID)    |

**Constraints:** `TYPE` accepts `scan_complete`, `scan_flagged`, `intake_update`, `system_alert`, or `quality_warning`. Deleting a user cascades to their notifications.
