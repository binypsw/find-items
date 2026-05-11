"""Initial schema with pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-05-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension (required for Vector columns in products)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ENUM types
    listing_status = postgresql.ENUM(
        "active", "sold", "deleted", "stale", "error",
        name="listing_status", create_type=False,
    )
    listing_status.create(op.get_bind(), checkfirst=True)

    scrape_run_status = postgresql.ENUM(
        "pending", "running", "completed", "failed", "cancelled",
        name="scrape_run_status", create_type=False,
    )
    scrape_run_status.create(op.get_bind(), checkfirst=True)

    session_status = postgresql.ENUM(
        "active", "expired", "banned", "needs_refresh",
        name="session_status", create_type=False,
    )
    session_status.create(op.get_bind(), checkfirst=True)

    # sources
    op.create_table(
        "sources",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(256), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("health_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_credit_budget", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credits_used_this_month", sa.Integer, nullable=False, server_default="0"),
        sa.Column("api_provider", sa.String(32), nullable=True),
    )

    # saved_searches
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("raw_query", sa.Text, nullable=False),
        sa.Column("parsed_query", postgresql.JSONB, nullable=True),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("max_price", sa.Integer, nullable=True),
        sa.Column("min_price", sa.Integer, nullable=True),
        sa.Column("condition", sa.String(16), nullable=True),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("source_filter", postgresql.JSONB, nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("canonical_title", sa.String(512), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),  # managed via pgvector raw SQL below
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedup_group_id", sa.Integer, nullable=True),
    )
    # Replace TEXT column with proper vector type
    op.execute("ALTER TABLE products DROP COLUMN embedding")
    op.execute("ALTER TABLE products ADD COLUMN embedding vector(384)")
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_dedup_group_id", "products", ["dedup_group_id"])
    # ivfflat index for cosine similarity search (run AFTER initial data load for better clusters)
    op.execute(
        "CREATE INDEX products_embedding_ivfflat ON products "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # scrape_runs (created before listings because listings.scrape_run_id references it)
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("search_id", sa.Integer, sa.ForeignKey("saved_searches.id"), nullable=True),
        sa.Column("source_id", sa.String(32), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="scrape_run_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("items_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB, nullable=True),
        sa.Column("api_credits_used", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_scrape_runs_search_id", "scrape_runs", ["search_id"])
    op.create_index("ix_scrape_runs_source_id", "scrape_runs", ["source_id"])
    op.create_index("ix_scrape_runs_status", "scrape_runs", ["status"])

    # listings
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=True),
        sa.Column("source_id", sa.String(32), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False, unique=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("current_price_thb", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_original", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("condition", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("seller_payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("image_urls", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("spec_tokens", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", postgresql.ENUM(name="listing_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consecutive_missing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer, nullable=False, server_default="720"),
        sa.Column("last_payload_hash", sa.String(64), nullable=True),
        sa.Column("price_change_count", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_listing_source_external"),
    )
    op.create_index("ix_listings_product_id", "listings", ["product_id"])
    op.create_index("ix_listings_source_id", "listings", ["source_id"])
    op.create_index("ix_listings_location", "listings", ["location"])
    op.create_index("ix_listings_status", "listings", ["status"])
    op.create_index("ix_listings_last_seen_at", "listings", ["last_seen_at"])
    op.create_index("ix_listings_next_poll_at", "listings", ["next_poll_at"])
    # GIN index for spec_tokens array overlap queries
    op.execute("CREATE INDEX listings_spec_gin ON listings USING GIN (spec_tokens)")

    # price_snapshots
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("listing_id", sa.Integer, sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("price_thb", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_original", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("fx_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scrape_run_id", sa.Integer, sa.ForeignKey("scrape_runs.id"), nullable=True),
    )
    op.create_index("ix_price_snapshots_listing_id", "price_snapshots", ["listing_id"])
    op.create_index("ix_price_snapshots_scraped_at", "price_snapshots", ["scraped_at"])
    op.execute(
        "CREATE INDEX ix_price_snapshots_listing_scraped "
        "ON price_snapshots (listing_id, scraped_at DESC)"
    )

    # account_sessions
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(32), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("cookies", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="session_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_sessions_source_id", "account_sessions", ["source_id"])
    op.create_index("ix_account_sessions_status", "account_sessions", ["status"])

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("channels", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_type", "notifications", ["type"])

    # Seed default sources
    op.execute("""
        INSERT INTO sources (id, name, base_url, tier, enabled, monthly_credit_budget) VALUES
        ('kaidee',   'Kaidee.com',           'https://www.kaidee.com',          'direct',      true, 0),
        ('shopee',   'Shopee Thailand',       'https://shopee.co.th',            'browserless', false, 0),
        ('lazada',   'Lazada Thailand',       'https://www.lazada.co.th',        'browserless', true, 0),
        ('facebook', 'Facebook Marketplace', 'https://www.facebook.com/marketplace', 'managed_api', false, 30000),
        ('aliexpress','AliExpress',           'https://www.aliexpress.com',       'browserless', true, 0),
        ('priceza',  'Priceza',               'https://www.priceza.com',          'direct',      true, 0),
        ('jib',      'JIB Computer',          'https://www.jib.co.th',            'direct',      true, 0),
        ('advice',   'Advice',                'https://www.advice.co.th',         'direct',      true, 0)
    """)


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("account_sessions")
    op.drop_table("price_snapshots")
    op.drop_table("listings")
    op.drop_table("scrape_runs")
    op.drop_table("products")
    op.drop_table("saved_searches")
    op.drop_table("sources")

    op.execute("DROP TYPE IF EXISTS session_status")
    op.execute("DROP TYPE IF EXISTS scrape_run_status")
    op.execute("DROP TYPE IF EXISTS listing_status")
    op.execute("DROP EXTENSION IF EXISTS vector")
