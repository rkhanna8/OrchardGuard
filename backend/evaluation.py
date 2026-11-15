"""Evaluation against post-processed RTK, separate from model confidence."""
import math
import numpy as np


def confidence(covariance, tolerance):
    """Probability inside a circle under a centered 2-D Gaussian model.

    Integrate in angle after diagonalizing covariance. This is a model
    probability, not a calibration claim or a reference-error measurement.
    """
    covariance = np.asarray(covariance)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all() or not math.isfinite(tolerance) or tolerance <= 0 or not np.allclose(covariance,covariance.T):
        return None
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues[0] <= 0:
        return None
    angles = (np.arange(256) + .5) * (2 * math.pi / 256)
    radial_variance = eigenvalues[0] * np.cos(angles)**2 + eigenvalues[1] * np.sin(angles)**2
    return float(np.mean(-np.expm1(-tolerance**2 / (2 * radial_variance))) * 100)


def metrics(frames, key, start, end, tolerance, sustained):
    errors = np.array([np.nan if f[key] is None else f[key] for f in frames])
    times = np.array([f['time'] for f in frames])
    # Left-held samples, clipped to the requested fault interval.
    dt = np.maximum(0, np.minimum(times[1:], end) - np.maximum(times[:-1], start))
    during = float(np.sum(dt * (errors[:-1] <= tolerance)))
    duration = float(np.sum(dt))
    known = np.isfinite(errors)
    breach_since = None; breach = None
    for t,e in zip(times,errors):
        if t<start or t>=end:continue
        if np.isfinite(e) and e>tolerance:
            if breach_since is None:breach_since=t
            if t-breach_since>=sustained-1e-6:
                breach=float(t-start);break
        else:breach_since=None
    recovery = None
    since = None
    if duration > 0:
        for t, error in zip(times, errors):
            if t < end:
                continue
            if error <= tolerance:
                if since is None:
                    since = t
                if t - since >= sustained - 1e-6:
                    recovery = float(t - end)
                    break
            else:
                since = None
    window=errors[(times>=start)&(times<end)&known]
    return {'window_rmse_m':float(np.sqrt(np.mean(window**2))) if len(window) else None,
            'window_peak_error_m':float(np.max(window)) if len(window) else None,
            'rmse_m': float(np.sqrt(np.nanmean(errors**2))) if known.any() else None, 'peak_error_m': float(np.nanmax(errors)) if known.any() else None,
            'fault_within_tolerance_s': during if duration else None,
            'fault_duration_s': duration, 'fault_reference_available_s':float(np.sum(dt*known[:-1])),
            'first_sustained_breach_s':breach,'breach_status':'breached' if breach is not None else 'not observed',
            'recovery_s': recovery,
            'recovery_status': ('not applicable' if not duration else
                                'recovered' if recovery is not None else 'did not recover')}


def probability_text(value):
    if value is None or not math.isfinite(value) or not 0 <= value <= 100:
        return 'Unavailable'
    return '>99.9%' if value > 99.9 else f'{value:.1f}%'


def probability_label(value,radius):
    if value is None:return 'Model probability unavailable'
    shown=probability_text(value)
    return f'Model-estimated chance of being within {radius:g} m: {shown} (not calibrated)'


def coverage(frames,interval,tolerance):
    """Descriptive same-time coverage, never used to tune a replay estimate."""
    start,end=interval;groups={'nominal':[],'degraded':[],'outage_or_fault':[],'recovery':[]}
    for frame in frames:
        if frame.get('position_error') is None:continue
        name='outage_or_fault' if frame.get('fault_active') or (end>start and start<=frame['time']<end) else 'recovery' if end>start and frame['time']>=end else 'degraded' if frame.get('candidate_health')=='degraded' else 'nominal'
        groups[name].append(frame)
    result={}
    for name,items in groups.items():
        if not items:continue
        errors=np.array([f['position_error'] for f in items])
        ellipse=[]
        for f in items:
            delta=np.array([f['estimated'][k]-f['ground_truth'][k] for k in ('x','y')])
            ellipse.append(float(delta @ np.linalg.solve(np.array(f['position_covariance']),delta))<=5.991)
        result[name]={'samples':len(items),'empirical_within_radius_pct':float(100*np.mean(errors<=tolerance)),
                      'mean_model_within_radius_pct':float(np.mean([confidence(f['position_covariance'],tolerance) for f in items])),
                      'empirical_95_ellipse_pct':float(100*np.mean(ellipse))}
    return result
