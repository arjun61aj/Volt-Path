import re, sqlite3
import pytest
from app import create_app

def make(path): return create_app({'TESTING':True,'DATABASE':str(path),'SECRET_KEY':'v3-test'})
def csrf(data): return re.search(rb'name="_csrf" value="([^"]+)"',data).group(1).decode()
def payload(token,**changes):
    p={'_csrf':token,'owner_name':'Operator One','company_name':'ChargeCo','owner_email':'owner@example.com','owner_phone':'+91 9876543210','name':'Registered EV Hub','address':'10 Registration Road','city':'Mumbai','state':'Maharashtra','pincode':'400001','latitude':'19.0762','longitude':'72.8780','is_24_hours':'1','opening_time':'','closing_time':'','total_chargers':'2','queue_length':'1','description':'Parking and cafe','parking':'1','cafe':'1','charger_type[]':['DC Fast Charger','AC'],'power_kw[]':['60','22'],'connector_type[]':['CCS2','Type 2'],'charger_status[]':['available','occupied'],'remaining_minutes[]':['0','18']}
    p.update(changes); return p
def submit(client,**changes):
    t=csrf(client.get('/register-station').data); return client.post('/register-station',data=payload(t,**changes))
def login(client):
    t=csrf(client.get('/admin/login').data); r=client.post('/admin/login',data={'_csrf':t,'username':'admin','password':'ChangeMe123!'}); assert r.status_code==302
def approve(client,rid):
    login(client); t=csrf(client.get(f'/admin/registrations/{rid}').data); return client.post(f'/admin/registrations/{rid}/approve',data={'_csrf':t})
@pytest.fixture
def env(tmp_path):
    path=tmp_path/'v3.db'; app=make(path); return app,app.test_client(),path

def test_registration_form_is_public(env): assert env[1].get('/register-station').status_code==200
def test_register_generates_pending_registration_id(env):
    _,c,path=env; r=submit(c); assert r.status_code==302 and '/registration/' in r.headers['Location']
    db=sqlite3.connect(path); row=db.execute('SELECT registration_id,registration_status FROM station_registrations').fetchone(); assert row==(1,'pending')
def test_registration_stores_multiple_proposed_chargers(env):
    _,c,path=env; submit(c); assert sqlite3.connect(path).execute('SELECT COUNT(*) FROM registration_chargers').fetchone()[0]==2
def test_registration_validation_does_not_partially_store(env):
    _,c,path=env; r=submit(c,latitude='99'); assert r.status_code==422 and b'Latitude must be between' in r.data
    db=sqlite3.connect(path); assert db.execute('SELECT COUNT(*) FROM station_registrations').fetchone()[0]==0 and db.execute('SELECT COUNT(*) FROM registration_chargers').fetchone()[0]==0
def test_declared_charger_count_must_match_records(env):
    _,c,_=env; r=submit(c,total_chargers='3'); assert r.status_code==422 and b'must match' in r.data
def test_duplicate_registration_requires_confirmation(env):
    _,c,path=env; submit(c); r=submit(c,name='Another Nearby Hub'); assert r.status_code==409 and b'Possible duplicate station' in r.data
    t=csrf(r.data); assert c.post('/register-station',data=payload(t,name='Another Nearby Hub',force_duplicate='1')).status_code==302
    assert sqlite3.connect(path).execute('SELECT COUNT(*) FROM station_registrations').fetchone()[0]==2
def test_pending_registration_is_absent_from_search_map_and_astar(env):
    _,c,_=env; submit(c)
    r=c.post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}); assert r.json['stations']==[]
    html=c.post('/search',data={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}).data; assert b'Registered EV Hub' not in html
def test_only_admin_can_approve_or_reject(env):
    _,c,_=env; submit(c); assert c.post('/admin/registrations/1/approve').status_code==302; assert c.post('/admin/registrations/1/reject').status_code==302
def test_approval_atomically_creates_station_and_chargers(env):
    _,c,path=env; submit(c); r=approve(c,1); assert r.status_code==302
    db=sqlite3.connect(path); assert db.execute('SELECT registration_status,station_id FROM station_registrations').fetchone()==('approved',1); assert db.execute('SELECT COUNT(*) FROM stations').fetchone()[0]==1; assert db.execute('SELECT COUNT(*) FROM chargers').fetchone()[0]==2
def test_approved_station_appears_in_search_map_and_astar(env):
    _,c,_=env; submit(c); approve(c,1)
    r=c.post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}); assert r.json['stations'][0]['name']=='Registered EV Hub' and r.json['stations'][0]['path']
    html=c.post('/search',data={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}).data; assert b'Registered EV Hub' in html and b'window.mapData' in html
def test_existing_wait_and_charge_calculations_apply_after_approval(env):
    _,c,_=env; submit(c); approve(c,1)
    s=c.post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':5}).json['stations'][0]
    assert s['charging_minutes']>0 and s['waiting_minutes']>=0 and s['total_minutes']==s['travel_minutes']+s['waiting_minutes']+s['charging_minutes']
def test_approved_station_has_no_fake_reviews_and_is_unverified(env):
    _,c,path=env; submit(c); approve(c,1); db=sqlite3.connect(path)
    assert db.execute('SELECT verification_status FROM stations').fetchone()[0]=='unverified'; assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0
def test_admin_rejection_stores_reason_and_creates_no_station(env):
    _,c,path=env; submit(c); login(c); t=csrf(c.get('/admin/registrations/1').data)
    c.post('/admin/registrations/1/reject',data={'_csrf':t,'rejection_reason':'Location could not be verified.'})
    db=sqlite3.connect(path); assert db.execute('SELECT registration_status,rejection_reason FROM station_registrations').fetchone()==('rejected','Location could not be verified.'); assert db.execute('SELECT COUNT(*) FROM stations').fetchone()[0]==0
def test_applicant_can_lookup_status_with_id_and_matching_email(env):
    _,c,_=env; submit(c); t=csrf(c.get('/registration-status').data)
    r=c.post('/registration-status',data={'_csrf':t,'registration_id':'REG00001','email':'owner@example.com'}); assert r.status_code==302 and '/registration/' in r.headers['Location']
def test_registration_and_approval_persist_after_restart(env):
    _,c,path=env; submit(c); approve(c,1); restarted=make(path)
    assert any(x['name']=='Registered EV Hub' for x in restarted.test_client().get('/api/stations').json)
