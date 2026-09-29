"""One database path, explicit schema migration, and local-only web settings."""
from __future__ import annotations
import contextlib, os, sqlite3
from pathlib import Path
from scm_db.settings import Settings
from scm_db.database import Database, choose_journal

ROOT = Path(__file__).resolve().parents[1]
_settings = None
_db_path = None
DEMO = False

def configure(settings: Settings, *, demo=False):
    global _settings, _db_path, DEMO
    _settings = settings
    _db_path = settings.db_path
    DEMO = demo

def settings():
    global _settings
    if _settings is None:
        configure(Settings(ROOT))
    return _settings

def db_path():
    return Path(_db_path or settings().db_path).resolve()

def connect(readonly=True):
    path = db_path()
    if not path.is_file():
        raise RuntimeError('DB not initialized. Run SETUP.cmd or python run.py init.')
    con = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                          uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    if readonly:
        con.execute('PRAGMA query_only=ON')
    else:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA synchronous=FULL')
    return con

SCHEMA = """
CREATE TABLE IF NOT EXISTS manual_target(
 target_id INTEGER PRIMARY KEY AUTOINCREMENT,
 period_ym TEXT NOT NULL, direction TEXT NOT NULL,
 metric TEXT NOT NULL, target_name TEXT NOT NULL,
 target_value REAL NOT NULL CHECK(target_value>=0),
 priority INTEGER NOT NULL DEFAULT 10, enabled INTEGER NOT NULL DEFAULT 1,
 additive INTEGER NOT NULL DEFAULT 0, memo TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manual_target_filter(
 filter_id INTEGER PRIMARY KEY AUTOINCREMENT,
 target_id INTEGER NOT NULL REFERENCES manual_target(target_id) ON DELETE CASCADE,
 seq INTEGER NOT NULL, field_key TEXT NOT NULL,
 operator TEXT NOT NULL, filter_value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_manual_target_scope ON manual_target(period_ym,direction,metric,enabled);
CREATE INDEX IF NOT EXISTS ix_target_filter ON manual_target_filter(target_id,seq);
CREATE TABLE IF NOT EXISTS focus_item(
 focus_id INTEGER PRIMARY KEY AUTOINCREMENT, focus_type TEXT NOT NULL DEFAULT 'item',
 item_code TEXT, customer_code TEXT, label TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS shipment_amount_kzwi3(
 vbeln TEXT NOT NULL,posnr TEXT NOT NULL,vgbel TEXT,matnr TEXT,kzwi3 REAL,
 kzwi2 REAL,waerk TEXT,fkdat TEXT,kunag TEXT,soname TEXT,kunnr TEXT,shname TEXT,
 werks TEXT,lgort TEXT,collected_at TEXT,PRIMARY KEY(vbeln,posnr));
"""

def ensure_runtime():
    """Additive migration only. Never reset/drop a fact or user-owned table."""
    with contextlib.closing(connect(False)) as con:
        con.executescript(SCHEMA)
        for table in ('inbound_current','shipment_current','shipment_box_current','inventory_current','shipment_amount_current'):
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                stem=table.removesuffix('_current')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{stem}_record ON {table}(record_key)')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{stem}_report ON {table}(plant,scope_ok,deleted,business_date)')
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shipment_amount_current'").fetchone():
            con.execute('CREATE INDEX IF NOT EXISTS ix_shipment_amount_latest ON shipment_amount_current(record_key,modified_us DESC,generated_us DESC,indexed_us DESC,source_id)')
        columns={r['name'] for r in con.execute('PRAGMA table_info(shipment_amount_kzwi3)')}
        for name,kind in [('kzwi2','REAL'),('kunag','TEXT'),('soname','TEXT'),
                          ('kunnr','TEXT'),('shname','TEXT'),('werks','TEXT'),('lgort','TEXT')]:
            if name not in columns: con.execute(f'ALTER TABLE shipment_amount_kzwi3 ADD COLUMN {name} {kind}')
        con.commit()
