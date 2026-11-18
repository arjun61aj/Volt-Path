# VoltPath — Smart EV Charging Station Finder

```
[Open Here Link](https://volt-path-lyum.onrender.com)
```

A complete Flask + SQLite academic project that answers **“Which charging station is the best option for me right now?”** It keeps A* route search, but does not pretend A* alone is a recommendation engine. Route search, eligibility filtering, physical estimates, and multi-factor ranking are separate services.

> **Accuracy notice:** Included station names, charger states, queues, reviews, reports, and verification times are **demo/simulated data**. The UI labels them accordingly. OpenStreetMap tiles and Google Maps route links are map conveniences—not live charger feeds.

## Problem and objective

The nearest station can be closed, full, slow, unreliable, or under maintenance. VoltPath searches routes and recommends an eligible station balancing travel, waiting, availability, charge speed, rating, and reliability. Alternatives remain visible so the user can decide.

## Architecture (designed before implementation)

```text
Browser: Jinja UI + JavaScript + Leaflet
        │ HTML forms / JSON APIs
Flask application factory (app.py)
        ├── distance.py         Haversine + travel assumptions
        ├── astar.py            Generic A* + station graph
        ├── availability.py     Hours, charger state, queue
        ├── charging_time.py    Energy and charging estimates
        ├── reviews.py          Dynamic rating/reliability
        └── recommendation.py   Filter, normalize, rank
        │
SQLite: stations ──< chargers / reviews / reports
```

Calculations are outside Flask routes. `config.py` holds project assumptions and weights. This supports replacing simulated fields with live provider adapters later.

## Features

- Mumbai area names, `latitude,longitude`, or browser geolocation
- 15 varied demo stations, including 24-hour, overnight, queue, and maintenance cases
- A* route search over a dynamic nearby-station graph
- Automatic open/closed status, including midnight-spanning hours
- Per-charger AC/DC power, connector, and available/occupied/maintenance state
- Queue simulation and current-session remaining times
- Energy, charge-time, travel-time, and total-time estimates
- Stored reviews and dynamic SQL average; “No reviews yet” when empty
- Bayesian-smoothed reliability so one report cannot dominate
- Configurable normalized ranking; recommended result plus alternatives
- Responsive map, station details, review form, JSON APIs, and dashboard
- Validation and automated edge-case tests

## Database design

The constrained schema is in `database/schema.sql`.

- **stations:** coordinates, address, hours, 24-hour flag, station maintenance, queue, verification timestamp, source.
- **chargers:** station foreign key, AC/DC type, kW, connector, status, remaining minutes. Maintenance units are ignored.
- **reviews:** station foreign key, 1–5 rating, comment, timestamp, verification source. Average and count are calculated, not hard-coded.
- **reports:** working, not working, maintenance, charger available, long wait, or station not found.

## How A* is used—accurately

`services/astar.py` implements generic A*:

```text
g(n) = accumulated edge road-distance estimate
h(n) = straight-line Haversine distance to the target
f(n) = g(n) + h(n)
```

The user and nearby stations become graph nodes connected to nearest neighbors. Edge cost is Haversine × 1.18. A* obtains a route-distance estimate for each candidate. Production should replace this compact graph with road-network nodes from a routing provider or OpenStreetMap extract.

**A* does not calculate station quality.** Operational filtering, queue/charge estimates, and recommendation ranking happen afterward in separate modules.

## Calculations

### Distance and travel

```text
straight distance = Haversine(user, station)
road estimate = straight distance × 1.18
travel minutes = route km ÷ 24 km/h × 60
```

The road factor and city speed are demo assumptions, not live traffic.

### Energy and charging

```text
energy required = capacity × (target − current) / 100
minutes = energy ÷ (charger kW × 0.90 efficiency) × 60
```

A modest taper adjustment applies to the portion above 80%. Actual time varies with the vehicle limit, charging curve, sharing, temperature, and battery health.

### Waiting and total

If a free charger remains after queued vehicles, wait is zero. Otherwise each queued vehicle is simulated as a 35-minute session on the earliest usable charger, beginning with each occupied unit’s `remaining_minutes`.

```text
total estimated time = travel + waiting + charging
```

## Eligibility and ranking

Closed stations, station-level maintenance, and sites without usable chargers remain visible but cannot be “Best option.” Eligible factors are min-max normalized within the current results; lower cost is better.

| Factor | Weight |
|---|---:|
| Travel | 30% |
| Waiting | 25% |
| Availability penalty | 20% |
| Charging | 10% |
| Reliability penalty | 10% |
| Rating penalty | 5% |

These are configurable **project-defined weights**, not universal standards. Edit `RECOMMENDATION_WEIGHTS` in `config.py`.

## Reliability

Positive reports are `working` and `charger_available`. A Bayesian prior of 8 positive and 2 negative virtual observations avoids overreacting to one report:

```text
reliability = (positive + 8) / (positive + negative + 10) × 100
```

