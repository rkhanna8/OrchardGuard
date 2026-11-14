"""CitrusFarm sensor replay and the desktop localization contract."""
from __future__ import annotations

import csv
import io
import math
import os
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import numpy as np

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/orchardguard-sensors.zip"


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


@lru_cache(maxsize=2)
def load_recording(path, modified_ns, size):
    """Load timestamped sensor streams and the independently scored reference."""
    with ZipFile(path) as archive:
        def read(name, *fields):
            with archive.open(name + ".csv") as stream:
                rows = csv.DictReader(io.TextIOWrapper(stream))
                return np.array([
                    [int(row["bag_time_ns"]) * 1e-9, *(float(row[f]) for f in fields)]
                    for row in rows
                ])

        wheel = read("wheel", "speed_mps", "yaw_rate_rad_s")
        imu = read("imu", "gyro_z_rad_s")
        gps = read("gps", "latitude_deg", "longitude_deg", "fix_status", "cov_ee", "cov_nn")
        with archive.open("gt.csv") as stream:
            ref = np.loadtxt(stream, delimiter=",", usecols=(0, 1, 2))

    gps = gps[(gps[:, 3] >= 0) & np.isfinite(gps[:, :3]).all(axis=1)]
    if len(gps) < 2:
        raise ValueError("CitrusFarm recording needs at least two valid GPS fixes")

    # WGS84 tangent-plane approximation over this short orchard route.
    lat = math.radians(gps[0, 1])
    eccentricity_sq = 0.00669437999014
    scale = 1 - eccentricity_sq * math.sin(lat)**2
    east_radius = 6378137 * math.cos(lat) / math.sqrt(scale)
    north_radius = 6378137 * (1 - eccentricity_sq) / scale**1.5
    east = np.deg2rad(gps[:, 2] - gps[0, 2]) * east_radius
    north = np.deg2rad(gps[:, 1] - gps[0, 1]) * north_radius
    gps[:, 1], gps[:, 2] = east, north
    # The supplied reference uses north/west axes with the same GPS origin.
    ref[:, 1], ref[:, 2] = -ref[:, 2].copy(), ref[:, 1].copy()
    return wheel, imu, gps, ref


def predict(state, speed, yaw_rate, dt):
    x, y, yaw = state
    middle = yaw + yaw_rate * dt / 2
    distance = speed * dt
    return np.array([
        x + distance * math.cos(middle),
        y + distance * math.sin(middle),
        wrap(yaw + yaw_rate * dt),
    ]), middle


def correct(state, covariance, fix, measurement_covariance):
    residual = fix - state[:2]
    innovation = covariance[:2, :2] + measurement_covariance
    if residual @ np.linalg.solve(innovation, residual) > 9.21:
        return state, covariance, False
    gain = np.linalg.solve(innovation, covariance[:2]).T
    state = state + gain @ residual
    state[2] = wrap(state[2])
    factor = np.eye(3)
    factor[:, :2] -= gain
    covariance = factor @ covariance @ factor.T + gain @ measurement_covariance @ gain.T
    return state, covariance, True


