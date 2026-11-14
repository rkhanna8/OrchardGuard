import math
import unittest
from frontend.mock_data import generate_mock_results

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.scenario={"gps_quality":0.8,"outage_enabled":False,"trees":[],"random_seed":42}

    def test_results_structure_and_errors(self):
        result=generate_mock_results(self.scenario)
        self.assertEqual(result["metadata"]["source"],"mock")
        frames=result["frames"]
        self.assertGreater(len(frames),10)
        self.assertEqual([f["time"] for f in frames], sorted(f["time"] for f in frames))
        for f in frames:
            self.assertAlmostEqual(f["position_error"],math.hypot(f["estimated"]["x"]-f["ground_truth"]["x"],f["estimated"]["y"]-f["ground_truth"]["y"]))
        self.assertAlmostEqual(result["metrics"]["rmse_m"],math.sqrt(sum(f["position_error"]**2 for f in frames)/len(frames)))

    def test_seed_reproducible(self):
        self.assertEqual(generate_mock_results(self.scenario),generate_mock_results(self.scenario))

    def test_outage_has_effect(self):
        normal=generate_mock_results(self.scenario)
        outage=generate_mock_results({**self.scenario,"outage_enabled":True})
        self.assertGreater(outage["metrics"]["rmse_m"],normal["metrics"]["rmse_m"])
        self.assertTrue(all(f["gps_status"]=="outage" for f in outage["frames"]))

if __name__=="__main__":
    unittest.main()
