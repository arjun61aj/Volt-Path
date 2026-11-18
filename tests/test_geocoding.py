import sqlite3
import pytest
import services.geocoding as geo
from app import create_app

CITIES=['Mumbai','Pune','Delhi','Bangalore','Hyderabad','Chennai','Kolkata','Nashik','Nagpur','Ahmedabad','London','Dubai']
def cache_db():
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE geocoding_cache(query_key TEXT PRIMARY KEY,query_text TEXT,response_json TEXT,created_at TEXT)'); return db

@pytest.mark.parametrize('name',CITIES)
def test_any_provider_resolved_city_is_supported(monkeypatch,name):
    monkeypatch.setattr(geo,'_request',lambda q:[{'display_name':f'{q}, resolved by provider','lat':'18.5204','lon':'73.8567','importance':0.8,'type':'city'}])
    result=geo.geocode_location(name,cache_db())
    assert result['name'].startswith(name) and result['latitude']==18.5204

def test_cache_prevents_repeat_provider_calls(monkeypatch):
    calls=[]
    monkeypatch.setattr(geo,'_request',lambda q:(calls.append(q) or [{'display_name':'Pune, Maharashtra, India','lat':'18.52','lon':'73.85','importance':.8}]))
    db=cache_db(); geo.geocode_location('Pune',db); geo.geocode_location('  pune ',db)
    assert calls==['Pune']

def test_unknown_location(monkeypatch):
    monkeypatch.setattr(geo,'_request',lambda q:[])
    with pytest.raises(geo.LocationNotFound): geo.geocode_location('RandomXYZ123',cache_db())

def test_similar_results_require_user_selection(monkeypatch):
    monkeypatch.setattr(geo,'_request',lambda q:[
      {'display_name':'Springfield, Illinois, USA','lat':'39.78','lon':'-89.64','importance':.55},
      {'display_name':'Springfield, Massachusetts, USA','lat':'42.10','lon':'-72.59','importance':.53}])
    with pytest.raises(geo.AmbiguousLocation) as error: geo.geocode_location('Springfield',cache_db())
    assert len(error.value.choices)==2

def test_named_route_uses_resolved_coordinates_and_label(tmp_path,monkeypatch):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'named.db'),'SECRET_KEY':'test'})
    monkeypatch.setattr('app.geocode_location',lambda q,db:{'name':'Pune, Maharashtra, India','latitude':18.5204,'longitude':73.8567})
    r=app.test_client().post('/api/recommend',json={'location':'Pune','capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==200 and r.json['query']['label']=='Pune, Maharashtra, India' and r.json['query']['latitude']==18.5204

def test_coordinate_input_bypasses_geocoder(tmp_path,monkeypatch):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'coords.db'),'SECRET_KEY':'test'})
    monkeypatch.setattr('app.geocode_location',lambda *x:(_ for _ in ()).throw(AssertionError('geocoder must not run')))
    r=app.test_client().post('/api/recommend',json={'location':'18.5204, 73.8567','capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==200 and r.json['query']['latitude']==18.5204

def test_html_ambiguous_location_page(tmp_path,monkeypatch):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'amb.db'),'SECRET_KEY':'test'})
    choices=[{'name':'Springfield, Illinois, USA','latitude':39.78,'longitude':-89.64,'importance':.5}]
    def ambiguous(*args): raise geo.AmbiguousLocation('Springfield',choices)
    monkeypatch.setattr('app.geocode_location',ambiguous)
    r=app.test_client().post('/search',data={'location':'Springfield','capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==409 and b'Select your location' in r.data and b'Springfield, Illinois' in r.data

def test_full_address_with_comma_is_geocoded_not_rejected(tmp_path,monkeypatch):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'address.db'),'SECRET_KEY':'test'})
    monkeypatch.setattr('app.geocode_location',lambda q,db:{'name':'Pune, Maharashtra, India','latitude':18.5204,'longitude':73.8567})
    r=app.test_client().post('/api/recommend',json={'location':'Pune, Maharashtra','capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==200 and r.json['query']['label']=='Pune, Maharashtra, India'

def test_geocoding_unavailable_returns_503(tmp_path,monkeypatch):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'down.db'),'SECRET_KEY':'test'})
    def down(*args): raise geo.GeocodingUnavailable('down')
    monkeypatch.setattr('app.geocode_location',down)
    r=app.test_client().post('/api/recommend',json={'location':'Pune','capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==503 and 'temporarily unavailable' in r.json['error']

def test_selected_ambiguous_choice_continues_without_second_geocode(tmp_path,monkeypatch):
    import json
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'selected.db'),'SECRET_KEY':'test'})
    monkeypatch.setattr('app.geocode_location',lambda *x:(_ for _ in ()).throw(AssertionError('must use selected coordinates')))
    choice={'name':'Springfield, Illinois, USA','latitude':39.7817,'longitude':-89.6501}
    r=app.test_client().post('/search',data={'location':'Springfield','location_choice':json.dumps(choice),'capacity':60,'current':20,'target':80,'radius':20})
    assert r.status_code==200 and b'SPRINGFIELD, ILLINOIS, USA' in r.data
