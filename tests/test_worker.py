"""Use the actual Qt event loop without opening a desktop window."""
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QCoreApplication, QTimer
from backend.run import run_localization


@unittest.skipUnless(os.environ.get('ORCHARDGUARD_TEST_DATA'),'set ORCHARDGUARD_TEST_DATA for worker replay')
class WorkerTests(unittest.TestCase):
    def test_replay_completes_while_qt_event_loop_runs(self):
        app=QCoreApplication.instance() or QCoreApplication([])
        pool=ThreadPoolExecutor(1)
        future=pool.submit(run_localization,{'data_path':os.environ['ORCHARDGUARD_TEST_DATA']})
        beats=[];started=time.monotonic()
        def poll():
            beats.append(time.monotonic())
            if future.done() or time.monotonic()-started>15:app.quit()
        timer=QTimer();timer.timeout.connect(poll);timer.start(20)
        app.exec();timer.stop()
        pool.shutdown(wait=False)
        self.assertTrue(future.done(),'worker timed out')
        self.assertGreater(len(future.result()['frames']),100)
        self.assertGreater(len(beats),2)
        self.assertLess(max(b-a for a,b in zip(beats,beats[1:])),1.5)
