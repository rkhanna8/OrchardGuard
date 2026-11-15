"""CitrusFarm replay: PR #1 EKF with explicit faults and matched comparisons."""
import math
import os
from pathlib import Path
import numpy as np
from backend.recording import load
from backend.diagnostics import load_diagnostics, latest_diagnostics
from backend.evaluation import confidence, metrics

DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'data/orchardguard-sensors.zip'


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def predict(state, speed, yaw_rate, dt):
    x, y, yaw = state
    middle = yaw + yaw_rate * dt / 2
    distance = speed * dt
    return np.array([
        x + distance * math.cos(middle),
        y + distance * math.sin(middle),
        wrap(yaw + yaw_rate * dt),
    ]), middle


def correct(state, covariance, fix, measurement_covariance, gate=True, threshold=9.21):
    residual = fix - state[:2]
    innovation = covariance[:2, :2] + measurement_covariance
    if gate and residual @ np.linalg.solve(innovation, residual) > threshold:
        return state, covariance, False
    gain = np.linalg.solve(innovation, covariance[:2]).T
    state = state + gain @ residual
    state[2] = wrap(state[2])
    factor = np.eye(3)
    factor[:, :2] -= gain
    covariance = factor @ covariance @ factor.T + gain @ measurement_covariance @ gain.T
    return state, covariance, True


def fault_active(time, scenario):
    return (scenario.get('outage_enabled', False) or
            (scenario.get('scenario_type', 'recorded') != 'recorded' and
             scenario.get('fault_start_s', 30.0) <= time < scenario.get('fault_end_s', 60.0)))


def fault_fix(fix, time, yaw, scenario):
    """Change only estimator GPS positions/availability, never reported covariance/status."""
    if not fault_active(time, scenario):
        return fix.copy()
    if scenario.get('outage_enabled') or scenario.get('scenario_type') == 'outage':
        return None
    jump = scenario.get('jump_m', 10.0)
    return fix + jump * np.array([-math.sin(yaw), math.cos(yaw)])


def measurement(row, max_age):
    age = row[0] - row[9]
    if not np.isfinite(row[1:3]).all() or not np.isfinite(row[3]) or row[3] < 0:
        return None, 'invalid recorded fix'
    if not math.isfinite(age) or age < -0.05 or age > max_age:
        return None, 'stale or inconsistent GPS header timestamp'
    covariance = np.array([[row[4], row[6]], [row[7], row[5]]])
    if row[8] == 0:
        return np.eye(2), 'reported covariance unknown; using 1 m² diagonal'
    if (not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T) or
            np.linalg.eigvalsh(covariance)[0] <= 0):
        return None, 'invalid reported covariance'
    # Retain PR #1 conservative floor for unmodelled antenna/planar effects.
    return covariance + np.eye(2) * max(0, .04 - np.linalg.eigvalsh(covariance)[0]), 'reported covariance with 0.04 m² eigenvalue floor'


