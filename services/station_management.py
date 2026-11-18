import re
from datetime import datetime, timezone
from services.distance import haversine_km

STATUSES={'active','maintenance','temporarily_closed'}
CHARGER_STATUSES={'available','occupied','maintenance','offline'}
CONNECTORS={'CCS2','Type 2','CHAdeMO','GB/T','Other'}

def now_iso(): return datetime.now(timezone.utc).isoformat()
def clean(v): return str(v or '').strip()

def parse_station_form(form):
    errors=[]
    def required(key,label):
        v=clean(form.get(key));
        if not v: errors.append(f'{label} is required.')
        return v
    name=required('name','Station name'); address=required('address','Address'); city=required('city','City'); state=required('state','State')
    pincode=clean(form.get('pincode'))
    if pincode and not re.fullmatch(r'[1-9][0-9]{5}',pincode): errors.append('Pincode must be a valid 6-digit Indian pincode.')
    try: lat=float(form.get('latitude',''))
    except (ValueError,TypeError): lat=999; errors.append('Latitude must be a number.')
    if lat!=999 and not -90<=lat<=90: errors.append('Latitude must be between -90 and 90.')
    try: lon=float(form.get('longitude',''))
    except (ValueError,TypeError): lon=999; errors.append('Longitude must be a number.')
    if lon!=999 and not -180<=lon<=180: errors.append('Longitude must be between -180 and 180.')
    is_24=clean(form.get('is_24_hours')) in {'1','on','true'}; opening=clean(form.get('opening_time')); closing=clean(form.get('closing_time'))
    if not is_24 and not opening: errors.append('Opening time is required unless station is open 24 hours.')
    if not is_24 and not closing: errors.append('Closing time is required unless station is open 24 hours.')
    if not is_24 and opening and closing and opening==closing: errors.append('Opening and closing time cannot be the same.')
    if is_24: opening,closing='00:00','23:59'
    phone=clean(form.get('contact_number')); email=clean(form.get('email'))
    if phone and not re.fullmatch(r'[+0-9 ()-]{7,20}',phone): errors.append('Contact number format is invalid.')
    if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): errors.append('Email address format is invalid.')
    status=clean(form.get('status')) or 'active'
    if status not in STATUSES: errors.append('Station status is invalid.')
    types=form.getlist('charger_type[]'); powers=form.getlist('power_kw[]'); connectors=form.getlist('connector_type[]'); statuses=form.getlist('charger_status[]'); remain=form.getlist('remaining_minutes[]')
    if not types: errors.append('Add at least one charger.')
    chargers=[]
    for i,ctype in enumerate(types):
        ctype=clean(ctype)
        try: power=float(powers[i])
        except (ValueError,TypeError,IndexError): power=0
        connector=clean(connectors[i]) if i<len(connectors) else ''
        cstatus=clean(statuses[i]) if i<len(statuses) else 'available'
        try: remaining=max(0,int(remain[i])) if i<len(remain) and remain[i] else 0
        except ValueError: remaining=0; errors.append(f'Charger {i+1} remaining time is invalid.')
        if not ctype: errors.append(f'Charger {i+1} type is required.')
        if power<=0: errors.append(f'Charger {i+1} power must be greater than 0.')
        if connector not in CONNECTORS: errors.append(f'Charger {i+1} connector is invalid.')
        if cstatus not in CHARGER_STATUSES: errors.append(f'Charger {i+1} status is invalid.')
        chargers.append({'charger_type':ctype,'power_kw':power,'connector_type':connector,'status':cstatus,'remaining_minutes':remaining})
    station={'name':name,'address':address,'city':city,'state':state,'pincode':pincode or None,'latitude':lat,'longitude':lon,
      'opening_time':opening,'closing_time':closing,'is_24_hours':int(is_24),'contact_number':phone or None,'email':email or None,
      'description':clean(form.get('description')) or None,'status':status,'maintenance_status':'maintenance' if status=='maintenance' else 'operational','queue_length':max(0,int(form.get('queue_length') or 0))}
    return station,chargers,errors

def nearby_duplicate(db,lat,lon,exclude_id=None,threshold_km=.25):
    rows=db.execute("SELECT station_id,name,latitude,longitude FROM stations WHERE status!='inactive'").fetchall()
    matches=[]
    for r in rows:
        if exclude_id and r['station_id']==exclude_id: continue
        d=haversine_km(lat,lon,r['latitude'],r['longitude'])
        if d<=threshold_km: matches.append({'station_id':r['station_id'],'name':r['name'],'distance_m':round(d*1000)})
    return sorted(matches,key=lambda x:x['distance_m'])
