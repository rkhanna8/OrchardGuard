import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from backend.run import correct, fault_fix, measurement, run_localization
from backend.evaluation import confidence, metrics
from backend.diagnostics import latest_diagnostics
from frontend.policy import PolicyConfig, SpeedPolicy, apply_policy
from frontend.advisor import explain, dashboard_values, local_summary


class FusionTests(unittest.TestCase):
    def test_gate_rejects_jump_ungated_accepts(self):
        state=np.zeros(3);cov=np.eye(3)*.1;fix=np.array([20.,0.]);noise=np.eye(2)*.04
        gated,pc,used=correct(state.copy(),cov.copy(),fix,noise)
        raw,pr,accepted=correct(state.copy(),cov.copy(),fix,noise,gate=False)
        self.assertFalse(used);self.assertTrue(accepted)
        np.testing.assert_array_equal(gated,state)
        self.assertGreater(raw[0],10)
        self.assertGreater(np.linalg.eigvalsh(pr).min(),0)

    def test_fault_boundaries_and_input_unchanged(self):
        fix=np.array([2.,3.]);s={'scenario_type':'outage','fault_start_s':10,'fault_end_s':20}
        np.testing.assert_array_equal(fault_fix(fix,9,0,s),fix)
        self.assertIsNone(fault_fix(fix,10,0,s));self.assertIsNone(fault_fix(fix,19.99,0,s))
        np.testing.assert_array_equal(fault_fix(fix,20,0,s),fix)
        np.testing.assert_array_equal(fault_fix(fix,12,0,{**s,'scenario_type':'jump','jump_m':8}),[2,11])
        np.testing.assert_array_equal(fix,[2,3])

    def test_validity_freshness_and_covariance(self):
        row=np.array([100.,2,3,2,.0049,.0049,0,0,1,99.99])
        self.assertIsNotNone(measurement(row,1)[0])
        row[3]=-1;self.assertIn('invalid',measurement(row,1)[1])
        row[3]=2;row[9]=90;self.assertIn('stale',measurement(row,1)[1])
        row[9]=100;row[4]=-1;self.assertIsNone(measurement(row,1)[0])
        row[8]=0;self.assertIsNotNone(measurement(row,1)[0])

    def test_confidence_gaussian_and_invalid(self):
        self.assertAlmostEqual(confidence(np.eye(2),2),100*(1-math.exp(-2)),places=8)
        self.assertIsNone(confidence(np.zeros((2,2)),2))
        self.assertIsNone(confidence([[float('nan'),0],[0,1]],2))
        self.assertLess(confidence(np.diag([1,9]),2),confidence(np.eye(2),2))

    def test_causal_diagnostics_and_staleness(self):
        data=([10.,20.],[{'time':10.,'num_sat':42},{'time':20.,'num_sat':38}])
        self.assertFalse(latest_diagnostics(data,9)['available'])
        self.assertEqual(latest_diagnostics(data,11)['num_sat'],42)
        self.assertEqual(latest_diagnostics(data,19)['reason'],'stale')
        self.assertEqual(latest_diagnostics(data,20)['num_sat'],38)

    def test_recovery_requires_sustained_dwell(self):
        frames=[{'time':t,'error':e} for t,e in enumerate([0,3,3,0,3,0,0,0,0])]
        m=metrics(frames,'error',1,3,2,2)
        self.assertEqual(m['fault_within_tolerance_s'],0)
        self.assertEqual(m['recovery_s'],4)
        self.assertEqual(metrics(frames[:6],'error',1,3,2,2)['recovery_status'],'did not recover')


