"""Guard abrupt position discontinuities without using fault flags or reference.

A consistent shifted cluster is not enough: recovery must also lie near the
wheel/IMU continuation of the last trusted fused pose. This deliberately refuses
large uncertain global relocalizations instead of guessing which cluster is real.
"""
from collections import deque
import numpy as np


class RecoveryGuard:
    def __init__(self, radius_m=2.0, samples=5):
        self.radius=radius_m
        self.history=deque(maxlen=samples)
        self.previous=None
        self.quarantined=False

    def observe(self,time,fix,shadow,speed,covariance,healthy,nis_passed):
        if not healthy:
            self.history.clear();self.previous=None
            return nis_passed,False,'innovation gate'
        if self.previous is not None:
            last_time,last_fix,last_cov=self.previous;dt=time-last_time
            # Four-sigma position-change envelope plus recorded forward travel.
            limit=max(1.,abs(speed)*max(0,dt)+4*np.sqrt(np.trace(covariance+last_cov)))
            if 0<dt<=1 and np.linalg.norm(fix-last_fix)>limit:
                self.quarantined=True;self.history.clear()
        self.previous=(time,fix.copy(),covariance.copy())
        offset=fix-shadow[:2]
        if self.history and time-self.history[-1][0]>.5:self.history.clear()
        self.history.append((time,offset.copy()))
        consistent=False
        if len(self.history)==self.history.maxlen:
            age=self.history[-1][0]-self.history[0][0]
            offsets=np.array([v for _,v in self.history])
            consistent=(.3<=age<=1 and np.max(np.linalg.norm(offsets-np.median(offsets,axis=0),axis=1))<=.5)
        if self.quarantined or not nis_passed:
            if consistent and np.linalg.norm(offset)<=self.radius:
                self.quarantined=False
                return True,not nis_passed,'five consistent fresh fixes near trusted prediction'
            return False,False,('GPS displacement quarantine; waiting for consistent fixes near trusted prediction'
                                if self.quarantined else 'innovation NIS exceeds 9.21 (2-D gate)')
        return True,False,'innovation gate'
