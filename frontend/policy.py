"""Deterministic demo-only speed policy evaluated on replay time."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PolicyConfig:
    slow_std_m: float = 1.0
    stop_std_m: float = 3.0
    slow_age_s: float = 2.0
    stop_age_s: float = 8.0
    recovery_s: float = 3.0

    def __post_init__(self):
        values = tuple(self.__dict__.values())
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError('Policy thresholds must be finite and positive')
        if self.slow_std_m >= self.stop_std_m or self.slow_age_s >= self.stop_age_s:
            raise ValueError('Slow thresholds must be below Stop thresholds')


class SpeedPolicy:
    def __init__(self, config=PolicyConfig()):
        self.config = config
        self.level = 0
        self.recovery_since = None

    def step(self, time, std, accepted_age, initialized=True):
        c = self.config
        if initialized and accepted_age is None:
            target, reason = 2, 'No trusted fix yet; waiting for qualified GPS'
        elif not initialized or std is None or (not math.isfinite(std) or not math.isfinite(accepted_age)):
            target, reason = 2, 'Localization unavailable'
        elif std >= c.stop_std_m:
            target, reason = 2, f'Estimated uncertainty {std:.2f} m (stop limit: {c.stop_std_m:g} m)'
        elif accepted_age >= c.stop_age_s:
            target, reason = 2, f'No trusted GPS fix for {accepted_age:.1f} s (stop limit: {c.stop_age_s:g} s)'
        elif std >= c.slow_std_m:
            target, reason = 1, f'Estimated uncertainty {std:.2f} m (slow limit: {c.slow_std_m:g} m)'
        elif accepted_age >= c.slow_age_s:
            target, reason = 1, f'No trusted GPS fix for {accepted_age:.1f} s (slow limit: {c.slow_age_s:g} s)'
        else:
            target, reason = 0, 'Position uncertainty and trusted GPS age are within limits'
        if target > self.level:
            # Escalate immediately; never wait through a dangerous condition.
            self.level = target
            self.recovery_since = None
        elif target < self.level:
            if self.recovery_since is None:
                self.recovery_since = time
            if time - self.recovery_since >= c.recovery_s - 1e-6:
                self.level -= 1
                self.recovery_since = None
            else:
                reason = f'Waiting for sustained recovery ({time-self.recovery_since:.1f}/{c.recovery_s:g} s) before increasing speed'
        else:
            self.recovery_since = None
        return {'state': ('Normal', 'Slow', 'Stop')[self.level], 'reason': reason,
                'stop_predicates': {'localization_unavailable': not initialized or std is None or accepted_age is None or not math.isfinite(std) or not math.isfinite(accepted_age),
                                    'uncertainty_limit': std is not None and std >= c.stop_std_m,
                                    'trusted_age_limit': accepted_age is not None and accepted_age >= c.stop_age_s},
                'speed_scale': (1.0, .35, 0.0)[self.level]}


def trusted_age(frame):
    """Only a causal, recorded trusted-fix timestamp can establish this age."""
    stamp = frame.get('last_trusted_time_s')
    now = frame.get('time')
    if stamp is None or now is None or not math.isfinite(stamp) or not math.isfinite(now) or stamp > now + 1e-6:
        return None
    return max(0., now-stamp)


def apply_policy(result, config=PolicyConfig()):
    policy = SpeedPolicy(config)
    for frame in result['frames']:
        frame['policy'] = policy.step(frame['time'], frame.get('position_std_m'),
                                     trusted_age(frame), frame.get('initialized', False) and frame.get('prediction_valid',True))
    return result
