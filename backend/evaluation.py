"""Evaluation against post-processed RTK, separate from model confidence."""
import math
import numpy as np


def confidence(covariance, tolerance):
    """Probability inside a circle under a centered 2-D Gaussian model.

    Integrate in angle after diagonalizing covariance. This is a model
    probability, not a calibration claim or a reference-error measurement.
    """
    covariance = np.asarray(covariance)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all() or tolerance <= 0:
        return None
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues[0] <= 0:
        return None
    angles = (np.arange(256) + .5) * (2 * math.pi / 256)
    radial_variance = eigenvalues[0] * np.cos(angles)**2 + eigenvalues[1] * np.sin(angles)**2
    return float(np.mean(-np.expm1(-tolerance**2 / (2 * radial_variance))) * 100)


def metrics(frames, key, start, end, tolerance, sustained):
    errors = np.array([f[key] for f in frames])
    times = np.array([f['time'] for f in frames])
    # Left-held samples, clipped to the requested fault interval.
    dt = np.maximum(0, np.minimum(times[1:], end) - np.maximum(times[:-1], start))
    during = float(np.sum(dt * (errors[:-1] <= tolerance)))
    duration = float(np.sum(dt))
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
    return {'rmse_m': float(np.sqrt(np.mean(errors**2))), 'peak_error_m': float(np.max(errors)),
            'fault_within_tolerance_s': during if duration else None,
            'fault_duration_s': duration, 'recovery_s': recovery,
            'recovery_status': ('not applicable' if not duration else
                                'recovered' if recovery is not None else 'did not recover')}
