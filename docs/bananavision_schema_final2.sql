-- ============================================================
-- bananavision database schema (final / aligned)
-- ============================================================
-- this schema represents the final alignment between the
-- designed data dictionary and the actual frontend models
-- found in src/types/index.ts and src/context/appcontext.tsx.
-- ============================================================

create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ============================================================
-- drop existing tables
-- ============================================================

drop table if exists app_notification cascade;
drop table if exists activity_log cascade;
drop table if exists scan_note cascade;
drop table if exists scan_classification cascade;
drop table if exists scan_original_ai_result cascade;
drop table if exists scan_status_log cascade;
drop table if exists scan cascade;
drop table if exists delivery_intake cascade;
drop table if exists supplier cascade;
drop table if exists device cascade;
drop table if exists system_config cascade;
drop table if exists operator_profile cascade;
drop table if exists admin_profile cascade;
drop table if exists user_account cascade;
drop table if exists user_role cascade;

-- ============================================================
-- core user & roles (aligned with user type + profiles for expansion)
-- ============================================================

create table user_role (
    id               serial primary key,
    name             varchar(30) unique not null,
    description      varchar(255)
);

create table user_account (
    id                       uuid primary key default gen_random_uuid(),
    username                 varchar(50) unique not null,
    full_name                varchar(100) not null,
    id                       int not null references user_role(id) on delete restrict,
    status                   varchar(20) default 'active' check (status in ('active', 'inactive')),
    avatar_url               text,
    password_hash            varchar(255) not null,
    requires_pwd_change      boolean default false,
    pwd_setup_reason         varchar(50) check (pwd_setup_reason in ('new_account', 'password_reset')),
    last_active              timestamp,
    created_at               timestamp not null default now(),
    updated_at               timestamp not null default now()
);

-- administrator profile extension
create table admin_profile (
    id               uuid primary key default gen_random_uuid(),
    account_id       uuid not null unique references user_account(id) on delete cascade,
    created_at       timestamp not null default now(),
    updated_at       timestamp not null default now()
);

-- operator profile extension (contains operator-specific properties like pins and scan counters)
create table operator_profile (
    id                   uuid primary key default gen_random_uuid(),
    account_id           uuid not null unique references user_account(id) on delete cascade,
    pin_hash             varchar(255),
    requires_pin_change  boolean default false,
    pin_setup_reason     varchar(50) check (pin_setup_reason in ('new_account', 'pin_reset')),
    total_scans          int default 0,
    flagged_scans        int default 0,
    created_at           timestamp not null default now(),
    updated_at           timestamp not null default now()
);

-- ============================================================
-- system configuration
-- ============================================================

create table system_config (
    id                   serial primary key,
    camera_ids           text not null,         -- aligned with config { cameraids: string }
    confidence_threshold int not null,          -- aligned with config { confidencethreshold: number }
    updated_at           timestamp not null default now(),
    upt_by_admin         uuid references admin_profile(id) on delete set null
);

-- ============================================================
-- device management (aligned with device type)
-- ============================================================

create table device (
    id              uuid primary key default gen_random_uuid(),
    camera_id       varchar(50) unique not null,
    label           varchar(100) not null,
    status          varchar(20) default 'offline' check (status in ('online', 'offline')),
    resolution      varchar(20) default '1920x1080',
    last_seen       timestamp,
    created_at      timestamp not null default now(),
    updated_at      timestamp not null default now()
);

-- ============================================================
-- supplier & intake (aligned with supplier & dailyintake types)
-- ============================================================

create table supplier (
    id              uuid primary key default gen_random_uuid(),
    name            varchar(100) not null,
    contact_person  varchar(100),
    contact_phone   varchar(20),
    status          varchar(20) default 'active' check (status in ('active', 'inactive')),
    date_added      timestamp not null default now(),
    updated_at      timestamp not null default now()
);

create table delivery_intake (
    id               uuid primary key default gen_random_uuid(),
    source           varchar(100) not null,
    date             date not null,
    status           varchar(20) default 'active' check (status in ('active', 'depleted')),
    created_at       timestamp not null default now(),
    updated_at       timestamp not null default now()
);

-- ============================================================
-- scan tables (aligned with scanresult & scannote types)
-- ============================================================

