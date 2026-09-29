PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY, installed_at TEXT NOT NULL);
INSERT OR IGNORE INTO schema_version VALUES(1, strftime('%Y-%m-%dT%H:%M:%SZ','now'));
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('reference_revision','0');
CREATE TABLE IF NOT EXISTS source_state(
 source_id TEXT PRIMARY KEY, domain TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
 config_hash TEXT NOT NULL, watermark INTEGER NOT NULL DEFAULT 0, coverage_from INTEGER,
 last_success TEXT, last_error TEXT, last_run_id TEXT, last_read INTEGER NOT NULL DEFAULT 0,
 last_written INTEGER NOT NULL DEFAULT 0, projection_note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS etl_run(
 run_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, run_kind TEXT NOT NULL,
 started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
 rows_read INTEGER NOT NULL DEFAULT 0, rows_written INTEGER NOT NULL DEFAULT 0,
 rows_unchanged INTEGER NOT NULL DEFAULT 0, rows_older INTEGER NOT NULL DEFAULT 0,
 rows_rejected INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_etl_run_time ON etl_run(started_at DESC);
CREATE TABLE IF NOT EXISTS schedule_run(
 task TEXT NOT NULL, local_day TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
 status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', PRIMARY KEY(task,local_day));
CREATE TABLE IF NOT EXISTS raw_splunk_event(
 source_id TEXT NOT NULL, event_hash TEXT NOT NULL, record_key TEXT,
 event_us INTEGER, indexed_us INTEGER, received_at TEXT NOT NULL,
 payload_json TEXT NOT NULL, PRIMARY KEY(source_id,event_hash));
CREATE INDEX IF NOT EXISTS ix_raw_event_age ON raw_splunk_event(received_at);
CREATE TABLE IF NOT EXISTS data_issue(
 issue_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, run_id TEXT,
 issue_code TEXT NOT NULL, event_hash TEXT, detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_issue_source ON data_issue(source_id,created_at DESC);
CREATE TABLE IF NOT EXISTS field_catalog(
 source_id TEXT NOT NULL, field_name TEXT NOT NULL, sample_types TEXT NOT NULL,
 last_seen TEXT NOT NULL, PRIMARY KEY(source_id,field_name));
CREATE TABLE IF NOT EXISTS reference_state(
 source_id TEXT PRIMARY KEY, oracle_table TEXT NOT NULL, kind TEXT NOT NULL,
 snapshot_id TEXT, loaded_at TEXT, row_count INTEGER NOT NULL DEFAULT 0,
 columns_json TEXT NOT NULL DEFAULT '[]', projection_ready INTEGER NOT NULL DEFAULT 0,
 projection_note TEXT NOT NULL DEFAULT 'NOT_LOADED');
CREATE TABLE IF NOT EXISTS reference_snapshot_log(
 snapshot_id TEXT NOT NULL, source_id TEXT NOT NULL, loaded_at TEXT NOT NULL,
 rows_read INTEGER NOT NULL, schema_hash TEXT NOT NULL, PRIMARY KEY(snapshot_id,source_id));
CREATE TABLE IF NOT EXISTS dim_product(
 material TEXT PRIMARY KEY, product_name TEXT NOT NULL DEFAULT '',
 product_group TEXT NOT NULL DEFAULT '', reference_source TEXT NOT NULL, snapshot_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dim_customer(
 customer_key TEXT PRIMARY KEY, customer_name TEXT NOT NULL DEFAULT '',
 customer_group TEXT NOT NULL DEFAULT '', reference_source TEXT NOT NULL, snapshot_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dim_conversion(
 period_ym TEXT NOT NULL, material TEXT NOT NULL, unit TEXT NOT NULL,
 eq_per_unit TEXT NOT NULL, reference_source TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 PRIMARY KEY(period_ym,material,unit));
CREATE TABLE IF NOT EXISTS dim_conversion_component(
 period_ym TEXT NOT NULL, material TEXT NOT NULL, conv_code TEXT NOT NULL,
 conv_family TEXT NOT NULL CHECK(conv_family IN ('DRAM','FLASH','OTHER')),
 eq_per_unit TEXT NOT NULL, reference_source TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 PRIMARY KEY(period_ym,material,conv_code));
CREATE INDEX IF NOT EXISTS ix_conversion_component_material
 ON dim_conversion_component(material,period_ym,conv_family);
CREATE TABLE IF NOT EXISTS plan_monthly(
 plan_id TEXT PRIMARY KEY, reference_source TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 direction TEXT NOT NULL CHECK(direction IN ('inbound','shipment')),
 period_ym TEXT NOT NULL, plan_version TEXT NOT NULL,
 metric TEXT NOT NULL CHECK(metric IN ('EA','BOX','EQ','USD')),
 target_i INTEGER NOT NULL, display_unit TEXT NOT NULL,
 material TEXT NOT NULL DEFAULT '*', product_group TEXT NOT NULL DEFAULT '*',
 customer_key TEXT NOT NULL DEFAULT '*', plant TEXT NOT NULL DEFAULT '*', warehouse TEXT NOT NULL DEFAULT '*',
 scope_confirmed INTEGER NOT NULL DEFAULT 0,
 UNIQUE(reference_source,period_ym,plan_version,metric,material,product_group,customer_key,plant,warehouse));
CREATE INDEX IF NOT EXISTS ix_plan_period ON plan_monthly(direction,period_ym,metric);
CREATE TABLE IF NOT EXISTS plan_actual_source(
 plan_source TEXT NOT NULL, actual_source TEXT NOT NULL,
 PRIMARY KEY(plan_source,actual_source));
CREATE TABLE IF NOT EXISTS fact_valuation(
 source_id TEXT NOT NULL, record_key TEXT NOT NULL, event_hash TEXT NOT NULL,
 reference_revision INTEGER NOT NULL, eq_i INTEGER, eq_dram_i INTEGER, eq_flash_i INTEGER, note TEXT NOT NULL,
 PRIMARY KEY(source_id,record_key));
