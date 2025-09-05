"""init hvac schema with TimescaleDB

Revision ID: 002_init_hvac_timescale
Revises: 
Create Date: 2025-09-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_init_hvac_timescale"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # =====================================================
    # Enable Timescale extension
    # =====================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    # =====================================================
    # Sites
    # =====================================================
    op.create_table(
        "sites",
        sa.Column("site_id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("tz", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # =====================================================
    # Devices
    # =====================================================
    op.create_table(
        "devices",
        sa.Column("device_id", sa.Text(), primary_key=True),
        sa.Column("site_id", sa.Text(), sa.ForeignKey("sites.site_id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # =====================================================
    # Points
    # =====================================================
    op.create_table(
        "points",
        sa.Column("point_id", sa.Text(), primary_key=True),
        sa.Column("site_id", sa.Text(), sa.ForeignKey("sites.site_id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Text(), sa.ForeignKey("devices.device_id", ondelete="CASCADE")),
        sa.Column("point_name", sa.Text(), nullable=False),
        sa.Column("point_type", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("site_id", "point_name", name="uq_points_site_name"),
    )

    # =====================================================
    # Measurements (Timescale hypertable)
    # =====================================================
    op.create_table(
        "measurements",
        sa.Column("site_id", sa.Text(), sa.ForeignKey("sites.site_id", ondelete="CASCADE"), nullable=False),
        sa.Column("point_id", sa.Text(), sa.ForeignKey("points.point_id", ondelete="CASCADE"), nullable=False),
        sa.Column("point_name", sa.Text()),
        sa.Column("unit", sa.Text()),
        sa.Column("ts_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("quality", sa.Integer()),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("meta_hash", sa.Text()),
        sa.PrimaryKeyConstraint("site_id", "point_id", "ts_utc"),
    )

    # Convert to hypertable
    op.execute("""
        SELECT create_hypertable(
            'measurements',
            'ts_utc',
            partitioning_column => 'site_id',
            number_partitions => 8,
            if_not_exists => TRUE
        );
    """)

    # Indexes
    op.create_index("ix_meas_point_time_desc", "measurements", ["point_id", sa.text("ts_utc DESC")])
    op.create_index("ix_meas_site_time", "measurements", ["site_id", "ts_utc"])

    # Enable compression
    op.execute("ALTER TABLE measurements SET (timescaledb.compress = 'true');")
    op.execute("SELECT add_compression_policy('measurements', interval '7 days', if_not_exists => TRUE);")
    op.execute("SELECT add_retention_policy('measurements', interval '365 days', if_not_exists => TRUE);")

    # =====================================================
    # Device State
    # =====================================================
    op.create_table(
        "device_state",
        sa.Column("device_id", sa.Text(), sa.ForeignKey("devices.device_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("site_id", sa.Text(), sa.ForeignKey("sites.site_id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_seen_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_upload_ts", sa.TIMESTAMP(timezone=True)),
        sa.Column("queue_depth", sa.Integer()),
        sa.Column("agent_version", sa.Text()),
        sa.Column("poll_interval_s", sa.Integer()),
        sa.Column("cpu_pct", sa.Float()),
        sa.Column("disk_free_gb", sa.Float()),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('ready','degraded','error')")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_devstate_site", "device_state", ["site_id"])
    op.create_index("ix_devstate_last_seen", "device_state", [sa.text("last_seen_ts DESC")])

    # =====================================================
    # Views
    # =====================================================
    op.execute("""
    CREATE MATERIALIZED VIEW IF NOT EXISTS v_point_latest AS
    SELECT DISTINCT ON (m.point_id)
      m.point_id, m.site_id, m.point_name, m.unit,
      m.ts_utc AS last_ts_utc, m.value, m.quality
    FROM measurements m
    ORDER BY m.point_id, m.ts_utc DESC;
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_v_point_latest ON v_point_latest(point_id);")

    op.execute("""
    CREATE OR REPLACE VIEW v_site_latest_window AS
    SELECT m.*
    FROM measurements m
    JOIN (
      SELECT point_id, max(ts_utc) AS last_ts
      FROM measurements
      WHERE ts_utc > now() - interval '1 day'
      GROUP BY point_id
    ) t ON t.point_id = m.point_id AND t.last_ts = m.ts_utc;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_devices_stale AS
    SELECT device_id, site_id, last_seen_ts, now() - last_seen_ts AS age
    FROM device_state
    WHERE now() - last_seen_ts > interval '120 seconds';
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS v_devices_stale;")
    op.execute("DROP VIEW IF EXISTS v_site_latest_window;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS v_point_latest;")

    op.drop_index("ix_devstate_last_seen", table_name="device_state")
    op.drop_index("ix_devstate_site", table_name="device_state")
    op.drop_table("device_state")

    op.drop_index("ix_meas_site_time", table_name="measurements")
    op.drop_index("ix_meas_point_time_desc", table_name="measurements")
    op.drop_table("measurements")

    op.drop_table("points")
    op.drop_table("devices")
    op.drop_table("sites")

    op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE;")