def run_localization(scenario: dict) -> dict:
    path = Path(scenario.get('data_path') or os.environ.get('ORCHARDGUARD_DATA', DEFAULT_DATA)).expanduser()
    if not path.is_file():
        raise NotImplementedError(f'Select the CitrusFarm sensor ZIP: {path}')
    stat = path.stat()
    wheel, imu, gps, ref, audit = load(str(path), stat.st_mtime_ns, stat.st_size)
    kind = scenario.get('scenario_type', 'recorded')
    if kind not in ('recorded', 'outage', 'jump'):
        raise ValueError('Unknown replay scenario')
    start_fault = float(scenario.get('fault_start_s', 30))
    end_fault = float(scenario.get('fault_end_s', 60))
    tolerance = float(scenario.get('tolerance_m', 2))
    sustained = float(scenario.get('recovery_s', 3))
    max_age = float(scenario.get('gps_max_age_s', 1))
    jump = float(scenario.get('jump_m', 10))
    quality = float(scenario.get('gps_quality', 1))
    if not all(math.isfinite(v) for v in (start_fault, end_fault, tolerance, sustained, max_age, jump, quality)):
        raise ValueError('Scenario numbers must be finite')
    if not (0 < start_fault < end_fault and tolerance > 0 and sustained > 0 and max_age > 0 and 0 <= quality <= 1):
        raise ValueError('Require 0 < fault start < end and positive tolerance/recovery/freshness')
    trees = scenario.get('trees', [])
    rng = np.random.default_rng(scenario.get('random_seed', 42))
    usable = [j for j, row in enumerate(gps) if measurement(row, max_age)[0] is not None
              and row[0] >= max(wheel[0, 0], imu[0, 0], ref[0, 0])]
    if not usable:
        raise ValueError('Uninitialized: no valid fresh GPS starting pose')
    first = usable[0]
    initial = next((j for j in usable if np.linalg.norm(gps[j, 1:3] - gps[first, 1:3]) >= 3), None)
    if initial is None:
        raise ValueError('Uninitialized: GPS course calibration requires 3 m of initial travel')
    course = gps[initial, 1:3] - gps[first, 1:3]
    start = gps[initial, 0]
    end = min(wheel[-1, 0], imu[-1, 0], ref[-1, 0])
    if end <= start or start < ref[0, 0]:
        raise ValueError('No overlap after GPS initialization')
    initial_state = np.array([*gps[initial, 1:3], math.atan2(course[1], course[0])])
    estimated = initial_state.copy()
    ungated = initial_state.copy()
    inertial = initial_state.copy()
    wheel_only = initial_state.copy()
    covariance = np.diag([.1, .1, math.radians(5)**2])
    ungated_cov = covariance.copy()
    moving = np.flatnonzero(np.abs(wheel[:, 1]) > .1)
    bias_end = min(start, wheel[moving[0], 0]) if len(moving) else start
    still = imu[(imu[:, 0] < bias_end), 1]
    bias = float(np.median(still)) if len(still) else 0.0
    frame_times = start + np.arange(0, end - start, .1)
    fixes = {row[0]: row for row in gps[initial + 1:] if row[0] <= frame_times[-1]}
    controls = np.unique(np.concatenate((frame_times, list(fixes), wheel[:, 0], imu[:, 0],
                                        [start + start_fault, start + end_fault])))
    controls = controls[(controls >= start) & (controls <= frame_times[-1])]
    wi = wheel[:, 0].searchsorted(controls, side='right') - 1
    ii = imu[:, 0].searchsorted(controls, side='right') - 1
    reference = np.column_stack([np.interp(controls, ref[:, 0], ref[:, j]) for j in (1, 2)])
    diagnostics = load_diagnostics(scenario.get('diagnostics_path') or os.environ.get(
        'ORCHARDGUARD_DIAGNOSTICS', str(DEFAULT_DATA.parent / 'receiver_state.csv')))
    frame_set = set(frame_times)
    frames, decisions = [], []
    last_accepted = start
    last_received = start
    decision, reason = 'accepted', 'GPS position and 3 m course initialization'
    accepted = False
    nis = None
    reference_yaw = initial_state[2]
    last_reference = reference[0]
    pose = lambda state: dict(zip(('x', 'y', 'yaw'), map(float, state)))
    for n, timestamp in enumerate(controls):
        time = round(float(timestamp - start), 6)
        if n:
            dt = timestamp - controls[n - 1]
            speed, gyro = wheel[wi[n - 1], 1], imu[ii[n - 1], 1] - bias
            inertial, _ = predict(inertial, speed, gyro, dt)
            wheel_only, _ = predict(wheel_only, speed, wheel[wi[n - 1], 2], dt)
            for name in ('gated', 'ungated'):
                state, cov = (estimated, covariance) if name == 'gated' else (ungated, ungated_cov)
                state, middle = predict(state, speed, gyro, dt)
                jacobian = np.array([[1, 0, -speed * dt * math.sin(middle)],
                                     [0, 1, speed * dt * math.cos(middle)], [0, 0, 1]])
                cov = jacobian @ cov @ jacobian.T + dt * np.diag([.08, .08, .003])
                if name == 'gated':
                    estimated, covariance = state, cov
                else:
                    ungated, ungated_cov = state, cov
        active = fault_active(time, scenario)
        injected_outage = active and (kind == 'outage' or scenario.get('outage_enabled'))
        if injected_outage:
            decision, reason, accepted = 'unavailable', 'simulated GPS outage', False
        if timestamp in fixes:
            row = fixes[timestamp]
            last_received = timestamp
            noise_cov, validity = measurement(row, max_age)
            fix = fault_fix(row[1:3], time, initial_state[2], scenario)
            local_quality = quality
            for tree in trees:
                if math.dist(reference[n], (tree['x'], tree['y'])) <= tree['radius_m']:
                    local_quality = min(local_quality, 1 - tree['severity'])
            if local_quality < 1 and rng.random() < .7 * (1 - local_quality):
                fix = None
            used, ungated_used = False, False
            nis = None
            if fix is None:
                decision, reason = 'unavailable', 'simulated GPS outage' if injected_outage else 'simulated canopy/quality dropout'
            elif noise_cov is None:
                decision, reason = 'unavailable', validity
            else:
                if local_quality < 1:
                    fix = fix + rng.normal(0, 2 * (1 - local_quality), 2)
                residual = fix - estimated[:2]
                nis = float(residual @ np.linalg.solve(covariance[:2, :2] + noise_cov, residual))
                estimated, covariance, used = correct(estimated, covariance, fix, noise_cov)
                ungated, ungated_cov, ungated_used = correct(ungated, ungated_cov, fix, noise_cov, gate=False)
                decision = 'accepted' if used else 'rejected'
                reason = validity if used else 'innovation NIS exceeds 9.21 (2-D gate)'
                if used:
                    last_accepted = timestamp
                    accepted = True
            decisions.append({'time': time, 'decision': decision, 'reason': reason, 'nis': nis,
                              'accepted': bool(used), 'ungated_accepted': bool(ungated_used),
                              'fault_active': bool(active), 'recorded_fix_status': float(row[3]) if math.isfinite(row[3]) else None})
        if timestamp - last_received > max_age and not injected_outage:
            decision, reason = 'unavailable', 'no fresh recorded GPS sample'
        if timestamp in frame_set:
            displacement = reference[n] - last_reference
            if np.linalg.norm(displacement) >= .2:
                reference_yaw = math.atan2(displacement[1], displacement[0])
                last_reference = reference[n]
            diag = latest_diagnostics(diagnostics, timestamp, float(scenario.get('diagnostics_max_age_s', 2)))
            status = 'nominal' if decision == 'accepted' else 'outage' if decision == 'unavailable' else 'degraded'
            frames.append({'time': time, 'ground_truth': pose((*reference[n], reference_yaw)),
                           'estimated': pose(estimated), 'ungated': pose(ungated), 'baseline': pose(wheel_only),
                           'wheel_imu': pose(inertial), 'initialized': True,
                           'position_error': math.dist(estimated[:2], reference[n]),
                           'baseline_error': math.dist(wheel_only[:2], reference[n]),
                           'wheel_imu_error': math.dist(inertial[:2], reference[n]),
                           'ungated_error': math.dist(ungated[:2], reference[n]),
                           'position_std_m': math.sqrt(np.trace(covariance[:2, :2])),
                           'position_covariance': covariance[:2, :2].tolist(),
                           'confidence_pct': confidence(covariance[:2, :2], tolerance),
                           'tolerance_m': tolerance, 'gps_status': status, 'gps_accepted': bool(accepted),
                           'gps_decision': decision, 'gps_reason': reason, 'gps_nis': nis,
                           'accepted_fix_age_s': float(timestamp - last_accepted),
                           'receiver': diag, 'satellites': diag.get('num_sat') if diag['available'] else None,
                           'fault_active': bool(active), 'speed_mps': float(wheel[wi[n], 1])})
            accepted = False
    interval = (0, frames[-1]['time']) if scenario.get('outage_enabled') else (start_fault, end_fault) if kind != 'recorded' else (0, 0)
    comparison = {name: metrics(frames, key, *interval, tolerance, sustained) for name, key in
                  [('gated', 'position_error'), ('ungated', 'ungated_error'), ('wheel_imu', 'wheel_imu_error'), ('wheel_only', 'baseline_error')]}
    return {'metadata': {'source': 'citrusfarm', 'sequence': '01_13B_Jackal', 'coordinate_frame': 'local_enu',
                         'units': 'meters', 'scenario_label': ('SIMULATED full outage' if scenario.get('outage_enabled') else
                                            f'SIMULATED {kind}' if kind != 'recorded' else
                                            'Recorded GPS + SIMULATED canopy/quality' if quality < 1 or trees else 'Recorded GPS'),
                         'scenario': dict(scenario), 'replay_start_unix_s': float(start),
                         'initialization': 'GPS position after 3 m initial GPS travel; heading from that course; stationary gyro bias',
                         'initial_yaw_rad': float(initial_state[2]), 'gyro_bias_rad_s': bias,
                         'reference_note': 'Error against post-processed RTK reference; GPS and reference share an RTK source',
                         'audit': audit, 'fault_interval_s': list(interval), 'recovery_sustained_s': sustained,
                         'jump_direction': 'lateral to the shared initial GPS course', 'satellites_illustrative': False},
            'frames': frames, 'gps_updates': decisions,
            'metrics': {'rmse_m': comparison['gated']['rmse_m'], 'max_error_m': comparison['gated']['peak_error_m'],
                        'baseline_rmse_m': comparison['wheel_only']['rmse_m'], 'comparisons': comparison}}
