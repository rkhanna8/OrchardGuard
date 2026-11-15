import csv,io,json,math,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from backend.run import run_localization
from backend.evaluation import confidence,probability_label
from backend.recording import sample_reference


def make_fixture(path,sequence='fixture_B',*,mixed=False,gap=False,bad=False,diagnostics=False):
    """Synthetic second-sequence regression fixture; never claimed CitrusFarm data."""
    start=1700000000.;lat=34.;lon=-118.;east_radius=6378137*math.cos(math.radians(lat))/math.sqrt(1-.00669437999014*math.sin(math.radians(lat))**2)
    def csv_text(header,rows):
        out=io.StringIO();writer=csv.writer(out);writer.writerow(header);writer.writerows(rows);return out.getvalue()
    times=np.arange(0,45,.1)
    with ZipFile(path,'w') as z:
        z.writestr('metadata.json',json.dumps({'sequence':sequence,'source':'fixture','reference_frame':'enu',
                                            'sensor_sequences':{'wheel':sequence,'imu':'wrong' if mixed else sequence}}))
        z.writestr('wheel.csv',csv_text(['bag_time_ns','speed_mps','yaw_rate_rad_s','frame_id'],[[int((start+t)*1e9),1,0,'base_link'] for t in times]))
        z.writestr('imu.csv',csv_text(['bag_time_ns','gyro_z_rad_s','frame_id'],[[int((start+t+(100 if gap else 0))*1e9),0,'microstrain_link'] for t in times]))
        header=['bag_time_ns','latitude_deg','longitude_deg','fix_status','cov_ee','cov_nn','cov_en','cov_ne','covariance_type','header_time_ns','frame_id']
        if bad:header[1]='wrong'
        z.writestr('gps.csv',csv_text(header,[[int((start+t)*1e9),lat,lon+math.degrees(t/east_radius),2,.0049,.0049,0,0,1,int((start+t)*1e9),'base_link'] for t in times]))
        z.writestr('gt.csv',''.join(f'{start+t},{t},0\n' for t in times))
        if diagnostics:
            z.writestr('receiver_state.csv',csv_text(['bag_time_ns','num_sat','rtk_mode_fix','fix_mode','system_error','io_error','swift_nap_error','external_antenna_present'],[[int((start+3)*1e9),8,1,'FIXED_RTK',0,0,0,1]]))
    return path


class SequenceTests(unittest.TestCase):
    def test_sequence_identity_origin_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_fixture(Path(d)/'b.zip',diagnostics=True)
            r=run_localization({'data_path':str(p)})
            self.assertEqual(r['metadata']['sequence'],'fixture_B')
            self.assertEqual(r['metadata']['source'],'mock')
            self.assertFalse(r['metadata']['map_registered'])
            self.assertEqual(r['metadata']['audit']['origin_lla'],[34.,-118.])
            self.assertTrue(any(f['satellites']==8 for f in r['frames']))
            self.assertIsNone(r['frames'][-1]['satellites'])
            self.assertLess(r['metrics']['rmse_m'],.01)

    def test_reject_mixed_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as d:
            for name,options in [('mixed',{'mixed':True}),('wrong',{'sequence':'01_13B_Jackal'}),('overlap',{'gap':True})]:
                with self.subTest(name=name):
                    p=make_fixture(Path(d)/(name+'.zip'),**options)
                    with self.assertRaises(ValueError):run_localization({'data_path':str(p)})

    def test_malformed_file_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_fixture(Path(d)/'bad.zip',bad=True)
            with self.assertRaises((ValueError,KeyError)):run_localization({'data_path':str(p)})

    def test_reference_gaps_are_not_interpolated(self):
        ref=np.array([[0,0,0],[.1,1,0],[2,20,0],[2.1,21,0]])
        result=sample_reference(ref,np.array([-.1,.05,1.,2.05,3]))
        self.assertTrue(np.isnan(result[[0,2,4]]).all())
        np.testing.assert_allclose(result[[1,3],0],[.5,20.5])

    def test_anisotropic_probability_matches_sampling(self):
        rng=np.random.default_rng(42)
        cov=np.array([[4.,1.5],[1.5,1.]])
        samples=rng.multivariate_normal([0,0],cov,200000)
        observed=100*np.mean(np.linalg.norm(samples,axis=1)<=1)
        self.assertAlmostEqual(confidence(cov,1),observed,delta=.3)
        self.assertIn('>99.9%',probability_label(99.9999,2))
        self.assertNotIn('100.0%',probability_label(100,2))
        self.assertIsNone(confidence([[1,1],[0,1]],1))

    def test_single_teleport_remains_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_fixture(Path(d)/'b.zip')
            r=run_localization({'data_path':str(p),'scenario_type':'jump','fault_start_s':10,'fault_end_s':10.05,'jump_m':20})
            during=[u for u in r['gps_updates'] if u['fault_active']]
            self.assertEqual(len(during),1)
            self.assertFalse(during[0]['accepted'])
            self.assertEqual(during[0]['candidate_health'],'healthy')
            self.assertEqual(during[0]['gate_threshold'],9.21)
            self.assertGreater(during[0]['nis'],9.21)


if __name__=='__main__':unittest.main()