Production should also use recency, trusted-provider data, unique users, and abuse detection.

## Folder structure

```text
smart-ev-finder/
├── app.py, config.py, seed.py, requirements.txt, README.md
├── database/     schema.sql + ev_charging.db
├── data/         stations.csv
├── models/       database access
├── services/     A*, distance, time, availability, reviews, ranking
├── templates/    home, results, station, dashboard, 404
├── static/       responsive CSS + browser/map JS
└── tests/        service and Flask tests
```

## Install and run

```bash
cd smart-ev-finder
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python app.py
```

Open <https://volt-path-lyum.onrender.com>. Running `python seed.py` resets demo data; normal app startup seeds only an empty database. Copy `.env.example` for future provider keys—none are hard-coded.

## Routes / APIs

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Search |
| POST | `/search` | HTML recommendations |
| GET | `/station/<id>` | Details and reviews |
| POST | `/review/<id>` | Store review/report |
| GET | `/dashboard` | Demo network overview |
| GET | `/api/stations` | Stations JSON |
| GET | `/api/station/<id>` | Station JSON |
| POST | `/api/recommend` | Recommendation JSON |
| GET | `/api/reviews/<id>` | Reviews JSON |

```bash
curl -X POST http://127.0.0.1:5000/api/recommend \
 -H 'Content-Type: application/json' \
 -d '{"location":"Mumbai","capacity":60,"current":20,"target":80,"radius":20}'
```

## Validation and edge cases

Capacity must be positive; battery values are 0–100; target cannot be below current; rating is 1–5; radius is 1–100 km. 0% current and 100% target are valid. UI/API handle no nearby station, all ineligible, full chargers, queues, maintenance, overnight hours, and no reviews.

## Tests

```bash
python -m pytest -q
```

The 18 tests cover open/closed/24-hour/overnight/invalid hours, maintenance, available/occupied units, queues, energy, 100% taper, A* shortest path, coordinates, API validation, and no results.

## Map fallback

Leaflet/OpenStreetMap needs internet but no key. Without tiles, textual distances and ranked cards remain functional. “Get directions” passes coordinates to Google Maps.

## Future improvements

- Live OCPI/OCPP/network adapters and periodic status ingestion
- Real road graph and traffic-aware routing
- Authentication, moderation, CSRF protection, unique-user/rate-limited reports
- Vehicle connector compatibility and maximum input power
- Pricing, amenities, reservations, accessibility, and renewable-energy data
- Recency-decayed reliability and learned queue prediction
- WebSockets, migrations, production database, caching, and observability

## Academic note

This demonstrates graph search, geospatial distance, normalized weighted decisions, relational aggregation, validation, testing, and full-stack Flask development. Do not use it for real charging decisions until connected to verified live data.

# Version 2 — Station Management

Version 2 adds permanent, administrator-controlled network growth while preserving every Version 1 feature. A station created in the admin panel is inserted into the same SQLite `stations` and `chargers` tables read by search. No static list or in-memory append is used, so the record survives Flask restarts and automatically becomes an A* destination and map marker.

## Admin authentication and security

Protected routes use a session-based `Admin/Station Manager` role. The initial administrator is created at startup and the database stores only a Werkzeug PBKDF2 password hash. Admin POST forms use a per-session CSRF token. All submitted values are validated again on the server; client validation is only a convenience.

For the local academic demo, initial credentials are:

```text
Username: admin
Password: ChangeMe123!
```

Change them before first production-style use:

```bash
export FLASK_SECRET_KEY='a-long-random-secret'
export ADMIN_USERNAME='station-manager'
export ADMIN_PASSWORD='a-strong-unique-password'
python app.py
```

Alternatively set `ADMIN_PASSWORD_HASH` to a pre-generated Werkzeug hash. Existing admin rows are never overwritten at restart. API/map keys belong in environment variables; none are hard-coded. Production deployment should also use HTTPS, secure cookie flags, login throttling, password reset/rotation, and a production WSGI server.

## V1 → V2 database migration

`models/database.py:migrate_db()` performs an idempotent in-place migration; it does not create a second database or remove V1 data. It adds:

```text
stations: city, state, pincode, status, contact_number, email,
          description, verification_status, verified_by, verified_at,
          created_at, updated_at, created_by
chargers: offline status, created_at, updated_at
admins:   username, password_hash, created_at
```

SQLite cannot modify an existing `CHECK` constraint, so the migration transaction rebuilds only the charger table when needed, copies all V1 charger rows, and then restores indexes. Reviews and reports remain linked to their original station IDs.

## Admin pages

| Method | Route | Function |
|---|---|---|
| GET/POST | `/admin/login` | Authenticate station manager |
| POST | `/admin/logout` | End admin session |
| GET | `/admin/` | Metrics and management shortcuts |
| GET | `/admin/stations` | Active/inactive station directory |
| GET/POST | `/admin/stations/add` | Add station and chargers |
| GET/POST | `/admin/stations/<id>/edit` | Edit station and charger set |
| POST | `/admin/stations/<id>/deactivate` | Soft-delete from user search |
| POST | `/admin/stations/<id>/verify` | Record verifier and timestamp |
| GET | `/admin/reviews` | Review management information |
| GET | `/admin/reports` | Status-report information |

