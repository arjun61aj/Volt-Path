import re
import sqlite3
import pytest
from app import create_app

def make_app(path): return create_app({'TESTING':True,'DATABASE':str(path),'SECRET_KEY':'test-secret'})
def token(html): return re.search(rb'name="_csrf" value="([^"]+)"',html).group(1).decode()
def login(client):
    t=token(client.get('/admin/login').data)
    r=client.post('/admin/login',data={'_csrf':t,'username':'admin','password':'ChangeMe123!'},follow_redirects=True)
    assert r.status_code==200 and b'Good day' in r.data

def form(csrf,**changes):
    data={'_csrf':csrf,'name':'Test Charge Point','address':'1 Test Road','city':'Mumbai','state':'Maharashtra','pincode':'400001','latitude':'19.076','longitude':'72.8777','is_24_hours':'1','opening_time':'','closing_time':'','status':'active','queue_length':'0','contact_number':'+91 9876543210','email':'ops@example.com','description':'Test station','charger_type[]':['DC Fast Charger','AC Charger'],'power_kw[]':['60','22'],'connector_type[]':['CCS2','Type 2'],'charger_status[]':['available','maintenance'],'remaining_minutes[]':['0','0']}
    data.update(changes); return data
@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'v2.db'; app=make_app(path); client=app.test_client(); login(client); return app,client,path

def add(client,**changes):
    t=token(client.get('/admin/stations/add').data); return client.post('/admin/stations/add',data=form(t,**changes))

def test_admin_route_requires_auth(tmp_path): assert make_app(tmp_path/'x.db').test_client().get('/admin/stations/add').status_code==302
def test_successfully_adds_station_and_multiple_chargers(setup):
    app,c,path=setup; r=add(c); assert r.status_code==200 and b'Station added successfully' in r.data
    db=sqlite3.connect(path); assert db.execute('SELECT COUNT(*) FROM stations').fetchone()[0]==1; assert db.execute('SELECT COUNT(*) FROM chargers').fetchone()[0]==2
@pytest.mark.parametrize(('field','value','message'),[('latitude','91','Latitude must be between'),('longitude','181','Longitude must be between')])
def test_invalid_coordinates(setup,field,value,message):
    _,c,_=setup; r=add(c,**{field:value}); assert r.status_code==422 and message.encode() in r.data
def test_missing_station_name(setup):
    _,c,_=setup; r=add(c,name=''); assert r.status_code==422 and b'Station name is required' in r.data
def test_missing_hours_for_non_24_hour_station(setup):
    _,c,_=setup; r=add(c,is_24_hours='',opening_time='',closing_time=''); assert r.status_code==422 and b'Opening time is required' in r.data
def test_24_hour_station_is_stored(setup):
    _,c,path=setup; assert add(c).status_code==200
    db=sqlite3.connect(path); assert db.execute('SELECT is_24_hours,opening_time FROM stations').fetchone()==(1,'00:00')
def test_duplicate_warning_then_continue(setup):
    _,c,path=setup; assert add(c).status_code==200
    r=add(c,name='Second Nearby Site'); assert r.status_code==409 and b'Possible duplicate station' in r.data
    t=token(r.data); payload=form(t,name='Second Nearby Site',force_duplicate='1'); assert c.post('/admin/stations/add',data=payload).status_code==200
    assert sqlite3.connect(path).execute('SELECT COUNT(*) FROM stations').fetchone()[0]==2
def test_new_station_appears_in_search_and_map(setup):
    _,c,_=setup; add(c,name='Map Search Station')
    r=c.post('/search',data={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5})
    assert r.status_code==200 and b'Map Search Station' in r.data and b'window.mapData' in r.data
def test_new_station_is_considered_by_recommendation_api(setup):
    _,c,_=setup; add(c,name='A Star Candidate')
    r=c.post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5})
    assert r.status_code==200 and r.json['stations'][0]['name']=='A Star Candidate' and r.json['stations'][0]['path']
def test_edit_updates_station_and_chargers(setup):
    _,c,path=setup; add(c); db=sqlite3.connect(path); sid=db.execute('SELECT station_id FROM stations').fetchone()[0]
    page=c.get(f'/admin/stations/{sid}/edit'); t=token(page.data)
    r=c.post(f'/admin/stations/{sid}/edit',data=form(t,**{'name':'Edited Station','charger_type[]':['DC'],'power_kw[]':['120'],'connector_type[]':['CCS2'],'charger_status[]':['available'],'remaining_minutes[]':['0']}))
    assert r.status_code==302
    db=sqlite3.connect(path); assert db.execute('SELECT name FROM stations').fetchone()[0]=='Edited Station'; assert db.execute('SELECT COUNT(*) FROM chargers').fetchone()[0]==1
def test_deactivate_removes_from_user_recommendations(setup):
    _,c,path=setup; add(c,name='Deactivate Me'); sid=sqlite3.connect(path).execute('SELECT station_id FROM stations').fetchone()[0]
    page=c.get('/admin/stations'); t=token(page.data); assert c.post(f'/admin/stations/{sid}/deactivate',data={'_csrf':t}).status_code==302
    r=c.post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}); assert r.json['stations']==[]
def test_new_station_starts_without_reviews_or_verification(setup):
    _,c,path=setup; add(c); db=sqlite3.connect(path)
    assert db.execute('SELECT verification_status FROM stations').fetchone()[0]=='unverified'; assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0
def test_station_persists_across_app_restart(setup):
    _,c,path=setup; add(c,name='Persistent Station')
    restarted=make_app(path); r=restarted.test_client().get('/api/stations')
    assert any(s['name']=='Persistent Station' for s in r.json)
def test_offline_charger_is_supported_but_not_usable(setup):
    _,c,path=setup; r=add(c,**{'name':'Offline Site','charger_type[]':['DC'],'power_kw[]':['60'],'connector_type[]':['CCS2'],'charger_status[]':['offline'],'remaining_minutes[]':['0']})
    assert r.status_code==200; db=sqlite3.connect(path); assert db.execute('SELECT status FROM chargers').fetchone()[0]=='offline'
