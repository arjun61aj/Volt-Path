from services.availability import station_status, counts, waiting_minutes
from services.charging_time import charging_minutes
from services.distance import travel_minutes
from services.reviews import rating_summary, reliability_summary
from services.astar import build_station_graph, astar
from config import RECOMMENDATION_WEIGHTS

def _normalize(values):
    lo,hi=min(values),max(values)
    return [0.0 if hi==lo else (v-lo)/(hi-lo) for v in values]

def recommend(db, stations, user, capacity, current, target):
    graph,coords=build_station_graph(user,stations); results=[]
    for srow in stations:
        s=dict(srow); sid=s["station_id"]
        chargers=[dict(x) for x in db.execute("SELECT * FROM chargers WHERE station_id=?",(sid,))]
        status=station_status(s); availability=counts(chargers)
        usable=[c for c in chargers if c["status"] not in {"maintenance","offline"}]
        best=max((c["power_kw"] for c in usable),default=0)
        path,distance=astar(graph,coords,"user",f"s{sid}")
        wait=waiting_minutes(chargers,s["queue_length"])
        charge=charging_minutes(capacity,current,target,best) if best else 10_000
        travel=travel_minutes(distance); rating=rating_summary(db,sid); reliable=reliability_summary(db,sid)
        eligible=status["is_open"] and s.get("status","active")=="active" and s["maintenance_status"]!="maintenance" and bool(usable)
        results.append({**s,"status":status,"chargers":chargers,"counts":availability,"best_power_kw":best,
          "path":path,"distance_km":round(distance,1),"travel_minutes":travel,"waiting_minutes":wait,
          "charging_minutes":charge,"total_minutes":travel+wait+charge,"rating":rating,"reliability":reliable,
          "eligible":eligible})
    # Multi-factor normalized score among candidates. Closed/maintenance remain visible but ineligible.
    finite=[r for r in results if r["eligible"]]
    if finite:
        fields={"travel":[r["travel_minutes"] for r in finite],"waiting":[r["waiting_minutes"] for r in finite],
          "availability":[1-r["counts"]["available"]/max(1,r["counts"]["total"]) for r in finite],
          "charging":[r["charging_minutes"] for r in finite],"reliability":[100-r["reliability"]["score"] for r in finite],
          "rating":[5-(r["rating"]["average"] if r["rating"]["average"] is not None else 3) for r in finite]}
        normalized={k:_normalize(v) for k,v in fields.items()}
        for i,r in enumerate(finite):
            r["score"]=round(sum(RECOMMENDATION_WEIGHTS[k]*normalized[k][i] for k in RECOMMENDATION_WEIGHTS)*100,1)
    for r in results:
        if not r["eligible"]: r["score"]=999.0
    return sorted(results,key=lambda x:(x["score"],x["total_minutes"]))
