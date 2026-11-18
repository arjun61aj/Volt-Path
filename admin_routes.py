import hmac, os, secrets
from functools import wraps
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models.database import get_db, rows_to_dicts
from services.station_management import parse_station_form, nearby_duplicate, now_iso
from services.availability import station_status

admin_bp=Blueprint('admin',__name__,url_prefix='/admin')

def ensure_admin(app):
    from models.database import connect
    username=os.getenv('ADMIN_USERNAME','admin')
    password=os.getenv('ADMIN_PASSWORD','ChangeMe123!')
    supplied_hash=os.getenv('ADMIN_PASSWORD_HASH')
    with connect(app.config['DATABASE']) as db:
        if not db.execute('SELECT 1 FROM admins WHERE username=?',(username,)).fetchone():
            db.execute('INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?)',(username,supplied_hash or generate_password_hash(password),now_iso()))

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('admin_id'):
            flash('Please sign in as an administrator.','error'); return redirect(url_for('admin.login',next=request.path))
        return fn(*args,**kwargs)
    return wrapped

def csrf_token():
    if '_csrf' not in session: session['_csrf']=secrets.token_urlsafe(24)
    return session['_csrf']

def require_csrf():
    if not hmac.compare_digest(str(session.get('_csrf','')),str(request.form.get('_csrf',''))): abort(400,'Invalid or expired form token.')

@admin_bp.app_context_processor
def inject_admin_helpers(): return {'csrf_token':csrf_token,'is_admin':bool(session.get('admin_id'))}

@admin_bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        require_csrf(); username=request.form.get('username','').strip(); password=request.form.get('password','')
        row=get_db().execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone()
        if row and check_password_hash(row['password_hash'],password):
            session.clear(); session['admin_id']=row['admin_id']; session['admin_username']=row['username']; session['_csrf']=secrets.token_urlsafe(24)
            return redirect(request.args.get('next') or url_for('admin.dashboard'))
        flash('Invalid administrator username or password.','error')
    return render_template('admin/login.html')

@admin_bp.post('/logout')
@admin_required
def logout(): require_csrf(); session.clear(); return redirect(url_for('index'))

@admin_bp.get('/')
@admin_required
def dashboard():
    db=get_db(); stations=rows_to_dicts(db.execute("SELECT * FROM stations WHERE status!='inactive'"))
    stats={'total':len(stations),'open':sum(station_status(s)['is_open'] for s in stations),'closed':sum(not station_status(s)['is_open'] for s in stations),'maintenance':sum(s['status']=='maintenance' for s in stations),
      'unverified':sum(s['verification_status']=='unverified' for s in stations),'reviews':db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],'reports':db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
      'pending_registrations':db.execute("SELECT COUNT(*) FROM station_registrations WHERE registration_status='pending'").fetchone()[0],
      'approved_registrations':db.execute("SELECT COUNT(*) FROM station_registrations WHERE registration_status='approved'").fetchone()[0],
      'rejected_registrations':db.execute("SELECT COUNT(*) FROM station_registrations WHERE registration_status='rejected'").fetchone()[0]}
    return render_template('admin/dashboard.html',stats=stats)

@admin_bp.get('/stations')
@admin_required
def stations():
    rows=get_db().execute('SELECT s.*,COUNT(c.charger_id) charger_count FROM stations s LEFT JOIN chargers c ON c.station_id=s.station_id GROUP BY s.station_id ORDER BY s.station_id DESC').fetchall()
    return render_template('admin/manage.html',stations=rows)

