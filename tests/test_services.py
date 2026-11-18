from datetime import datetime
from zoneinfo import ZoneInfo
from services.availability import station_status, waiting_minutes
from services.charging_time import energy_required, charging_minutes
from services.distance import parse_location
from services.astar import astar
TZ=ZoneInfo('Asia/Kolkata')
def dt(h): return datetime(2026,8,18,h,0,tzinfo=TZ)
def station(**kw): return {'opening_time':'06:00','closing_time':'23:00','is_24_hours':0,'maintenance_status':'operational',**kw}
def test_open_station(): assert station_status(station(),dt(12))['is_open']
def test_closed_station(): assert not station_status(station(),dt(3))['is_open']
def test_24_hour_station(): assert station_status(station(is_24_hours=1),dt(3))['is_open']
def test_overnight_hours(): assert station_status(station(opening_time='20:00',closing_time='06:00'),dt(23))['is_open']
def test_invalid_equal_hours(): assert station_status(station(opening_time='06:00',closing_time='06:00'),dt(8))['label']=='Invalid hours'
def test_maintenance_closed(): assert station_status(station(maintenance_status='maintenance'),dt(12))['label']=='Maintenance'
def test_available_charger_has_no_wait(): assert waiting_minutes([{'status':'available','remaining_minutes':0}],0)==0
def test_occupied_charger_wait(): assert waiting_minutes([{'status':'occupied','remaining_minutes':18}],0)==18
def test_queue_across_chargers():
    cs=[{'status':'occupied','remaining_minutes':10},{'status':'occupied','remaining_minutes':25}]
    assert waiting_minutes(cs,2)==45
def test_maintenance_charger_ignored(): assert waiting_minutes([{'status':'maintenance','remaining_minutes':0}],0)==10_000
def test_energy_formula(): assert energy_required(60,20,80)==36
def test_charge_time_efficiency(): assert charging_minutes(60,20,80,60)==40
def test_target_100_adds_taper(): assert charging_minutes(60,20,100,60)>charging_minutes(60,20,80,60)
def test_location_coordinates(): assert parse_location('19.076,72.878')[:2]==(19.076,72.878)
def test_astar_shortest_path():
    graph={'a':{'b':2,'c':1},'b':{'a':2,'d':1},'c':{'a':1,'d':5},'d':{'b':1,'c':5}}
    coords={x:(0,0) for x in graph}; path,cost=astar(graph,coords,'a','d')
    assert path==['a','b','d'] and cost==3
