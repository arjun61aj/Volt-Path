"""Responsible, cached OpenStreetMap Nominatim geocoding.

This module resolves user-entered names only. It never creates station data.
Nominatim's public service is called only on explicit search submission, with an
identifying User-Agent, a one-request-per-second process limit, and SQLite cache.
"""
import json, os, threading, time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ENDPOINT=os.getenv('NOMINATIM_URL','https://nominatim.openstreetmap.org/search')
USER_AGENT=os.getenv('GEOCODING_USER_AGENT','VoltPath-Smart-EV-Finder/3.0 (academic project)')
CACHE_DAYS=int(os.getenv('GEOCODING_CACHE_DAYS','30'))
_rate_lock=threading.Lock(); _last_request=0.0

class LocationNotFound(ValueError): pass
class GeocodingUnavailable(RuntimeError): pass
class AmbiguousLocation(ValueError):
    def __init__(self,query,choices): self.query=query; self.choices=choices; super().__init__('Please select the intended location.')

def _key(text): return ' '.join(text.casefold().split())
def _public(item):
    try: lat=float(item['lat']); lon=float(item['lon'])
    except (KeyError,TypeError,ValueError): return None
    if not (-90<=lat<=90 and -180<=lon<=180): return None
    return {'name':item.get('display_name') or item.get('name') or 'Resolved location','latitude':lat,'longitude':lon,
      'importance':float(item.get('importance') or 0),'type':item.get('type',''),'category':item.get('category','')}

def _cached(db,key):
    row=db.execute('SELECT response_json,created_at FROM geocoding_cache WHERE query_key=?',(key,)).fetchone()
    if not row:return None
    try:
        created=datetime.fromisoformat(row['created_at']); fresh=datetime.now(timezone.utc)-created < timedelta(days=CACHE_DAYS)
        return json.loads(row['response_json']) if fresh else None
    except (ValueError,TypeError,json.JSONDecodeError): return None

def _request(query):
    global _last_request
    params={'q':query,'format':'jsonv2','addressdetails':'1','limit':'5','accept-language':'en'}
    email=os.getenv('NOMINATIM_EMAIL');
    if email: params['email']=email
    req=Request(f'{ENDPOINT}?{urlencode(params)}',headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with _rate_lock:
        delay=1.05-(time.monotonic()-_last_request)
        if delay>0: time.sleep(delay)
        try:
            with urlopen(req,timeout=8) as response: body=response.read().decode('utf-8')
            _last_request=time.monotonic()
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            _last_request=time.monotonic(); raise GeocodingUnavailable('Location service is temporarily unavailable.') from exc
    try: return json.loads(body)
    except json.JSONDecodeError as exc: raise GeocodingUnavailable('Location service returned an invalid response.') from exc

def geocode_candidates(query,db):
    text=' '.join(str(query or '').strip().split())
    if len(text)<2: raise ValueError('Please enter a valid location.')
    key=_key(text); raw=_cached(db,key)
    if raw is None:
        raw=_request(text)
        db.execute('INSERT OR REPLACE INTO geocoding_cache(query_key,query_text,response_json,created_at) VALUES(?,?,?,?)',(key,text,json.dumps(raw),datetime.now(timezone.utc).isoformat())); db.commit()
    candidates=[x for x in (_public(item) for item in raw) if x]
    # For equal provider importance, prefer an actual populated place (city/town)
    # over its administrative boundary.
    type_priority={'city':5,'town':4,'village':3,'municipality':2,'administrative':1}
    candidates.sort(key=lambda x:(x['importance'],type_priority.get(x['type'],0)),reverse=True)
    if not candidates: raise LocationNotFound("We couldn't find that location. Please enter a city, area, landmark, full address, or coordinates.")
    return candidates

def _clearly_best(query,choices):
    if len(choices)==1:return True
    first,second=choices[0],choices[1]; gap=first['importance']-second['importance']
    if first['name'].casefold()==second['name'].casefold(): return True
    # Nominatim importance is provider-defined. A clear gap means the first result
    # is suitable; similar-ranked results are shown to the user for confirmation.
    return gap>=0.10 or (first['importance']>=0.65 and gap>=0.04)

def geocode_location(query,db):
    choices=geocode_candidates(query,db)
    if not _clearly_best(query,choices): raise AmbiguousLocation(query,choices[:5])
    return choices[0]
