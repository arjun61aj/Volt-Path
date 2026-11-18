from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")

def _time(v): return time.fromisoformat(v) if v else None

def station_status(station, now=None):
    now = now or datetime.now(TZ)
    state=station.get('status','active')
    if state == 'inactive': return {'is_open':False,'label':'Inactive','next_open':None}
    if state == 'temporarily_closed': return {'is_open':False,'label':'Temporarily closed','next_open':None}
    if state == 'maintenance' or station.get("maintenance_status") == "maintenance":
        return {"is_open": False, "label":"Maintenance", "next_open":"After maintenance"}
    if station.get("is_24_hours"):
        return {"is_open":True,"label":"Open 24 hours","next_open":None}
    try: opening, closing = _time(station.get("opening_time")), _time(station.get("closing_time"))
    except ValueError:
        return {"is_open":False,"label":"Invalid hours","next_open":None}
    if not opening or not closing or opening == closing:
        return {"is_open":False,"label":"Invalid hours","next_open":None}
    current=now.timetz().replace(tzinfo=None)
    is_open = opening <= current < closing if opening < closing else (current >= opening or current < closing)
    if is_open: return {"is_open":True,"label":"Open","next_open":None}
    day = "today" if current < opening else "tomorrow"
    return {"is_open":False,"label":"Closed","next_open":f"Opens {day} at {opening.strftime('%I:%M %p')}"}

def counts(chargers):
    result={"total":len(chargers),"available":0,"occupied":0,"maintenance":0,"offline":0}
    for c in chargers: result[c["status"]]+=1
    return result

def waiting_minutes(chargers, queue_length):
    usable=[c for c in chargers if c["status"] not in {"maintenance","offline"}]
    available=sum(c["status"] == "available" for c in usable)
    if not usable: return 10_000
    # User can plug in now when one unit is free and nobody is queued ahead.
    if available > queue_length: return 0
    occupied_remaining=sorted([max(1,c.get("remaining_minutes",30)) for c in usable if c["status"]=="occupied"])
    slots=[0]*available + occupied_remaining
    if not slots: return 10_000
    # Simulate queued vehicles taking an average 35-minute session on the earliest free charger.
    for _ in range(queue_length):
        i=min(range(len(slots)), key=slots.__getitem__); slots[i]+=35
    return min(slots)
