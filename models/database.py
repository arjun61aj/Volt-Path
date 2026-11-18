import sqlite3
from pathlib import Path
from flask import current_app, g

def connect(path):
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys = ON'); return db

def get_db():
    if 'db' not in g: g.db=connect(current_app.config['DATABASE'])
    return g.db

def close_db(_error=None):
    db=g.pop('db',None)
    if db is not None: db.close()

def _columns(db,table): return {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}

def migrate_db(db):
    """Idempotent V1→V2 migration; preserves all station/review/report data."""
    station_additions={
      'city':"TEXT NOT NULL DEFAULT 'Mumbai'",'state':"TEXT NOT NULL DEFAULT 'Maharashtra'",'pincode':'TEXT',
      'status':"TEXT NOT NULL DEFAULT 'active'",'contact_number':'TEXT','email':'TEXT','description':'TEXT','facilities':"TEXT NOT NULL DEFAULT '[]'",
      'verification_status':"TEXT NOT NULL DEFAULT 'unverified'",'verified_by':'TEXT','verified_at':'TEXT',
      'created_at':'TEXT','updated_at':'TEXT','created_by':'TEXT'}
    existing=_columns(db,'stations')
    for name,definition in station_additions.items():
        if name not in existing: db.execute(f'ALTER TABLE stations ADD COLUMN {name} {definition}')
    # SQLite cannot alter CHECK constraints. Rebuild the V1 charger table to add offline + audit columns.
    ccols=_columns(db,'chargers')
    sql=(db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='chargers'").fetchone() or [''])[0] or ''
    if 'offline' not in sql or 'created_at' not in ccols:
        db.execute('PRAGMA foreign_keys = OFF')
        db.execute('ALTER TABLE chargers RENAME TO chargers_v1')
        db.execute("""CREATE TABLE chargers (charger_id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE, charger_type TEXT NOT NULL, power_kw REAL NOT NULL CHECK(power_kw>0), connector_type TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('available','occupied','maintenance','offline')), remaining_minutes INTEGER NOT NULL DEFAULT 0 CHECK(remaining_minutes>=0), created_at TEXT, updated_at TEXT)""")
        old=_columns(db,'chargers_v1'); audit=', created_at, updated_at' if {'created_at','updated_at'}<=old else ''
        select_audit=', created_at, updated_at' if audit else ", datetime('now'), datetime('now')"
        db.execute(f'INSERT INTO chargers(charger_id,station_id,charger_type,power_kw,connector_type,status,remaining_minutes,created_at,updated_at) SELECT charger_id,station_id,charger_type,power_kw,connector_type,status,remaining_minutes{select_audit} FROM chargers_v1')
        db.execute('DROP TABLE chargers_v1'); db.execute('PRAGMA foreign_keys = ON')
    db.execute("UPDATE stations SET status=CASE WHEN maintenance_status='maintenance' THEN 'maintenance' ELSE COALESCE(status,'active') END")
    db.execute("UPDATE stations SET created_at=COALESCE(created_at,datetime('now')), updated_at=COALESCE(updated_at,datetime('now')), created_by=COALESCE(created_by,'system')")
    db.execute('CREATE INDEX IF NOT EXISTS idx_chargers_station ON chargers(station_id)')

def init_db(app):
    Path(app.config['DATABASE']).parent.mkdir(parents=True,exist_ok=True)
    with connect(app.config['DATABASE']) as db:
        schema=(Path(__file__).parents[1]/'database'/'schema.sql').read_text(); db.executescript(schema); migrate_db(db); db.commit()

def rows_to_dicts(rows): return [dict(row) for row in rows]
