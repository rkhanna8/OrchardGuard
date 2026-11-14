"""DEMONSTRATION ONLY — deterministic synthetic trajectories for UI development."""
from __future__ import annotations
import math
import random

def generate_mock_results(scenario: dict) -> dict:
    quality = max(0.0, min(1.0, float(scenario.get("gps_quality", 1.0))))
    outage = bool(scenario.get("outage_enabled", False))
    trees = scenario.get("trees", [])
    rng = random.Random(int(scenario.get("random_seed", 42)))
    frames = []
    errors, baseline_errors = [], []
    drift_x, drift_y = 0.0, 0.0
    for i in range(181):
        t = i * 0.25
        # A simple orchard route with turns, NOT a real CitrusFarm path.
        x = 8.0 + 0.36*i
        y = 22 + 8*math.sin(i/33.0)
        nxtx = 8.0 + 0.36*(i+1)
        nxty = 22 + 8*math.sin((i+1)/33.0)
        yaw = math.atan2(nxty-y,nxtx-x)
        inside = any(math.hypot(x-float(z["x"]), y-float(z["y"])) <= float(z.get("radius_m",5.0)) for z in trees)
        condition = (0 if outage else max(0,quality-(0.65 if inside else 0)))
        status = "outage" if condition < 0.18 else "degraded" if condition < 0.7 else "nominal"
        # Drift increases during degradation; recovery only in nominal conditions.
        rate = (1-condition)*0.075
        drift_x += rate + rng.gauss(0,0.005)
        drift_y += rate*0.45 + rng.gauss(0,0.005)
        if status == "nominal":
            drift_x *= 0.90
            drift_y *= 0.90
        ex, ey = x+drift_x, y+drift_y
        bx, by = x+0.055*i, y-0.028*i
        err=math.hypot(ex-x,ey-y); berr=math.hypot(bx-x,by-y)
        errors.append(err);baseline_errors.append(berr)
        frames.append({
            "time":round(t,3),
            "ground_truth":{"x":x,"y":y,"yaw":yaw},
            "estimated":{"x":ex,"y":ey,"yaw":yaw+0.02},
            "baseline":{"x":bx,"y":by},
            "position_error":err,
            "baseline_error":berr,
            "position_std_m":0.15+(1-condition)*i*0.011,
            "gps_status":status,
            "gps_accepted":status=="nominal",
            "satellites":int(round(3+condition*11)) if status!="outage" else 0
        })
    return {
        "metadata":{"source":"mock","sequence":"synthetic-demo","coordinate_frame":"local_enu","units":"meters","scenario_label":"Illustrative demonstration (NOT CitrusFarm results)"},
        "frames":frames,
        "metrics":{"rmse_m":math.sqrt(sum(e*e for e in errors)/len(errors)),
                   "baseline_rmse_m":math.sqrt(sum(e*e for e in baseline_errors)/len(baseline_errors)),
                   "max_error_m":max(errors)}
    }
