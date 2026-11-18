PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS admins (
  admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stations (
  station_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
  address TEXT NOT NULL, city TEXT NOT NULL DEFAULT 'Mumbai', state TEXT NOT NULL DEFAULT 'Maharashtra',
  pincode TEXT, opening_time TEXT, closing_time TEXT,
  is_24_hours INTEGER NOT NULL DEFAULT 0 CHECK(is_24_hours IN (0,1)),
  maintenance_status TEXT NOT NULL DEFAULT 'operational',
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','maintenance','temporarily_closed','inactive')),
  queue_length INTEGER NOT NULL DEFAULT 0 CHECK(queue_length >= 0),
  contact_number TEXT, email TEXT, description TEXT, facilities TEXT NOT NULL DEFAULT '[]',
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK(verification_status IN ('unverified','verified')),
  verified_by TEXT, verified_at TEXT, last_verified TEXT,
  created_at TEXT, updated_at TEXT, created_by TEXT,
  data_source TEXT NOT NULL DEFAULT 'demo'
);
CREATE TABLE IF NOT EXISTS chargers (
  charger_id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
  charger_type TEXT NOT NULL, power_kw REAL NOT NULL CHECK(power_kw > 0),
  connector_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('available','occupied','maintenance','offline')),
  remaining_minutes INTEGER NOT NULL DEFAULT 0 CHECK(remaining_minutes >= 0),
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  review_id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, verification_status TEXT NOT NULL DEFAULT 'unverified'
);
CREATE TABLE IF NOT EXISTS reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL REFERENCES stations(station_id) ON DELETE CASCADE,
  report_type TEXT NOT NULL CHECK(report_type IN ('working','not_working','maintenance','charger_available','long_wait','station_not_found')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chargers_station ON chargers(station_id);
CREATE INDEX IF NOT EXISTS idx_reviews_station ON reviews(station_id);
CREATE INDEX IF NOT EXISTS idx_reports_station ON reports(station_id);

-- Version 3: operator submissions are isolated from operational stations until approval.
CREATE TABLE IF NOT EXISTS station_registrations (
  registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tracking_token TEXT NOT NULL UNIQUE,
  owner_name TEXT NOT NULL, company_name TEXT, owner_email TEXT NOT NULL, owner_phone TEXT NOT NULL,
  station_name TEXT NOT NULL, address TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL, pincode TEXT,
  latitude REAL NOT NULL, longitude REAL NOT NULL,
  opening_time TEXT, closing_time TEXT, is_24_hours INTEGER NOT NULL DEFAULT 0 CHECK(is_24_hours IN (0,1)),
  description TEXT, facilities TEXT NOT NULL DEFAULT '[]', queue_length INTEGER NOT NULL DEFAULT 0,
  registration_status TEXT NOT NULL DEFAULT 'pending' CHECK(registration_status IN ('pending','approved','rejected')),
  rejection_reason TEXT, station_id INTEGER REFERENCES stations(station_id),
  submitted_at TEXT NOT NULL, reviewed_at TEXT, reviewed_by TEXT
);
CREATE TABLE IF NOT EXISTS registration_chargers (
  registration_charger_id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER NOT NULL REFERENCES station_registrations(registration_id) ON DELETE CASCADE,
  charger_type TEXT NOT NULL, power_kw REAL NOT NULL CHECK(power_kw>0), connector_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('available','occupied','maintenance','offline')),
  remaining_minutes INTEGER NOT NULL DEFAULT 0 CHECK(remaining_minutes>=0)
);
CREATE INDEX IF NOT EXISTS idx_registration_status ON station_registrations(registration_status);
CREATE INDEX IF NOT EXISTS idx_registration_chargers ON registration_chargers(registration_id);

-- Persistent cache avoids repeated requests to the public geocoder.
CREATE TABLE IF NOT EXISTS geocoding_cache (
  query_key TEXT PRIMARY KEY,
  query_text TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
