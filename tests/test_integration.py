"""Frontend delivery logic without opening a Qt window."""
from concurrent.futures import Future
from types import SimpleNamespace
import unittest
from frontend.app import OrchardGuard


class Label:
    def __init__(self):self.text='';self.enabled=True
    def setText(self,text):self.text=text
    def setEnabled(self,enabled):self.enabled=enabled


class DeliveryTests(unittest.TestCase):
    def harness(self,future):
        applied=[];queued=[]
        state=SimpleNamespace(pending=future, use_backend=True, requested_scenario=None,
                              backend_error='', integration=Label(),mode=Label(),play=Label(),
                              poller=SimpleNamespace(stop=lambda:None),
                              apply_results=applied.append,start_backend=queued.append)
        return state,applied,queued

    def test_real_failure_does_not_substitute_mock(self):
        future=Future();future.set_exception(ValueError('invalid ZIP'))
        state,applied,_=self.harness(future)
        OrchardGuard.poll_backend(state)
        self.assertEqual(applied,[])
        self.assertIn('REAL DATA FAILED',state.integration.text)
        self.assertFalse(state.play.enabled)

    def test_superseded_result_is_discarded(self):
        future=Future();future.set_result({'old':True})
        state,applied,queued=self.harness(future);state.requested_scenario={'scenario_type':'jump'}
        OrchardGuard.poll_backend(state)
        self.assertEqual(applied,[]);self.assertEqual(queued,[{'scenario_type':'jump'}])

    def test_switch_to_mock_discards_pending_real_result(self):
        future=Future();future.set_result({'old':True})
        state,applied,_=self.harness(future);state.use_backend=False
        OrchardGuard.poll_backend(state)
        self.assertEqual(applied,[])

    def test_stale_advisory_does_not_replace_current_state(self):
        future=Future();future.set_result({'source':'Gemini','text':'old reply'})
        state=SimpleNamespace(advisor_pending=(((1,'old'),{},5),future),advisor_signature=(2,'new'),
                              results={'metadata':{'source':'mock'}},advice=Label())
        OrchardGuard.poll_advisor(state)
        self.assertEqual(state.advice.text,'')
