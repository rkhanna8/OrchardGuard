import os
import unittest
import numpy as np
from backend.trust import FixTrust
from backend.run import run_localization
from backend.evaluation import confidence, probability_label
from frontend.policy import apply_policy, SpeedPolicy, PolicyConfig


class TrustTests(unittest.TestCase):
    def test_sustained_evidence_and_rejections(self):
        observer=FixTrust();r=np.array([.1,.1]);s=np.eye(2);m=np.eye(2)*.6
        for t in np.arange(0,2,.1):
            self.assertFalse(observer.observe(t,True,True,r,s,m)[0])
        self.assertTrue(observer.observe(2.1,True,True,r,s,m)[0])
        self.assertFalse(observer.observe(2.2,False,True,np.array([10.,0]),s,m)[0])
        self.assertFalse(observer.observe(2.3,True,True,r,s,m)[0])
        for t in np.arange(3,7,.1):
            self.assertFalse(observer.observe(t,True,True,np.array([1.,0]),s,m)[0])
        self.assertFalse(observer.observe(7,True,False,r,s,m)[0])
        self.assertFalse(observer.observe(8,True,True,r,s,np.eye(2)*2)[0])

    def test_policy_exact_limits_and_recovery(self):
        policy=SpeedPolicy(PolicyConfig(stop_age_s=10,recovery_s=3))
        f=policy.step(12,.4,12)
        self.assertEqual(f['state'],'Stop');self.assertIn('stop limit: 10 s',f['reason'])
        self.assertTrue(f['stop_predicates']['trusted_age_limit'])
        self.assertFalse(f['stop_predicates']['uncertainty_limit'])
        self.assertEqual(policy.step(13,.4,0)['state'],'Stop')
        self.assertEqual(policy.step(16,.4,0)['state'],'Slow')
        policy.step(17,.4,0)
        self.assertEqual(policy.step(20,.4,0)['state'],'Normal')
        self.assertIn('stop limit: 3 m',policy.step(21,4,0)['reason'])

    def test_probability_label(self):
        label=probability_label(confidence(np.eye(2)*.01,1),1)
        self.assertIn('Model-estimated chance of being within 1 m',label)
        self.assertIn('>99.9%',label);self.assertNotIn('100%',label)


@unittest.skipUnless(os.environ.get('ORCHARDGUARD_TEST_DATA'),'real ZIP not configured')
class RealTrustTests(unittest.TestCase):
    def test_moderate_outage_jump_recovery(self):
        base={'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],'trees':[], 'random_seed':42,'outage_enabled':False,'scenario_type':'recorded'}
        for quality in (.60,.62):
            result=apply_policy(run_localization({**base,'gps_quality':quality}))
            f=result['frames'][1324]
            self.assertAlmostEqual(f['time'],132.4)
            self.assertLess(f['accepted_fix_age_s'],.1);self.assertLess(f['trusted_fix_age_s'],.1)
            self.assertEqual(f['policy']['state'],'Normal')
            self.assertIn('sustained',f['trust_reason'])
            # Guard against inadvertently changing the EKF while fixing policy trust.
            self.assertAlmostEqual(f['position_error'],.1858843788 if quality==.6 else .3181739903,places=7)
        for scenario in ('outage','jump'):
            result=apply_policy(run_localization({**base,'gps_quality':1,'scenario_type':scenario,'fault_start_s':30,'fault_end_s':60,'jump_m':10}))
            self.assertFalse(any(u['accepted'] for u in result['gps_updates'] if 30<=u['time']<60))
            self.assertEqual(result['frames'][450]['policy']['state'],'Stop')
            self.assertEqual(result['frames'][700]['policy']['state'],'Normal')
        result=apply_policy(run_localization({**base,'gps_quality':.62,'scenario_type':'outage','fault_start_s':30,'fault_end_s':60}))
        self.assertEqual(result['frames'][450]['policy']['state'],'Stop')
        self.assertEqual(result['frames'][800]['policy']['state'],'Normal')

    def test_quality38_canopy_and_outage_recovery(self):
        base={'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],'gps_quality':.38,'random_seed':42,
              'trees':[{'x':6,'y':20,'radius_m':6,'severity':.7}]}
        result=apply_policy(run_localization(base))
        for index,expected in ((140,.5656348641),(260,.3033439170)):
            f=result['frames'][index]
            self.assertLess(f['trusted_fix_age_s'],4)
            self.assertEqual(f['policy']['state'],'Slow')
            self.assertAlmostEqual(f['position_error'],expected,places=7)
            self.assertAlmostEqual(f['time']-f['last_trusted_time_s'],f['trusted_fix_age_s'],places=5)
        outage=apply_policy(run_localization({**base,'scenario_type':'outage','fault_start_s':30,'fault_end_s':60}))
        self.assertEqual(outage['frames'][450]['policy']['state'],'Stop')
        self.assertFalse(any(u['accepted'] for u in outage['gps_updates'] if 30<=u['time']<60))
        self.assertTrue(any(f['policy']['state']=='Normal' for f in outage['frames'][700:900]))


class TimestampTests(unittest.TestCase):
    def test_age_requires_timestamp(self):
        from frontend.policy import trusted_age
        self.assertIsNone(trusted_age({'time':26,'trusted_fix_age_s':26}))
        self.assertIsNone(trusted_age({'time':26,'last_trusted_time_s':None}))
        self.assertIsNone(trusted_age({'time':26,'last_trusted_time_s':27}))
        self.assertEqual(trusted_age({'time':26,'last_trusted_time_s':25}),1)
        self.assertIn('No trusted fix yet',SpeedPolicy().step(26,.5,None)['reason'])
