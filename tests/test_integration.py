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
        self.assertTrue(state.play.enabled)

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


class MapTransformTests(unittest.TestCase):
    def test_cover_resize_zoom_and_clicked_zone_share_metric_transform(self):
        from types import MethodType
        from PySide6.QtCore import QPointF,QPoint,Qt
        from PySide6.QtGui import QImage
        from frontend.app import Sketch
        for width,height in ((1100,360),(500,700),(1600,450)):
            emitted=[]
            state=SimpleNamespace(real=True,registered=True,kind='farm',zoom=1.,pan=QPointF(0,0),
                                  map_image=QImage(2172,724,QImage.Format_ARGB32),width=lambda:width,height=lambda:height,
                                  update=lambda:None,frames=[{}],drag_start=QPointF(1,1),dragged=False,
                                  tree_added=SimpleNamespace(emit=lambda x,y:emitted.append((x,y))))
            state.image_view=MethodType(Sketch.image_view,state);state.transform=MethodType(Sketch.transform,state)
            scale,origin=state.image_view()
            self.assertLessEqual(origin.x(),0);self.assertLessEqual(origin.y(),0)
            self.assertGreaterEqual(origin.x()+2172*scale,width-.001)
            self.assertGreaterEqual(origin.y()+724*scale,height-.001)
            event=SimpleNamespace(position=lambda:QPointF(width/2,height/2),angleDelta=lambda:QPoint(0,120),accept=lambda:None)
            Sketch.wheelEvent(state,event)
            self.assertGreater(state.zoom,1)
            pos=state.transform().map(QPointF(12,30))
            click=SimpleNamespace(position=lambda:pos,button=lambda:Qt.LeftButton)
            Sketch.mouseReleaseEvent(state,click)
            self.assertAlmostEqual(emitted[0][0],12);self.assertAlmostEqual(emitted[0][1],30)
