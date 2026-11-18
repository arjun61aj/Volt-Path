from math import ceil
from config import CHARGER_EFFICIENCY

def energy_required(capacity, current, target): return capacity * (target-current) / 100

def charging_minutes(capacity, current, target, power_kw, vehicle_max_kw=None):
    effective_power=min(power_kw, vehicle_max_kw) if vehicle_max_kw else power_kw
    # 90% efficiency; a modest taper factor above 80% approximates charging curves.
    energy=energy_required(capacity,current,target)
    base=energy/(effective_power*CHARGER_EFFICIENCY)*60
    taper=max(0,target-max(current,80))/20 * 0.20
    return ceil(base*(1+taper))