def run_localization(scenario: dict) -> dict:
    """Replay the ZIP in data/ or the path supplied by ORCHARDGUARD_DATA."""
    path = Path(os.environ.get("ORCHARDGUARD_DATA", DEFAULT_DATA)).expanduser()
    try:
        stat = path.stat()
    except FileNotFoundError as exc:
        raise NotImplementedError(f"CitrusFarm ZIP required at {path}") from exc
    wheel, imu, gps, ref = load_recording(path, stat.st_mtime_ns, stat.st_size)
    quality = float(scenario.get("gps_quality", 1))
    if not 0 <= quality <= 1:
        raise ValueError("gps_quality must be between 0 and 1")
    outage = scenario.get("outage_enabled", False)
    trees = scenario.get("trees", [])
    rng = np.random.default_rng(scenario.get("random_seed", 42))

    # Use a brief GPS course calibration before every scenario, including outage.
    # The robot initially drives straight. No reference position enters the filter.
    course = gps[:, 1:3] - gps[0, 1:3]
    moved = np.flatnonzero(np.linalg.norm(course, axis=1) >= 3)
    if not len(moved):
        raise ValueError("GPS course calibration requires 3 m of initial travel")
    initial = moved[0]
    start = gps[initial, 0]
    end = min(wheel[-1, 0], imu[-1, 0], ref[-1, 0])
    if end <= start or start < max(wheel[0, 0], imu[0, 0], ref[0, 0]):
        raise ValueError("Sensor and reference streams do not overlap after calibration")

    estimated = np.array([*gps[initial, 1:3], math.atan2(*course[initial, ::-1])])
    baseline = estimated.copy()
    inertial = estimated.copy()
    covariance = np.diag([0.1, 0.1, math.radians(5)**2])
    stationary_end = np.flatnonzero(np.abs(wheel[:, 1]) > 0.1)
    bias_end = wheel[stationary_end[0], 0] if len(stationary_end) else start
    still = imu[imu[:, 0] < bias_end, 1]
    gyro_bias = float(np.median(still)) if len(still) else 0.0

    frame_times = start + np.arange(0, end - start, 0.1)
    fixes = {r[0]: r for r in gps[initial + 1:] if r[0] <= frame_times[-1]}
    events = np.union1d(frame_times, list(fixes))
    # Integrate the high-rate input streams before sampling the replay timeline.
    controls = np.union1d(events, wheel[:, 0])
    controls = np.union1d(controls, imu[:, 0])
    controls = controls[(controls >= start) & (controls <= events[-1])]
    wheel_idx = wheel[:, 0].searchsorted(controls, side="right") - 1
    imu_idx = imu[:, 0].searchsorted(controls, side="right") - 1
    ref_xy = np.column_stack([np.interp(controls, ref[:, 0], ref[:, j]) for j in (1, 2)])
    frame_set = set(frame_times)
    frames = []
    accepted = False
    status = "outage" if outage else ("nominal" if quality == 1 else "degraded")
    reference_yaw = float(estimated[2])
    last_reference = ref_xy[0]

    def pose(state):
        return dict(zip(("x", "y", "yaw"), map(float, state)))

    for i, t in enumerate(controls):
        if i:
            dt = t - controls[i - 1]
            _, speed, wheel_yaw = wheel[wheel_idx[i - 1]]
            gyro = imu[imu_idx[i - 1], 1] - gyro_bias
            estimated, middle = predict(estimated, speed, gyro, dt)
            baseline, _ = predict(baseline, speed, wheel_yaw, dt)
            inertial, _ = predict(inertial, speed, gyro, dt)
            dx = -speed * dt * math.sin(middle)
            dy = speed * dt * math.cos(middle)
            jacobian = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]])
            covariance = jacobian @ covariance @ jacobian.T + dt * np.diag([0.08, 0.08, 0.003])

        reference = ref_xy[i]
        if t in fixes:
            _, x, y, _, east_var, north_var = fixes[t]
            local_quality = quality
            for tree in trees:
                if math.hypot(reference[0] - tree["x"], reference[1] - tree["y"]) <= tree["radius_m"]:
                    local_quality = min(local_quality, 1 - tree["severity"])
            if outage or rng.random() < 0.7 * (1 - local_quality):
                status = "outage"
            else:
                status = "nominal" if local_quality == 1 else "degraded"
                noise = 2 * (1 - local_quality)
                fix = np.array([x, y]) + rng.normal(0, noise, 2)
                if rng.random() < 0.15 * (1 - local_quality):
                    fix += rng.normal(0, 8, 2)
                measurement = np.diag(np.maximum([east_var, north_var], 0.04) + noise**2)
                estimated, covariance, used = correct(estimated, covariance, fix, measurement)
                accepted |= used

        if t in frame_set:
            displacement = reference - last_reference
            if np.linalg.norm(displacement) >= 0.2:
                reference_yaw = math.atan2(*displacement[::-1])
                last_reference = reference
            frames.append({
                "time": float(t - start),
                "ground_truth": pose((*reference, reference_yaw)),
                "estimated": pose(estimated),
                "baseline": pose(baseline),
                "wheel_imu": pose(inertial),
                "position_error": math.dist(estimated[:2], reference),
                "baseline_error": math.dist(baseline[:2], reference),
                "wheel_imu_error": math.dist(inertial[:2], reference),
                "position_std_m": math.sqrt(np.trace(covariance[:2, :2])),
                "gps_status": status,
                "gps_accepted": bool(accepted),
                "satellites": 0 if status == "outage" else (12 if status == "nominal" else 6),
            })
            accepted = False

    def rmse(key):
        return math.sqrt(sum(frame[key]**2 for frame in frames) / len(frames))

    return {
        "metadata": {
            "source": "citrusfarm",
            "sequence": "01_13B_Jackal",
            "coordinate_frame": "local_enu",
            "units": "meters",
            "scenario_label": "Recorded CitrusFarm sensors with synthetic GNSS controls",
            "satellites_illustrative": True,
            "reference_yaw_derived": True,
        },
        "frames": frames,
        "metrics": {
            "rmse_m": rmse("position_error"),
            "baseline_rmse_m": rmse("baseline_error"),
            "wheel_imu_rmse_m": rmse("wheel_imu_error"),
            "max_error_m": max(f["position_error"] for f in frames),
        },
    }
