from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, session
from models.database import get_db, rows_to_dicts
from admin_routes import admin_required, require_csrf
from services.registration import parse_registration_form, registration_duplicates, tracking_token, facilities_json, facilities_from_json, FACILITIES
from services.station_management import now_iso

registration_bp=Blueprint('registration',__name__)

def _get_registration(registration_id):
    row=get_db().execute('SELECT * FROM station_registrations WHERE registration_id=?',(registration_id,)).fetchone()
    if not row: abort(404)
    return row

@registration_bp.route('/register-station',methods=['GET','POST'])
def register_station():
    if request.method=='GET': return render_template('registration/form.html',registration=None,chargers=[],facilities=[])
    require_csrf(); owner,station,chargers,facilities,errors=parse_registration_form(request.form)
    duplicates=[] if errors or request.form.get('force_duplicate')=='1' else registration_duplicates(get_db(),station['name'],station['latitude'],station['longitude'])
    submitted={**owner,**station}
    if errors or duplicates:
        return render_template('registration/form.html',registration=submitted,chargers=chargers,facilities=facilities,errors=errors,duplicates=duplicates),422 if errors else 409
    db=get_db(); token=tracking_token(); now=now_iso()
    try:
        with db:
            cur=db.execute('''INSERT INTO station_registrations(tracking_token,owner_name,company_name,owner_email,owner_phone,station_name,address,city,state,pincode,latitude,longitude,opening_time,closing_time,is_24_hours,description,facilities,queue_length,registration_status,submitted_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(token,owner['owner_name'],owner['company_name'],owner['owner_email'],owner['owner_phone'],station['name'],station['address'],station['city'],station['state'],station['pincode'],station['latitude'],station['longitude'],station['opening_time'],station['closing_time'],station['is_24_hours'],station['description'],facilities_json(facilities),station['queue_length'],'pending',now))
            rid=cur.lastrowid
            db.executemany('INSERT INTO registration_chargers(registration_id,charger_type,power_kw,connector_type,status,remaining_minutes) VALUES(?,?,?,?,?,?)',[(rid,c['charger_type'],c['power_kw'],c['connector_type'],c['status'],c['remaining_minutes']) for c in chargers])
    except Exception:
        db.rollback(); flash('Registration could not be submitted. No partial information was stored.','error'); return render_template('registration/form.html',registration=submitted,chargers=chargers,facilities=facilities),500
    return redirect(url_for('registration.registration_status_token',token=token))

@registration_bp.route('/registration-status',methods=['GET','POST'])
def registration_status_lookup():
    if request.method=='POST':
        require_csrf(); code=request.form.get('registration_id','').strip().upper(); email=request.form.get('email','').strip().lower()
        if not code.startswith('REG') or not code[3:].isdigit(): flash('Enter a valid registration ID such as REG00001.','error'); return render_template('registration/status_lookup.html')
        row=get_db().execute('SELECT tracking_token FROM station_registrations WHERE registration_id=? AND lower(owner_email)=?',(int(code[3:]),email)).fetchone()
        if not row: flash('No registration matched that ID and email.','error'); return render_template('registration/status_lookup.html')
        return redirect(url_for('registration.registration_status_token',token=row['tracking_token']))
    return render_template('registration/status_lookup.html')

@registration_bp.get('/registration/<token>')
def registration_status_token(token):
    row=get_db().execute('SELECT * FROM station_registrations WHERE tracking_token=?',(token,)).fetchone()
    if not row: abort(404)
    return render_template('registration/status.html',registration=dict(row))

@registration_bp.get('/admin/registrations')
@admin_required
def admin_registrations():
    status=request.args.get('status','pending')
    if status not in {'pending','approved','rejected','all'}: status='pending'
    sql='SELECT r.*,COUNT(c.registration_charger_id) charger_count FROM station_registrations r LEFT JOIN registration_chargers c ON c.registration_id=r.registration_id'
    params=()
    if status!='all': sql+=' WHERE r.registration_status=?'; params=(status,)
    sql+=' GROUP BY r.registration_id ORDER BY r.submitted_at DESC'
    return render_template('admin/registrations.html',registrations=get_db().execute(sql,params).fetchall(),filter_status=status)

@registration_bp.get('/admin/registrations/<int:registration_id>')
@admin_required
def admin_registration_detail(registration_id):
    row=_get_registration(registration_id); chargers=rows_to_dicts(get_db().execute('SELECT * FROM registration_chargers WHERE registration_id=?',(registration_id,)))
    return render_template('admin/registration_detail.html',registration=dict(row),chargers=chargers,facilities=facilities_from_json(row['facilities']),facility_labels=FACILITIES)

@registration_bp.post('/admin/registrations/<int:registration_id>/approve')
@admin_required
def approve_registration(registration_id):
    require_csrf(); db=get_db(); reg=_get_registration(registration_id)
    if reg['registration_status']!='pending': flash('Only pending registrations can be approved.','error'); return redirect(url_for('registration.admin_registration_detail',registration_id=registration_id))
    chargers=db.execute('SELECT * FROM registration_chargers WHERE registration_id=?',(registration_id,)).fetchall(); now=now_iso()
    try:
        with db:
            cur=db.execute('''INSERT INTO stations(name,latitude,longitude,address,city,state,pincode,opening_time,closing_time,is_24_hours,maintenance_status,status,queue_length,contact_number,email,description,facilities,verification_status,created_at,updated_at,created_by,data_source)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(reg['station_name'],reg['latitude'],reg['longitude'],reg['address'],reg['city'],reg['state'],reg['pincode'],reg['opening_time'],reg['closing_time'],reg['is_24_hours'],'operational','active',reg['queue_length'],None,None,reg['description'],reg['facilities'],'unverified',now,now,session['admin_username'],'operator_registration'))
            sid=cur.lastrowid
            db.executemany('INSERT INTO chargers(station_id,charger_type,power_kw,connector_type,status,remaining_minutes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',[(sid,c['charger_type'],c['power_kw'],c['connector_type'],c['status'],c['remaining_minutes'],now,now) for c in chargers])
            db.execute("UPDATE station_registrations SET registration_status='approved',station_id=?,reviewed_at=?,reviewed_by=?,rejection_reason=NULL WHERE registration_id=?",(sid,now,session['admin_username'],registration_id))
    except Exception:
        db.rollback(); flash('Approval failed. No station or partial charger data was created.','error'); return redirect(url_for('registration.admin_registration_detail',registration_id=registration_id))
    flash('Station approved successfully. It is now available to search, maps, A*, and recommendations.','success'); return redirect(url_for('registration.admin_registration_detail',registration_id=registration_id))

@registration_bp.post('/admin/registrations/<int:registration_id>/reject')
@admin_required
def reject_registration(registration_id):
    require_csrf(); db=get_db(); reg=_get_registration(registration_id)
    if reg['registration_status']!='pending': flash('Only pending registrations can be rejected.','error'); return redirect(url_for('registration.admin_registration_detail',registration_id=registration_id))
    reason=request.form.get('rejection_reason','').strip()[:500] or 'Registration details could not be verified.'; now=now_iso()
    db.execute("UPDATE station_registrations SET registration_status='rejected',rejection_reason=?,reviewed_at=?,reviewed_by=? WHERE registration_id=?",(reason,now,session['admin_username'],registration_id)); db.commit()
    flash('Registration rejected. No operational station was created.','success'); return redirect(url_for('registration.admin_registration_detail',registration_id=registration_id))