@admin_bp.route('/stations/add',methods=['GET','POST'])
@admin_required
def add_station():
    if request.method=='GET': return render_template('admin/station_form.html',mode='add',station=None,chargers=[])
    require_csrf(); station,chargers,errors=parse_station_form(request.form)
    duplicates=[] if errors or request.form.get('force_duplicate')=='1' else nearby_duplicate(get_db(),station['latitude'],station['longitude'])
    if errors or duplicates:
        return render_template('admin/station_form.html',mode='add',station=station,chargers=chargers,errors=errors,duplicates=duplicates),422 if errors else 409
    db=get_db(); now=now_iso()
    try:
        with db:
            cur=db.execute('''INSERT INTO stations(name,latitude,longitude,address,city,state,pincode,opening_time,closing_time,is_24_hours,maintenance_status,status,queue_length,contact_number,email,description,verification_status,created_at,updated_at,created_by,data_source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(station['name'],station['latitude'],station['longitude'],station['address'],station['city'],station['state'],station['pincode'],station['opening_time'],station['closing_time'],station['is_24_hours'],station['maintenance_status'],station['status'],station['queue_length'],station['contact_number'],station['email'],station['description'],'unverified',now,now,session['admin_username'],'admin'))
            sid=cur.lastrowid
            db.executemany('INSERT INTO chargers(station_id,charger_type,power_kw,connector_type,status,remaining_minutes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',[(sid,c['charger_type'],c['power_kw'],c['connector_type'],c['status'],c['remaining_minutes'],now,now) for c in chargers])
    except Exception:
        current_app.logger.exception('Station transaction failed'); flash('The station could not be saved. No partial data was stored.','error'); return render_template('admin/station_form.html',mode='add',station=station,chargers=chargers),500
    return render_template('admin/success.html',station_id=sid,station=station,charger_count=len(chargers))

@admin_bp.route('/stations/<int:station_id>/edit',methods=['GET','POST'])
@admin_required
def edit_station(station_id):
    db=get_db(); row=db.execute('SELECT * FROM stations WHERE station_id=?',(station_id,)).fetchone()
    if not row: abort(404)
    if request.method=='GET':
        return render_template('admin/station_form.html',mode='edit',station=dict(row),chargers=rows_to_dicts(db.execute('SELECT * FROM chargers WHERE station_id=?',(station_id,))))
    require_csrf(); station,chargers,errors=parse_station_form(request.form)
    duplicates=[] if errors or request.form.get('force_duplicate')=='1' else nearby_duplicate(db,station['latitude'],station['longitude'],station_id)
    if errors or duplicates: return render_template('admin/station_form.html',mode='edit',station={**dict(row),**station},chargers=chargers,errors=errors,duplicates=duplicates),422 if errors else 409
    now=now_iso()
    with db:
        db.execute('''UPDATE stations SET name=?,latitude=?,longitude=?,address=?,city=?,state=?,pincode=?,opening_time=?,closing_time=?,is_24_hours=?,maintenance_status=?,status=?,queue_length=?,contact_number=?,email=?,description=?,updated_at=? WHERE station_id=?''',(station['name'],station['latitude'],station['longitude'],station['address'],station['city'],station['state'],station['pincode'],station['opening_time'],station['closing_time'],station['is_24_hours'],station['maintenance_status'],station['status'],station['queue_length'],station['contact_number'],station['email'],station['description'],now,station_id))
        db.execute('DELETE FROM chargers WHERE station_id=?',(station_id,))
        db.executemany('INSERT INTO chargers(station_id,charger_type,power_kw,connector_type,status,remaining_minutes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',[(station_id,c['charger_type'],c['power_kw'],c['connector_type'],c['status'],c['remaining_minutes'],now,now) for c in chargers])
    flash('Station and charger information updated.','success'); return redirect(url_for('admin.stations'))

@admin_bp.post('/stations/<int:station_id>/deactivate')
@admin_required
def deactivate_station(station_id):
    require_csrf(); db=get_db(); db.execute("UPDATE stations SET status='inactive',updated_at=? WHERE station_id=?",(now_iso(),station_id)); db.commit(); flash('Station deactivated. Historical data was retained.','success'); return redirect(url_for('admin.stations'))

@admin_bp.post('/stations/<int:station_id>/verify')
@admin_required
def verify_station(station_id):
    require_csrf(); now=now_iso(); db=get_db(); db.execute("UPDATE stations SET verification_status='verified',verified_by=?,verified_at=?,last_verified=?,updated_at=? WHERE station_id=?",(session['admin_username'],now,now,now,station_id)); db.commit(); flash('Station verified.','success'); return redirect(url_for('admin.stations'))

@admin_bp.get('/reviews')
@admin_required
def reviews():
    rows=get_db().execute('SELECT r.*,s.name station_name FROM reviews r JOIN stations s ON s.station_id=r.station_id ORDER BY r.created_at DESC').fetchall(); return render_template('admin/community.html',title='Reviews',rows=rows,kind='reviews')
@admin_bp.get('/reports')
@admin_required
def reports():
    rows=get_db().execute('SELECT r.*,s.name station_name FROM reports r JOIN stations s ON s.station_id=r.station_id ORDER BY r.created_at DESC').fetchall(); return render_template('admin/community.html',title='Status reports',rows=rows,kind='reports')
