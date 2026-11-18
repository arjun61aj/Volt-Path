from app import create_app
def make(tmp_path): return create_app({'TESTING':True,'DATABASE':str(tmp_path/'test.db'),'SECRET_KEY':'test'})
def test_homepage(tmp_path):
    r=make(tmp_path).test_client().get('/'); assert r.status_code==200 and b'Spend less time' in r.data
def test_invalid_battery_api(tmp_path):
    r=make(tmp_path).test_client().post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':80,'target':20,'radius':20})
    assert r.status_code==400 and 'Target battery' in r.json['error']
def test_no_nearby_station(tmp_path):
    r=make(tmp_path).test_client().post('/api/recommend',json={'location':'19.076,72.878','capacity':60,'current':20,'target':80,'radius':2})
    assert r.status_code==200 and r.json['stations']==[]