class PolicyTests(unittest.TestCase):
    def test_escalation_and_sustained_stepwise_recovery(self):
        p=SpeedPolicy()
        self.assertEqual(p.step(0,.2,0)['state'],'Normal')
        self.assertEqual(p.step(2,.2,2)['state'],'Slow')
        self.assertEqual(p.step(8,.2,8)['state'],'Stop')
        self.assertEqual(p.step(9,.2,0)['state'],'Stop')
        self.assertEqual(p.step(11,.2,0)['state'],'Stop')
        self.assertEqual(p.step(12,.2,0)['state'],'Slow')
        self.assertEqual(p.step(13,.2,0)['state'],'Slow')
        self.assertEqual(p.step(16,.2,0)['state'],'Normal')
        self.assertEqual(p.step(17,None,None,False)['state'],'Stop')

    def test_invalid_thresholds(self):
        with self.assertRaises(ValueError):PolicyConfig(slow_std_m=4)


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.values=dashboard_values({'gps_decision':'rejected','gps_reason':'innovation gate',
                                     'position_std_m':3.,'policy':{'state':'Stop','reason':'uncertainty'}})

    def test_missing_key_deterministic_no_network(self):
        with patch.dict(os.environ,{},clear=True):
            def fail(*a,**k):raise AssertionError('network called')
            result=explain(self.values,opener=fail)
            self.assertEqual(result['text'],local_summary(self.values))
            self.assertEqual('Offline summary',result['source'])

    def test_api_failure_fallback_does_not_leak(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-secret'}):
            def fail(*a,**k):raise RuntimeError('test-secret')
            result=explain(self.values,opener=fail)
            self.assertEqual(result['text'],local_summary(self.values))
            self.assertNotIn('test-secret',str(result))

    def test_success_is_only_advice(self):
        import io
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-secret'}):
            def respond(request,timeout):
                self.assertEqual(timeout,12)
                return io.BytesIO(json.dumps({'candidates':[{'content':{'parts':[{'text':'Model uncertainty is high.'}]}}]}).encode())
            self.assertEqual('Offline summary',explain(self.values,opener=respond)['source'])
            self.assertEqual(self.values['policy']['state'],'Stop')


@unittest.skipUnless(os.environ.get('ORCHARDGUARD_TEST_DATA'),'set ORCHARDGUARD_TEST_DATA for real ZIP checks')
class RealReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results={k:run_localization({'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],
                                        'scenario_type':k}) for k in ('recorded','outage','jump')}

    def test_common_initialization_and_outage_predictions(self):
        results=self.results
        self.assertEqual(results['recorded']['frames'][0]['estimated'],results['outage']['frames'][0]['estimated'])
        self.assertEqual(results['jump']['frames'][0]['estimated'],results['outage']['frames'][0]['estimated'])
        updates=[u for u in results['outage']['gps_updates'] if u['fault_active']]
        self.assertGreater(len(updates),0);self.assertFalse(any(u['accepted'] or u['ungated_accepted'] for u in updates))
        frames=[f for f in results['outage']['frames'] if f['fault_active']]
        self.assertFalse(any(f['gps_accepted'] for f in frames))
        self.assertGreater(math.dist(list(frames[0]['estimated'].values())[:2],list(frames[-1]['estimated'].values())[:2]),1)

    def test_jump_isolates_gate(self):
        r=self.results['jump'];updates=[u for u in r['gps_updates'] if u['fault_active']]
        self.assertFalse(any(u['accepted'] for u in updates))
        self.assertTrue(all(u['ungated_accepted'] for u in updates))
        self.assertLess(r['metrics']['comparisons']['gated']['rmse_m'],r['metrics']['comparisons']['ungated']['rmse_m'])
        self.assertEqual(self.results['recorded']['metrics']['comparisons']['gated'],self.results['recorded']['metrics']['comparisons']['ungated'])

    def test_serialization_errors_and_clock_contract(self):
        for r in self.results.values():
            json.dumps(r,allow_nan=False)
            self.assertLess(r['metadata']['audit']['gps_reference_max_m'],.1)
            self.assertTrue(all(b['time']>a['time'] for a,b in zip(r['frames'],r['frames'][1:])))
            for f in r['frames']:
                self.assertAlmostEqual(f['position_error'],math.hypot(f['estimated']['x']-f['ground_truth']['x'],f['estimated']['y']-f['ground_truth']['y']))

    def test_no_reference_fused(self):
        from backend.recording import load
        p=Path(os.environ['ORCHARDGUARD_TEST_DATA']);st=p.stat()
        w,i,g,r,a=load(str(p),st.st_mtime_ns,st.st_size)
        changed=r.copy();changed[:,1:]+=100
        with patch('backend.run.load',return_value=(w,i,g,changed,a)):
            result=run_localization({'data_path':str(p)})
        for before,after in zip(self.results['recorded']['frames'],result['frames']):
            self.assertEqual(before['estimated'],after['estimated'])
        self.assertGreater(result['metrics']['rmse_m'],100)

    def test_policy_replay_determinism(self):
        r=apply_policy(self.results['outage'])
        policy=[f['policy'] for f in r['frames']]
        self.assertIn('Slow',[p['state'] for p in policy]);self.assertIn('Stop',[p['state'] for p in policy])
        self.assertEqual(policy,[f['policy'] for f in apply_policy(r)['frames']])

    def test_canopy_and_quality_change_only_gps_input(self):
        before=self.results['recorded']
        center=before['frames'][400]['ground_truth']
        result=run_localization({'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],
                                'trees':[{'x':center['x'],'y':center['y'],'radius_m':10,'severity':1}],
                                'gps_quality':.7,'random_seed':42,'diagnostics_path':'/missing/receiver.csv'})
        again=run_localization({'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],
                                'trees':[{'x':center['x'],'y':center['y'],'radius_m':10,'severity':1}],
                                'gps_quality':.7,'random_seed':42,'diagnostics_path':'/missing/receiver.csv'})
        self.assertEqual(result,again)
        self.assertTrue(any(u['decision']=='unavailable' for u in result['gps_updates']))
        self.assertFalse(any(f['receiver']['available'] for f in result['frames']))
        self.assertTrue(all(f['satellites'] is None for f in result['frames']))
        for old,new in zip(before['frames'],result['frames']):
            self.assertEqual(old['baseline'],new['baseline'])
            self.assertEqual(old['wheel_imu'],new['wheel_imu'])
            self.assertEqual(old['ground_truth'],new['ground_truth'])
        self.assertNotEqual(before['metrics']['rmse_m'],result['metrics']['rmse_m'])

    def test_covariance_fix_prevents_restoration_cascade(self):
        scenario={'data_path':os.environ['ORCHARDGUARD_TEST_DATA'],'gps_quality':.2,'quality_end_s':90,'legacy_sensor_offset':True,'calibrate_wheel_scale':False,'guarded_recovery':False}
        before=run_localization({**scenario,'legacy_noise_covariance':True})
        after=run_localization(scenario)
        old=[u for u in before['gps_updates'] if u['time']>=90]
        new=[u for u in after['gps_updates'] if u['time']>=90]
        self.assertTrue(all(u['candidate_health']=='healthy' and u['decision']=='rejected' for u in old[:100]))
        self.assertTrue(new[0]['accepted'])
        self.assertLess(after['metrics']['rmse_m'],before['metrics']['rmse_m'])
        for u in after['gps_updates']:
            self.assertGreaterEqual(u['prediction']['wheel_age_s'],0)
            self.assertGreaterEqual(u['prediction']['imu_age_s'],0)
            self.assertGreater(np.linalg.eigvalsh(u['pose_covariance']).min(),0)
            if u['nis'] is not None:
                residual=np.array(u['innovation']);S=np.array(u['innovation_covariance'])
                self.assertAlmostEqual(float(residual@np.linalg.solve(S,residual)),u['nis'])

    def test_tolerance_does_not_change_filter_or_policy_thresholds(self):
        path=os.environ['ORCHARDGUARD_TEST_DATA']
        a=run_localization({'data_path':path,'tolerance_m':.5,'outage_enabled':True})
        b=run_localization({'data_path':path,'tolerance_m':2.,'outage_enabled':True})
        self.assertFalse(any(u['accepted'] or u['ungated_accepted'] for u in a['gps_updates']))
        apply_policy(a);apply_policy(b)
        for x,y in zip(a['frames'],b['frames']):
            self.assertEqual(x['estimated'],y['estimated']);self.assertEqual(x['position_covariance'],y['position_covariance'])
            self.assertEqual(x['policy'],y['policy'])

    def test_initialization_calibration_is_causal_and_uses_no_reference(self):
        r=self.results['recorded'];meta=r['metadata']
        self.assertAlmostEqual(meta['wheel_scale'],.9067395932264634,places=6)
        self.assertEqual(meta['wheel_scale_calibration_end_unix_s'],meta['replay_start_unix_s'])
        from backend.recording import load
        p=Path(os.environ['ORCHARDGUARD_TEST_DATA']);st=p.stat();w,i,g,ref,a=load(str(p),st.st_mtime_ns,st.st_size)
        changed=g.copy();changed[changed[:,0]>meta['replay_start_unix_s']+30,1:3]+=100
        with patch('backend.run.load',return_value=(w,i,changed,ref,a)):
            future_changed=run_localization({'data_path':str(p)})
        self.assertEqual(future_changed['metadata']['wheel_scale'],meta['wheel_scale'])
        for before,after in zip(r['frames'],future_changed['frames']):
            if before['time']>=30:break
            self.assertEqual(before['estimated'],after['estimated'])
