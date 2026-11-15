"""Policy trust from accepted innovations, never reference error or slider value.

This observer does not modify the EKF or its recovery shadow. A noisy correction
is useful before there is enough evidence to renew policy trust. Consistency is
relative to the predicted motion; it cannot certify absence of slow GPS bias.
"""
from collections import deque
import numpy as np


class FixTrust:
    def __init__(self):
        self.history = deque()

    def observe(self, time, accepted, receiver_ok, residual, innovation, measurement):
        if not accepted and residual is None and receiver_ok:
            return False, 'No new correction; awaiting fresh accepted GPS'
        if not accepted or not receiver_ok:
            self.history.clear()
            return False, 'No trust renewal: correction rejected/unavailable or receiver unhealthy'
        if self.history and time - self.history[-1][0] > .8:
            self.history.clear()
        self.history.append((time, np.asarray(residual), np.asarray(innovation), np.asarray(measurement)))
        while self.history and time - self.history[0][0] > 3.0:
            self.history.popleft()
        if len(self.history) < 10 or time - self.history[0][0] < 2.0:
            return False, 'Correction used; collecting ≥10 consistent accepted fixes over ≥2 s'
        # Judge precision of the sustained window, not each noisy correction.
        # Independent injected noise averages down; consistency checks below
        # still reject biased/incompatible innovations. No reference is used.
        mean_variance = sum(np.trace(m) for _, _, _, m in self.history) / len(self.history)**2
        if not np.isfinite(mean_variance) or mean_variance > .25:
            return False, 'Correction used; GPS window precision insufficient (mean-noise RMS limit: 0.5 m)'
        residuals = np.array([r for _, r, _, _ in self.history])
        mean_offset = np.linalg.norm(np.mean(residuals, axis=0))
        mean_nis = np.mean([r @ np.linalg.solve(s, r) for _, r, s, _ in self.history])
        if mean_offset > .75 or mean_nis > 3.0:
            return False, 'Correction used; sustained innovation consistency exceeds trust limits (0.75 m mean, NIS 3)'
        return True, 'Trust renewed: sustained accepted fixes agree with predicted motion'