Friendly aliases `/add-station` and `/manage-stations` redirect to protected admin pages.

## Add-station workflow

```text
Authenticate → complete form → server validation → nearby duplicate check
→ transaction begins → insert station → insert every charger → commit
→ success page → automatically available to search/map/A*
```

The form supports station identity/address, Indian pincode, latitude/longitude, a click/drag Leaflet picker, normal or 24-hour opening, contact details, description, initial queue and status, and any number of normalized charger records. Charger connector options are CCS2, Type 2, CHAdeMO, GB/T, and Other; state options are available, occupied, maintenance, and offline.

Station IDs are SQLite-generated integers and displayed as `STN0001`, `STN0002`, and so on. `created_by`, `created_at`, and `updated_at` are audit fields. Adding the station and all chargers occurs inside one transaction: any exception rolls the entire operation back.

## Validation and duplicate detection

Server validation includes required text, latitude −90…90, longitude −180…180, Indian six-digit pincode, email/phone format, hours unless 24-hour, valid status/connector choices, positive charger power, and at least one charger.

Before insert, Haversine distance is calculated against active database stations. A site within 250 metres causes a `409 Possible Duplicate` confirmation page showing its name and distance. The administrator may cancel or explicitly continue because legitimate colocated sites can exist.

## Edit, deactivate, and verify

Editing updates station fields and replaces its charger set within one transaction, then refreshes `updated_at`. Deactivation is a soft delete: `status='inactive'` retains chargers, reviews, reports, and audit history, but normal station APIs/search exclude it. Verification records `verification_status`, `verified_by`, `verified_at`, and `last_verified`.

A newly added station starts with:

```text
Rating: No reviews yet
Verification: Not yet verified
```

No fake review, 5-star rating, or 100% reliability is inserted. Community reviews/reports and explicit admin verification build those signals later.

## Automatic search, map, and A* integration

`run_search()` queries all non-inactive stations from SQLite on every request. `build_station_graph()` then creates nodes from those returned records; therefore `astar.py` contains no hard-coded station. The same ranked JSON is embedded into the Leaflet map. A new active station is immediately evaluated for distance, hours, usable/offline chargers, queue, charge time, rating, reliability, eligibility, and composite cost.

Maintenance and temporarily closed stations remain visible when appropriate but are ineligible to win. Inactive stations are not returned to normal users.

## Version 2 tests

Version 2 adds integration tests for authentication protection, successful transaction, multiple chargers, latitude/longitude errors, missing name/hours, 24-hour storage, duplicate confirmation, search and map appearance, A* recommendation inclusion, edit, deactivate, unverified/no-review defaults, offline chargers, and persistence across application restart.

Current complete test result:

```text
33 passed
```

# Global named-location search

VoltPath is no longer limited to a hard-coded Mumbai dictionary. The existing search UI accepts any city, area, landmark, or full address that OpenStreetMap Nominatim can resolve—for example Pune, Delhi, London, Dubai, or `Pune, Maharashtra`. Direct `latitude, longitude` and browser geolocation continue to bypass the external geocoder.

## Resolution flow

```text
Search text → coordinate-pair detection
  ├─ coordinates/current location → use directly
  └─ location name/address → cached Nominatim lookup
       ├─ clear match → existing distance/A*/recommendation pipeline
       ├─ similar matches → user selects the intended location
       ├─ no match → friendly not-found message
       └─ provider unavailable → retry/manual-coordinate message
```

`services/geocoding.py` uses an identifying User-Agent, an eight-second timeout, a process-wide maximum of approximately one provider request per second, and a 30-day SQLite `geocoding_cache`. It calls Nominatim only after explicit form/API submission; autocomplete is deliberately not sent to the public Nominatim endpoint because its public usage policy does not support client autocomplete traffic.

Configure identification in the environment:

```bash
export GEOCODING_USER_AGENT='VoltPath-Smart-EV-Finder/3.0 (you@example.com)'
export NOMINATIM_EMAIL='you@example.com'
```

No API key is required. For production traffic, use a commercial/self-hosted geocoder and set `NOMINATIM_URL` appropriately.

The geocoder resolves only the **user location**. Charging stations still come exclusively from SQLite. A valid global location with no approved nearby station correctly returns zero results; it never generates fake stations. Approved operator registrations already flow into the same database query, distance filter, A* graph, map, time calculations, and recommendation logic.

### Geocoding API

```text
GET /api/geocode?q=Pune
POST /api/recommend
```

Ambiguous API requests return HTTP `409` with `choices`; service outages return `503`; unknown locations return `404`. The HTML flow presents a location-selection page for ambiguous names.
