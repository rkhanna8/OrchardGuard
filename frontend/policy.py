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
        if not initialized or std is None or accepted_age is None or (not math.isfinite(std) or not math.isfinite(accepted_age)):
            target, reason = 2, 'Localization unavailable'
        elif std >= c.stop_std_m or accepted_age >= c.stop_age_s:
            target, reason = 2, 'Uncertainty or accepted-fix age exceeds Stop threshold'
        elif std >= c.slow_std_m or accepted_age >= c.slow_age_s:
            target, reason = 1, 'Uncertainty or accepted-fix age exceeds Slow threshold'
        else:
            target, reason = 0, 'Uncertainty and fix age within nominal thresholds'
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
                reason = 'Holding recommendation until sustained recovery'
        else:
            self.recovery_since = None
        return {'state': ('Normal', 'Slow', 'Stop')[self.level], 'reason': reason,
                'speed_scale': (1.0, .35, 0.0)[self.level]}


def apply_policy(result, config=PolicyConfig()):
    policy = SpeedPolicy(config)
    for frame in result['frames']:
        frame['policy'] = policy.step(frame['time'], frame.get('position_std_m'),
                                     frame.get('accepted_fix_age_s'), frame.get('initialized', False))
    return result
