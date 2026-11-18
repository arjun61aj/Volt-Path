import csv, random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from models.database import connect
from config import DATABASE

CHARGER_SETS = [
 [("DC",60,"CCS2","available",0),("DC",60,"CCS2","occupied",18),("AC",22,"Type 2","available",0),("DC",120,"CCS2","maintenance",0)],
 [("DC",50,"CCS2","occupied",12),("DC",50,"CCS2","occupied",28),("AC",22,"Type 2","available",0)],
 [("DC",120,"CCS2","available",0),("DC",60,"CCS2","available",0),("AC",7.4,"Type 2","occupied",20)],
 [("DC",60,"CCS2","occupied",8),("DC",60,"CCS2","occupied",25),("AC",22,"Type 2","occupied",32)],
 [("DC",50,"CCS2","available",0),("AC",22,"Type 2","available",0)],
]
COMMENTS=["Fast charger and clean station.","Easy to find; staff were helpful.","Charging worked, but parking was busy.","Good experience and clear signage.","Queue moved faster than expected."]

def seed(reset=False):
    db=connect(DATABASE)
    if reset:
        db.executescript("DELETE FROM reports; DELETE FROM reviews; DELETE FROM chargers; DELETE FROM stations;")
    if db.execute("SELECT COUNT(*) FROM stations").fetchone()[0]: db.close(); return
    csv_path=Path(__file__).parent/'data'/'stations.csv'; now=datetime.now(timezone.utc)
    with csv_path.open() as f:
        for i,row in enumerate(csv.DictReader(f)):
            cur=db.execute("INSERT INTO stations(name,latitude,longitude,address,opening_time,closing_time,is_24_hours,maintenance_status,queue_length,last_verified,data_source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (row['name'],float(row['latitude']),float(row['longitude']),row['address'],row['opening_time'],row['closing_time'],int(row['is_24_hours']),row['maintenance_status'],int(row['queue_length']),(now-timedelta(minutes=7+i*3)).isoformat(),'demo'))
            sid=cur.lastrowid
            items=CHARGER_SETS[i%len(CHARGER_SETS)]
            if row['maintenance_status']=='maintenance': items=[(a,b,c,'maintenance',0) for a,b,c,_,_ in items]
            db.executemany("INSERT INTO chargers(station_id,charger_type,power_kw,connector_type,status,remaining_minutes) VALUES(?,?,?,?,?,?)",[(sid,*x) for x in items])
            # One station deliberately has no reviews for the edge case.
            if i != 12:
                for j in range(3+(i%5)):
                    rating=max(1,min(5,5-((i+j)%4==0)-((i+j)%9==0)))
                    db.execute("INSERT INTO reviews(station_id,rating,comment,created_at,verification_status) VALUES(?,?,?,?,?)",(sid,rating,COMMENTS[(i+j)%len(COMMENTS)],(now-timedelta(days=j)).isoformat(),'demo'))
            reports=['working']*(8+i%5)+['charger_available']*3+(['long_wait']*(i%3))+(['not_working'] if i%6==0 else [])
            db.executemany("INSERT INTO reports(station_id,report_type,created_at) VALUES(?,?,?)",[(sid,r,(now-timedelta(hours=j)).isoformat()) for j,r in enumerate(reports)])
    db.commit(); db.close()
if __name__=='__main__': seed(reset=True); print(f"Seeded demo database: {DATABASE}")
