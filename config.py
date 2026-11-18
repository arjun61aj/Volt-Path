from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "database" / "ev_charging.db"
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-change-me")
SEARCH_RADIUS_KM = 35.0
ROAD_FACTOR = 1.18
AVERAGE_CITY_SPEED_KMH = 24.0
CHARGER_EFFICIENCY = 0.90
# Project-defined weights; lower composite score is better. They are not universal standards.
RECOMMENDATION_WEIGHTS = {
    "travel": 0.30,
    "waiting": 0.25,
    "availability": 0.20,
    "charging": 0.10,
    "reliability": 0.10,
    "rating": 0.05,
}
POSITIVE_REPORTS = {"working", "charger_available"}
NEGATIVE_REPORTS = {"not_working", "maintenance", "station_not_found", "long_wait"}
