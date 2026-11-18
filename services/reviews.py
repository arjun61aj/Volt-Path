from datetime import datetime, timezone, timedelta
from config import POSITIVE_REPORTS, NEGATIVE_REPORTS

def rating_summary(db, station_id):
    row=db.execute("SELECT AVG(rating) average, COUNT(*) count FROM reviews WHERE station_id=?",(station_id,)).fetchone()
    return {"average":round(row["average"],1) if row["average"] is not None else None,"count":row["count"]}

def reliability_summary(db, station_id):
    # Bayesian smoothing (8 virtual positive + 2 negative reports) prevents one report dominating.
    reports=db.execute("SELECT report_type FROM reports WHERE station_id=?",(station_id,)).fetchall()
    positive=sum(r[0] in POSITIVE_REPORTS for r in reports); negative=sum(r[0] in NEGATIVE_REPORTS for r in reports)
    return {"score":round((positive+8)/(positive+negative+10)*100),"reports":len(reports)}
