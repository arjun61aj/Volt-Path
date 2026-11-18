from math import radians, sin, cos, asin, sqrt
from config import ROAD_FACTOR, AVERAGE_CITY_SPEED_KMH


def haversine_km(lat1, lon1, lat2, lon2):
    p1,p2 = radians(lat1),radians(lat2); dlat=radians(lat2-lat1); dlon=radians(lon2-lon1)
    a=sin(dlat/2)**2 + cos(p1)*cos(p2)*sin(dlon/2)**2
    return 6371 * 2 * asin(sqrt(a))

def road_distance_km(*args): return haversine_km(*args) * ROAD_FACTOR

def travel_minutes(distance_km): return max(1, round(distance_km / AVERAGE_CITY_SPEED_KMH * 60))

def parse_coordinates(value, lat=None, lon=None):
    """Return coordinates when supplied by browser fields or as `lat, lon`."""
    if lat not in (None, "") and lon not in (None, ""):
        try:
            a,b=float(lat),float(lon)
            if -90 <= a <= 90 and -180 <= b <= 180: return a,b
        except (TypeError,ValueError): pass
        raise ValueError("Invalid coordinates. Latitude must be -90 to 90 and longitude -180 to 180.")
    text=(value or "").strip()
    parts=[x.strip() for x in text.split(",")]
    if len(parts)!=2: return None
    try: a,b=map(float,parts)
    except ValueError: return None  # e.g. "Pune, Maharashtra" is a name/address, not coordinates.
    if -90 <= a <= 90 and -180 <= b <= 180: return a,b
    raise ValueError("Invalid coordinates. Latitude must be -90 to 90 and longitude -180 to 180.")

# Backward-compatible helper for code/tests that provide coordinates directly.
def parse_location(value, lat=None, lon=None):
    coords=parse_coordinates(value,lat,lon)
    if not coords: raise ValueError("Location names must be resolved by the geocoding service.")
    label="Current location" if lat not in (None,"") else "Custom coordinates"
    return *coords,label
