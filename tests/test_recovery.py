import unittest
import numpy as np
from backend.recovery import RecoveryGuard


class RecoveryTests(unittest.TestCase):
    def test_teleport_and_persistent_shift_are_quarantined(self):
        guard=RecoveryGuard();cov=np.eye(2)*.04;shadow=np.zeros(3)
        self.assertTrue(guard.observe(0,np.zeros(2),shadow,0,cov,True,True)[0])
        self.assertFalse(guard.observe(.1,np.array([10.,0]),shadow,0,cov,True,False)[0])
        # Even a loose NIS gate must not accept the stable displaced cluster.
        for t in np.arange(.2,3,.1):
            self.assertFalse(guard.observe(float(t),np.array([10.,0]),shadow,0,cov,True,True)[0])
        for t in (3.,3.1,3.2,3.3):
            self.assertFalse(guard.observe(t,np.zeros(2),shadow,0,cov,True,True)[0])
        self.assertTrue(guard.observe(3.4,np.zeros(2),shadow,0,cov,True,True)[0])

    def test_guarded_recovery_requires_window_and_nearby_trusted_prediction(self):
        guard=RecoveryGuard();cov=np.eye(2)*.04;shadow=np.zeros(3)
        for t in (0,.1,.2,.3):
            self.assertFalse(guard.observe(t,np.array([1.,0]),shadow,0,cov,True,False)[0])
        allowed,recovery,_=guard.observe(.4,np.array([1.,0]),shadow,0,cov,True,False)
        self.assertTrue(allowed and recovery)
        guard=RecoveryGuard()
        for t in np.arange(0,2,.1):self.assertFalse(guard.observe(float(t),np.array([3.,0]),shadow,0,cov,True,False)[0])

    def test_degraded_samples_cannot_authorize_recovery(self):
        guard=RecoveryGuard();cov=np.eye(2)*.04;shadow=np.zeros(3)
        for t in np.arange(0,1,.1):self.assertFalse(guard.observe(float(t),np.array([1.,0]),shadow,0,cov,False,False)[0])
