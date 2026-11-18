from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
import config
from models.database import get_db, close_db, init_db, rows_to_dicts
from services.distance import parse_coordinates, haversine_km
from services.recommendation import recommend
from services.reviews import rating_summary, reliability_summary
from services.availability import station_status, counts
from seed import seed
from admin_routes import admin_bp, ensure_admin
from registration_routes import registration_bp
from services.registration import facilities_from_json, FACILITIES
from services.geocoding import geocode_location, geocode_candidates, AmbiguousLocation, LocationNotFound, GeocodingUnavailable

def create_app(test_config=None):
    app=Flask(__name__)
    app.config.from_mapping(SECRET_KEY=config.SECRET_KEY,DATABASE=str(config.DATABASE),SEARCH_RADIUS_KM=config.SEARCH_RADIUS_KM)
    if test_config: app.config.update(test_config)
    app.teardown_appcontext(close_db)
    init_db(app)
    ensure_admin(app)
    app.register_blueprint(admin_bp)
    app.register_blueprint(registration_bp)
    if not test_config or not test_config.get("TESTING"):
        seed()

    def payload(): return request.get_json(silent=True) or request.form
    def validate_search(data):
        try:
            capacity=float(data.get('capacity','')); current=float(data.get('current','')); target=float(data.get('target',''))
            radius=float(data.get('radius',app.config['SEARCH_RADIUS_KM']))
        except (ValueError,TypeError): raise ValueError('Battery values and radius must be numbers.')
        if capacity<=0: raise ValueError('Battery capacity must be greater than 0 kWh.')
        if not 0<=current<=100 or not 0<=target<=100: raise ValueError('Battery percentages must be between 0 and 100.')
        if target<current: raise ValueError('Target battery cannot be lower than current battery.')
        if radius<=0 or radius>100: raise ValueError('Search radius must be between 1 and 100 km.')
        location=str(data.get('location','')).strip()
        if not location and data.get('latitude') in (None,''): raise ValueError('Please enter a valid location.')
        coordinates=parse_coordinates(location,data.get('latitude'),data.get('longitude'))
        if coordinates:
            lat,lon=coordinates
            label=str(data.get('resolved_location') or ('Current location' if location.lower()=='current location' else f'{lat:.5f}, {lon:.5f}'))
        else:
            resolved=geocode_location(location,get_db())
            lat,lon,label=resolved['latitude'],resolved['longitude'],resolved['name']
        return capacity,current,target,radius,(lat,lon),label
    def run_search(data):
        capacity,current,target,radius,user,label=validate_search(data); db=get_db()
        all_stations=db.execute("SELECT * FROM stations WHERE status!='inactive'").fetchall()
        nearby=[s for s in all_stations if haversine_km(*user,s['latitude'],s['longitude'])<=radius]
        ranked=recommend(db,nearby,user,capacity,current,target) if nearby else []
        return ranked,{"capacity":capacity,"current":current,"target":target,"radius":radius,"latitude":user[0],"longitude":user[1],"label":label}

    @app.get('/')
    def index(): return render_template('index.html')
    @app.get('/add-station')
    def add_station_alias(): return redirect(url_for('admin.add_station'))
    @app.get('/manage-stations')
    def manage_stations_alias(): return redirect(url_for('admin.stations'))
    @app.post('/search')
    def search():
        data=request.form
        if request.form.get('location_choice'):
            try:
                choice=__import__('json').loads(request.form['location_choice']); data=request.form.to_dict(flat=True)
                data.update(latitude=choice['latitude'],longitude=choice['longitude'],resolved_location=choice['name'])
            except (ValueError,KeyError,TypeError): flash('Please select a valid location.','error'); return redirect(url_for('index'))
        try: ranked,query=run_search(data)
        except AmbiguousLocation as e:
            return render_template('location_select.html',choices=e.choices,search=request.form),409
        except LocationNotFound as e: flash(str(e),'error'); return redirect(url_for('index'))
        except GeocodingUnavailable: flash('Location service is temporarily unavailable. Please try again or enter coordinates manually.','error'); return redirect(url_for('index'))
        except ValueError as e: flash(str(e),'error'); return redirect(url_for('index'))
        return render_template('results.html',stations=ranked,recommended=next((x for x in ranked if x['eligible']),None),query=query,weights=config.RECOMMENDATION_WEIGHTS)
    @app.get('/station/<int:station_id>')
    def station(station_id):
        db=get_db(); row=db.execute('SELECT * FROM stations WHERE station_id=?',(station_id,)).fetchone()
        if not row: return render_template('404.html'),404
        s=dict(row); chargers=rows_to_dicts(db.execute('SELECT * FROM chargers WHERE station_id=?',(station_id,)))
        reviews=rows_to_dicts(db.execute('SELECT * FROM reviews WHERE station_id=? ORDER BY created_at DESC',(station_id,)))
        return render_template('station.html',station=s,chargers=chargers,reviews=reviews,status=station_status(s),counts=counts(chargers),rating=rating_summary(db,station_id),reliability=reliability_summary(db,station_id),facilities=facilities_from_json(s.get('facilities')),facility_labels=FACILITIES)
    @app.post('/review/<int:station_id>')
    def review(station_id):
        db=get_db(); data=payload()
        try: rating=int(data.get('rating',0))
        except (ValueError,TypeError): rating=0
        comment=str(data.get('comment','')).strip()
        if rating not in range(1,6): flash('Rating must be from 1 to 5.','error'); return redirect(url_for('station',station_id=station_id))
        if len(comment)>500: flash('Comment must be 500 characters or fewer.','error'); return redirect(url_for('station',station_id=station_id))
        db.execute('INSERT INTO reviews(station_id,rating,comment,created_at,verification_status) VALUES(?,?,?,?,?)',(station_id,rating,comment,datetime.now(timezone.utc).isoformat(),'user'))
        working=data.get('working')
        if working in ('working','not_working','maintenance','charger_available','long_wait','station_not_found'):
            db.execute('INSERT INTO reports(station_id,report_type,created_at) VALUES(?,?,?)',(station_id,working,datetime.now(timezone.utc).isoformat()))
            db.execute('UPDATE stations SET last_verified=? WHERE station_id=?',(datetime.now(timezone.utc).isoformat(),station_id))
        db.commit(); flash('Thanks — your review was saved and the rating was recalculated.','success')
        if request.is_json: return jsonify({"ok":True,"rating":rating_summary(db,station_id)}),201
        return redirect(url_for('station',station_id=station_id))
    @app.get('/api/stations')
    def api_stations(): return jsonify(rows_to_dicts(get_db().execute("SELECT * FROM stations WHERE status!='inactive'")))
    @app.get('/api/stations/<int:station_id>')
    @app.get('/api/station/<int:station_id>')
    def api_station(station_id):
        db=get_db(); row=db.execute('SELECT * FROM stations WHERE station_id=?',(station_id,)).fetchone()
        if not row:return jsonify(error='Station not found'),404
        s=dict(row); s['chargers']=rows_to_dicts(db.execute('SELECT * FROM chargers WHERE station_id=?',(station_id,))); s['rating']=rating_summary(db,station_id); s['reliability']=reliability_summary(db,station_id); s['status']=station_status(s)
        return jsonify(s)
    @app.post('/api/recommend')
    def api_recommend():
        try: ranked,query=run_search(payload())
        except AmbiguousLocation as e:return jsonify(error='Location is ambiguous.',choices=e.choices),409
        except LocationNotFound as e:return jsonify(error=str(e)),404
        except GeocodingUnavailable:return jsonify(error='Location service is temporarily unavailable.'),503
        except ValueError as e:return jsonify(error=str(e)),400
        return jsonify(query=query,availability_notice='Demo / Simulated Availability',stations=ranked)
    @app.get('/api/geocode')
    def api_geocode():
        try: return jsonify(query=request.args.get('q',''),choices=geocode_candidates(request.args.get('q',''),get_db()))
        except LocationNotFound as e:return jsonify(error=str(e),choices=[]),404
        except GeocodingUnavailable:return jsonify(error='Location service is temporarily unavailable.'),503
        except ValueError as e:return jsonify(error=str(e)),400
    @app.get('/api/reviews/<int:station_id>')
    def api_reviews(station_id): return jsonify(rows_to_dicts(get_db().execute('SELECT * FROM reviews WHERE station_id=? ORDER BY created_at DESC',(station_id,))))
    @app.get('/dashboard')
    def dashboard():
        db=get_db(); stations=rows_to_dicts(db.execute("SELECT * FROM stations WHERE status!='inactive'")); chargers=rows_to_dicts(db.execute('SELECT * FROM chargers'))
        stats={"stations":len(stations),"open":sum(station_status(s)['is_open'] for s in stations),"available":sum(c['status']=='available' for c in chargers),"occupied":sum(c['status']=='occupied' for c in chargers),"maintenance":sum(c['status']=='maintenance' for c in chargers)}
        return render_template('dashboard.html',stats=stats,stations=stations)
    return app

app=create_app()
if __name__=='__main__': app.run(host='0.0.0.0',port=5000,debug=True)