create table scan (
    id                   uuid primary key default gen_random_uuid(),
    date_time            timestamp not null default now(),
    flagged              boolean default false,
    is_overridden        boolean default false,
    operator_id          uuid not null references operator_profile(id) on delete restrict,
    intake_id            uuid references delivery_intake(id) on delete set null,
    source_text          varchar(100), -- explicit denormalized source for quick lookup
    updated_at           timestamp not null default now()
);

create table scan_classification (
    id             serial primary key,
    scan_id        uuid unique not null references scan(id) on delete cascade,
    cultivar       varchar(20) not null check (cultivar in ('lakatan', 'latundan', 'saba')),
    ripeness       varchar(20) not null check (ripeness in ('unripe', 'semi_ripe', 'ripe', 'overripe')),
    confidence     decimal(5,2) not null check (confidence >= 0 and confidence <= 100),
    temperature    decimal(5,2), -- added from frontend scanresult
    humidity       decimal(5,2), -- added from frontend scanresult
    spoilage_days  varchar(20) not null,
    finger_count   int not null,
    thumbnail_url  varchar(500)
);

create table scan_status_log (
    id                 serial primary key,
    scan_id            uuid not null references scan(id) on delete cascade,
    inventory_status   varchar(30) not null check (inventory_status in ('in stock', 'sold', 'for processing', 'spoiled')),
    updated_at         timestamp not null default now()
);

-- represents the `originalairesult` property structure
create table scan_original_ai_result (
    id             serial primary key,
    scan_id        uuid unique not null references scan(id) on delete cascade,
    cultivar       varchar(20) not null check (cultivar in ('lakatan', 'latundan', 'saba')),
    ripeness       varchar(20) not null check (ripeness in ('unripe', 'semi_ripe', 'ripe', 'overripe')),
    confidence     decimal(5,2) not null,
    finger_count   int not null,
    created_at     timestamp not null default now()
);

-- ============================================================
-- iot camera infrastructure (4 camera support)
-- ============================================================

create table scan_detection (
    id                   uuid primary key default gen_random_uuid(),
    scan_id              uuid not null references scan(id) on delete cascade,
    camera_id            varchar(20) not null,
    camera_label         varchar(30) not null,
    detected_cultivar    varchar(20),
    detected_ripeness    varchar(20),
    confidence           decimal(5,2),
    finger_count         int default 0,
    bounding_boxes       jsonb,
    inference_time_ms    decimal(8,2),
    captured_at          timestamp not null default now()
);

create table scan_image (
    id               uuid primary key default gen_random_uuid(),
    scan_id          uuid not null references scan(id) on delete cascade,
    camera_id        varchar(20) not null,
    file_path        varchar(500) not null,
    width            int,
    height           int,
    file_size_bytes  int,
    captured_at      timestamp not null default now()
);

-- aligned with the scannote interface in appcontext.tsx
create table scan_note (
    id                     uuid primary key default gen_random_uuid(),
    scan_id                uuid not null references scan(id) on delete cascade,
    text                   text not null,
    author_name            varchar(100) not null, -- storing author explicitly based on interface
    timestamp              timestamp not null default now()
);

-- ============================================================
-- system logs & notifications (aligned with activitylog & appnotification types)
-- ============================================================

create table activity_log (
    id               uuid primary key default gen_random_uuid(),
    timestamp        timestamp not null default now(),
    user_id          uuid references user_account(id) on delete set null,
    action           varchar(50) not null check (action in (
                            'login', 'logout', 'scan_created', 'scan_edited', 
                            'user_created', 'user_updated', 'config_changed', 'scan_flagged', 
                            'supplier_created', 'supplier_updated', 
                            'intake_created', 'intake_edited',  
                            'intake_status_changed'
                        )),
    details          text not null,
    ip_address       varchar(45)
);

create table app_notification (
    id            uuid primary key default gen_random_uuid(),
    type          varchar(30) not null check (type in ('scan_complete', 'scan_flagged', 'intake_update', 'system_alert', 'quality_warning')),
    title         varchar(200) not null,
    message       text not null,
    timestamp     timestamp not null default now(),
    is_read       boolean default false,
    href          varchar(200),
    user_id       uuid references user_account(id) on delete cascade
);

-- ============================================================
