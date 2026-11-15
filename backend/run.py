"""CitrusFarm replay: PR #1 EKF with explicit faults and matched comparisons."""
import math
import os
from pathlib import Path
import numpy as np
from backend.recording import load, sample_reference, recording_diagnostics
from backend.diagnostics import load_diagnostics, latest_diagnostics
from backend.evaluation import confidence, metrics, coverage
from backend.recovery import RecoveryGuard
from backend.trust import FixTrust

DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'data/orchardguard-sensors.zip'


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def predict(state, speed, yaw_rate, dt, lever_arm_m=0.0):
    x, y, yaw = state
    middle = yaw + yaw_rate * dt / 2
    distance = speed * dt
    return np.array([
        x + distance * math.cos(middle) + lever_arm_m*(math.cos(yaw+yaw_rate*dt)-math.cos(yaw)),
        y + distance * math.sin(middle) + lever_arm_m*(math.sin(yaw+yaw_rate*dt)-math.sin(yaw)),
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
    if not math.isfinite(age) or age < -1e-6 or age > max_age:
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
    tolerance = float(scenario.get('tolerance_m', 1))
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
              and row[0] >= max(wheel[0, 0], imu[0, 0])]
    if not usable:
        raise ValueError('Uninitialized: no valid fresh GPS starting pose')
    first = usable[0]
    initial = next((j for j in usable if np.linalg.norm(gps[j, 1:3] - gps[first, 1:3]) >= 3), None)
    if initial is None:
        raise ValueError('Uninitialized: GPS course calibration requires 3 m of initial travel')
    course = gps[initial, 1:3] - gps[first, 1:3]
    start = gps[initial, 0]
    end = min(wheel[-1, 0], imu[-1, 0])
    if end <= start:
        raise ValueError('No overlap after GPS initialization')
    initial_state = np.array([*gps[initial, 1:3], math.atan2(course[1], course[0])])
    lever_arm = -.18 if audit.get('map_registered') and not scenario.get('legacy_sensor_offset',False) else 0.0
    estimated = initial_state.copy()
    shadow = initial_state.copy()
    guard = RecoveryGuard()
    ungated = initial_state.copy()
    inertial = initial_state.copy()
    wheel_only = initial_state.copy()
    covariance = np.diag([.1, .1, math.radians(5)**2])
    ungated_cov = covariance.copy()
    moving = np.flatnonzero(np.abs(wheel[:, 1]) > .1)
    bias_end = min(start, wheel[moving[0], 0]) if len(moving) else start
    still = imu[(imu[:, 0] < bias_end), 1]
    bias = float(np.median(still)) if len(still) else 0.0
    # Causal speed calibration: only recorded GPS/wheel/IMU at or before the
    # documented initialization instant. No reference or later replay samples.
    calibration_times=np.r_[gps[first,0],wheel[(wheel[:,0]>gps[first,0])&(wheel[:,0]<start),0],start]
    calibration_indices=wheel[:,0].searchsorted(calibration_times[:-1],side='right')-1
    wheel_travel=float(np.sum(wheel[calibration_indices,1]*np.diff(calibration_times)))
    calibration_imu=imu[(imu[:,0]>=gps[first,0])&(imu[:,0]<=start)]
    turning=float(np.sum((np.abs(calibration_imu[:-1,1]-bias)+np.abs(calibration_imu[1:,1]-bias))*.5*np.diff(calibration_imu[:,0]))) if len(calibration_imu)>1 else math.inf
    proposed_scale=float(np.linalg.norm(course)/wheel_travel) if wheel_travel>2 else 1.0
    wheel_scale=proposed_scale if scenario.get('calibrate_wheel_scale',True) and turning<.15 and np.max(np.diff(calibration_times))<.5 and .7<proposed_scale<1.3 else 1.0
    frame_times = start + np.arange(0, end - start, .1)
    fixes = {row[0]: row for row in gps[initial + 1:] if row[0] <= frame_times[-1]}
    controls = np.unique(np.concatenate((frame_times, list(fixes), wheel[:, 0], imu[:, 0],
                                        [start + start_fault, start + end_fault])))
    controls = controls[(controls >= start) & (controls <= frame_times[-1])]
    wi = wheel[:, 0].searchsorted(controls, side='right') - 1
    ii = imu[:, 0].searchsorted(controls, side='right') - 1
    reference = sample_reference(ref, controls)
    diagnostics = recording_diagnostics(path, audit, scenario.get('diagnostics_path') or os.environ.get('ORCHARDGUARD_DIAGNOSTICS'))
    frame_set = set(frame_times)
    frames, decisions = [], []
    last_accepted = start
    # start is gps[initial, 0]: the actual valid GPS course-initialization
    # sample timestamp, not an arbitrary playback-clock origin.
    last_trusted = start
    trust = FixTrust()
    trust_reason = "Trusted GPS initialization"
    trust_renewed = True
    candidate_health = "healthy"
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
            speed, gyro = wheel_scale*wheel[wi[n - 1], 1], imu[ii[n - 1], 1] - bias
            stale_control=(controls[n-1]-wheel[wi[n-1],0]>.5 or controls[n-1]-imu[ii[n-1],0]>.5)
            if controls[n-1]-wheel[wi[n-1],0]>.5:speed=0.0
            if controls[n-1]-imu[ii[n-1],0]>.5:gyro=0.0
            inertial, _ = predict(inertial, speed, gyro, dt, lever_arm)
            shadow, _ = predict(shadow, speed, gyro, dt, lever_arm)
            wheel_only, _ = predict(wheel_only, speed, wheel[wi[n - 1], 2], dt, lever_arm)
            for name in ('gated', 'ungated'):
                state, cov = (estimated, covariance) if name == 'gated' else (ungated, ungated_cov)
                old_yaw=state[2]
                state, middle = predict(state, speed, gyro, dt, lever_arm)
                jacobian = np.array([[1, 0, -speed * dt * math.sin(middle)+lever_arm*(-math.sin(state[2])+math.sin(old_yaw))],
                                     [0, 1, speed * dt * math.cos(middle)+lever_arm*(math.cos(state[2])-math.cos(old_yaw))], [0, 0, 1]])
                cov = jacobian @ cov @ jacobian.T + dt * np.diag([.08, .08, .003]) * (10 if stale_control else 1)
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
            local_quality = quality if scenario.get('quality_start_s',0)<=time<scenario.get('quality_end_s',float('inf')) else 1.0
            for tree in trees:
                if math.dist(reference[n], (tree['x'], tree['y'])) <= tree['radius_m']:
                    local_quality = min(local_quality, 1 - tree['severity'])
            if local_quality < 1 and rng.random() < .7 * (1 - local_quality):
                fix = None
            used, ungated_used = False, False
            nis = None
            recovered=False
            guard_reason=None
            residual = innovation = None
            prior_state=estimated.copy();prior_cov=covariance.copy();prior_shadow=shadow.copy()
            diag=latest_diagnostics(diagnostics,timestamp,float(scenario.get('diagnostics_max_age_s',2)))
            receiver_ok=(noise_cov is not None and (not diag['available'] or
                     (diag.get('fix_mode')=='FIXED_RTK' and not any(diag.get(k,0) for k in ('system_error','io_error','swift_nap_error')))))
            healthy = local_quality == 1 and receiver_ok
            candidate_health='healthy' if healthy else 'degraded'
            accepted_age_before=float(timestamp-last_accepted)
            if fix is None:
                decision, reason = 'unavailable', 'simulated GPS outage' if injected_outage else 'simulated canopy/quality dropout'
            elif noise_cov is None:
                decision, reason = 'unavailable', validity
            else:
                if local_quality < 1:
                    fix = fix + rng.normal(0, 2 * (1 - local_quality), 2)
                    # This noise is known because we inject it. The jump scenario
                    # deliberately preserves covariance to test the innovation gate.
                    if not scenario.get('legacy_noise_covariance',False):
                        noise_cov=noise_cov+np.eye(2)*(2*(1-local_quality))**2
                residual = fix - estimated[:2]
                innovation=covariance[:2,:2]+noise_cov
                nis = float(residual @ np.linalg.solve(innovation, residual))
                allowed,recovered,guard_reason=guard.observe(time,fix,shadow,wheel_scale*wheel[wi[n],1],noise_cov,healthy,nis<=9.21) if scenario.get('guarded_recovery',True) else (nis<=9.21,False,'innovation gate')
                if allowed:
                    if recovered:
                        # Guarded and bounded recovery after five samples. Inflate
                        # XY uncertainty before the Joseph update; never hard-reset.
                        covariance=covariance+np.diag([max(0.,float(residual@residual)),max(0.,float(residual@residual)),0.])
                    estimated, covariance, used = correct(estimated, covariance, fix, noise_cov)
                else:used=False
                ungated, ungated_cov, ungated_used = correct(ungated, ungated_cov, fix, noise_cov, gate=False)
                decision = 'accepted' if used else 'rejected'
                reason = (validity + ('; plus known simulated noise variance' if local_quality<1 and not scenario.get('legacy_noise_covariance',False) else '')) if used else guard_reason
                if used:
                    last_accepted = timestamp
                    if healthy:
                        last_trusted=timestamp;shadow=estimated.copy()
                    accepted = True
            # Policy trust observer is independent of EKF acceptance/recovery.
            trust_renewed, trust_reason = trust.observe(time, used, receiver_ok, residual, innovation, noise_cov)
            if used and healthy:
                trust_renewed, trust_reason = True, 'Trust renewed: healthy receiver and accepted guarded fix'
            if trust_renewed:
                last_trusted = timestamp
            decisions.append({'time': time, 'decision': decision, 'reason': reason, 'nis': nis,
                              'accepted': bool(used), 'ungated_accepted': bool(ungated_used),
                              'fault_active': bool(active), 'local_quality':local_quality,
                              'candidate_health':candidate_health if fix is not None and noise_cov is not None else 'missing_or_invalid',
                              'candidate_available':bool(fix is not None and noise_cov is not None),
                              'fix_mode':diag.get('fix_mode'), 'diagnostic_age_s':diag.get('age_s'),
                              'innovation':residual.tolist() if residual is not None else None,
                              'innovation_covariance':innovation.tolist() if innovation is not None else None,
                              'measurement_covariance':noise_cov.tolist() if noise_cov is not None else None,
                              'gate_threshold':9.21,'guard_reason':guard_reason,'guarded_recovery':bool(recovered),
                              'trusted_prediction':pose(prior_shadow),'quarantined':guard.quarantined, 'accepted_fix_age_before_s':accepted_age_before,
                              'accepted_fix_age_s':float(timestamp-last_accepted),
                              'trusted_fix_age_s':float(timestamp-last_trusted),
                              'last_accepted_time_s':float(last_accepted-start), 'last_trusted_time_s':float(last_trusted-start),
                              'receiver_healthy':bool(receiver_ok), 'trust_renewed':bool(trust_renewed), 'trust_reason':trust_reason,
                              'prediction':{'wheel_speed_mps':float(wheel_scale*wheel[wi[n],1]),'raw_wheel_speed_mps':float(wheel[wi[n],1]),'gyro_rad_s':float(imu[ii[n],1]-bias),
                                            'wheel_age_s':float(timestamp-wheel[wi[n],0]),'imu_age_s':float(timestamp-imu[ii[n],0])},
                              'prior_pose':pose(prior_state),'prior_covariance':prior_cov.tolist(),
                              'pose_covariance':covariance.tolist(),
                              'reference_error_m':math.dist(estimated[:2],reference[n]) if np.isfinite(reference[n]).all() else None,
                              'prior_reference_error_m':math.dist(prior_state[:2],reference[n]) if np.isfinite(reference[n]).all() else None,
                              'recorded_fix_status': float(row[3]) if math.isfinite(row[3]) else None})
        if timestamp - last_received > max_age and not injected_outage:
            decision, reason = 'unavailable', 'no fresh recorded GPS sample'
        if timestamp in frame_set:
            displacement = reference[n] - last_reference
            if np.linalg.norm(displacement) >= .2:
                reference_yaw = math.atan2(displacement[1], displacement[0])
                last_reference = reference[n]
            diag = latest_diagnostics(diagnostics, timestamp, float(scenario.get('diagnostics_max_age_s', 2)))
            status = 'nominal' if decision == 'accepted' else 'outage' if decision == 'unavailable' else 'degraded'
            frames.append({'time': time, 'ground_truth': pose((*reference[n], reference_yaw)) if np.isfinite(reference[n]).all() else None,
                           'estimated': pose(estimated), 'ungated': pose(ungated), 'baseline': pose(wheel_only),
                           'wheel_imu': pose(inertial), 'initialized': True,
                           'position_error': math.dist(estimated[:2], reference[n]) if np.isfinite(reference[n]).all() else None,
                           'baseline_error': math.dist(wheel_only[:2], reference[n]) if np.isfinite(reference[n]).all() else None,
                           'wheel_imu_error': math.dist(inertial[:2], reference[n]) if np.isfinite(reference[n]).all() else None,
                           'ungated_error': math.dist(ungated[:2], reference[n]) if np.isfinite(reference[n]).all() else None,
                           'position_std_m': math.sqrt(np.trace(covariance[:2, :2])),
                           'position_covariance': covariance[:2, :2].tolist(),
                           'confidence_pct': confidence(covariance[:2, :2], tolerance),
                           'tolerance_m': tolerance, 'gps_status': status, 'gps_accepted': bool(accepted),
                           'gps_decision': decision, 'gps_reason': reason, 'gps_nis': nis,
                           'accepted_fix_age_s': float(timestamp - last_accepted),
                           'trusted_fix_age_s':float(timestamp-last_trusted), 'candidate_health':candidate_health,
                           'last_accepted_time_s':float(last_accepted-start), 'last_trusted_time_s':float(last_trusted-start),
                           'trust_reason':trust_reason,
                           'prediction_valid':bool(timestamp-wheel[wi[n],0]<=.5 and timestamp-imu[ii[n],0]<=.5),
                           'receiver': diag, 'satellites': diag.get('num_sat') if diag['available'] else None,
                           'fault_active': bool(active), 'speed_mps': float(wheel_scale*wheel[wi[n], 1])})
            accepted = False
    interval = (0, frames[-1]['time']) if scenario.get('outage_enabled') else (start_fault, end_fault) if kind != 'recorded' else (0, 0)
    comparison = {name: metrics(frames, key, *interval, tolerance, sustained) for name, key in
                  [('gated', 'position_error'), ('ungated', 'ungated_error'), ('wheel_imu', 'wheel_imu_error'), ('wheel_only', 'baseline_error')]}
    return {'metadata': {'source': audit.get('source','citrusfarm'), 'recording_kind':audit.get('recording_kind','recorded'), 'sequence': audit['sequence'], 'map_registered':audit['map_registered'], 'coordinate_frame': 'local_enu',
                         'units': 'meters', 'scenario_label': ('SIMULATED full outage' if scenario.get('outage_enabled') else
                                            f'SIMULATED {kind}' if kind != 'recorded' else
                                            'Recorded GPS + SIMULATED canopy/quality' if quality < 1 or trees else 'Recorded GPS'),
                         'scenario': dict(scenario), 'replay_start_unix_s': float(start),
                         'initialization': 'GPS position after 3 m initial GPS travel; course heading; stationary gyro bias; guarded wheel speed scale from pre-initialization GPS distance',
                         'wheel_scale':wheel_scale,'wheel_scale_calibration_end_unix_s':float(start),'initial_calibration_turn_rad':turning,'antenna_lever_arm_body_x_m':lever_arm,'initial_yaw_rad': float(initial_state[2]), 'gyro_bias_rad_s': bias, 'initialization_end_unix_s':float(start),
                         'reference_note': 'Error against post-processed RTK reference; GPS and reference share an RTK source',
                         'audit': audit, 'fault_interval_s': list(interval), 'recovery_sustained_s': sustained,
                         'jump_direction': 'lateral to the shared initial GPS course', 'satellites_illustrative': False},
            'frames': frames, 'gps_updates': decisions,
            'metrics': {'rmse_m': comparison['gated']['rmse_m'], 'max_error_m': comparison['gated']['peak_error_m'],
                        'baseline_rmse_m': comparison['wheel_only']['rmse_m'], 'comparisons': comparison,
                        'coverage':coverage(frames, interval, tolerance)}}
