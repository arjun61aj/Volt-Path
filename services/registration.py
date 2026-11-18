import json, re, secrets
from werkzeug.datastructures import MultiDict
from services.station_management import parse_station_form, nearby_duplicate
from services.distance import haversine_km

FACILITIES={'parking':'Parking','restroom':'Restroom','cafe':'Food / Cafe','wifi':'Wi-Fi','security':'Security','waiting_area':'Waiting area'}

def parse_registration_form(form):
    errors=[]
    owner_name=str(form.get('owner_name','')).strip(); company=str(form.get('company_name','')).strip()
    owner_email=str(form.get('owner_email','')).strip(); owner_phone=str(form.get('owner_phone','')).strip()
    if not owner_name: errors.append('Owner or operator name is required.')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',owner_email): errors.append('A valid owner email is required.')
    if not re.fullmatch(r'[+0-9 ()-]{7,20}',owner_phone): errors.append('A valid owner phone number is required.')
    # Reuse V2's validated station/charger parser, forcing a proposed active operational state.
    values=MultiDict(form)
    values.setlist('status',['active'])
    station,chargers,station_errors=parse_station_form(values); errors.extend(station_errors)
    declared=form.get('total_chargers')
    try: declared_count=int(declared)
    except (ValueError,TypeError): declared_count=0
    if declared_count<=0: errors.append('Number of chargers must be greater than 0.')
    elif declared_count!=len(chargers): errors.append('Number of chargers must match the charger records provided.')
    facilities=[key for key in FACILITIES if str(form.get(key,'')).lower() in {'1','on','true'}]
    owner={'owner_name':owner_name,'company_name':company or None,'owner_email':owner_email,'owner_phone':owner_phone}
    return owner,station,chargers,facilities,errors

def registration_duplicates(db,name,lat,lon,threshold_km=.25):
    matches=nearby_duplicate(db,lat,lon,threshold_km=threshold_km)
    known={m.get('station_id') for m in matches}
    # Exact normalized names are also flagged even when coordinates are farther apart.
    for r in db.execute("SELECT station_id,name,latitude,longitude FROM stations WHERE status!='inactive' AND lower(trim(name))=lower(trim(?))",(name,)):
        if r['station_id'] not in known:
            matches.append({'station_id':r['station_id'],'name':r['name'],'distance_m':round(haversine_km(lat,lon,r['latitude'],r['longitude'])*1000),'name_match':True})
    rows=db.execute("SELECT registration_id,station_name,latitude,longitude FROM station_registrations WHERE registration_status='pending'").fetchall()
    for r in rows:
        d=haversine_km(lat,lon,r['latitude'],r['longitude'])
        similar=name.strip().lower()==r['station_name'].strip().lower()
        if d<=threshold_km or similar:
            matches.append({'registration_id':r['registration_id'],'name':r['station_name'],'distance_m':round(d*1000),'pending':True})
    return sorted(matches,key=lambda x:x['distance_m'])

def tracking_token(): return secrets.token_urlsafe(24)
def facilities_json(values): return json.dumps(values)
def facilities_from_json(value):
    try: return json.loads(value or '[]')
    except (ValueError,TypeError): return []
