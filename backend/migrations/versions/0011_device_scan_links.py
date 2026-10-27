"""Link scan detections and images to the device that produced them."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_device_scan_links"
down_revision = "0010_notification_read_receipts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # -- scan_detection -------------------------------------------------------
    if "scan_detection" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("scan_detection")}
        if "device_id" not in existing_cols:
            op.add_column(
                "scan_detection",
                sa.Column("device_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
            )
            op.create_index("ix_scan_detection_device_id", "scan_detection", ["device_id"])
            op.create_foreign_key(
                "scan_detection_device_id_fkey",
                "scan_detection", "device",
                ["device_id"], ["id"],
                ondelete="SET NULL",
            )

    # -- scan_image -----------------------------------------------------------
    if "scan_image" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("scan_image")}
        if "device_id" not in existing_cols:
            op.add_column(
                "scan_image",
                sa.Column("device_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
            )
            op.create_index("ix_scan_image_device_id", "scan_image", ["device_id"])
            op.create_foreign_key(
                "scan_image_device_id_fkey",
                "scan_image", "device",
                ["device_id"], ["id"],
                ondelete="SET NULL",
            )

    # -- Backfill existing rows by matching camera_id -------------------------
    # PostgreSQL-only: SQLite does not support UPDATE … FROM with table aliases.
    if bind.dialect.name == "postgresql" and "device" in tables:
        if "scan_detection" in tables:
            op.execute(
                sa.text(
                    "UPDATE scan_detection sd "
                    "SET device_id = d.id "
                    "FROM device d "
                    "WHERE sd.camera_id = d.camera_id "
                    "AND sd.device_id IS NULL"
                )
            )
        if "scan_image" in tables:
            op.execute(
                sa.text(
                    "UPDATE scan_image si "
                    "SET device_id = d.id "
                    "FROM device d "
                    "WHERE si.camera_id = d.camera_id "
                    "AND si.device_id IS NULL"
                )
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "scan_image" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("scan_image")}
        if "device_id" in existing_cols:
            op.drop_constraint("scan_image_device_id_fkey", "scan_image", type_="foreignkey")
            op.drop_index("ix_scan_image_device_id", table_name="scan_image")
            op.drop_column("scan_image", "device_id")

    if "scan_detection" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("scan_detection")}
        if "device_id" in existing_cols:
            op.drop_constraint("scan_detection_device_id_fkey", "scan_detection", type_="foreignkey")
            op.drop_index("ix_scan_detection_device_id", table_name="scan_detection")
            op.drop_column("scan_detection", "device_id")
