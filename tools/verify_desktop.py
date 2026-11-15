"""Native Qt interaction check; run from repository root, no physical actuation."""
import argparse
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QTimer, QEventLoop
from PySide6.QtTest import QTest
from frontend.app import OrchardGuard, create_application

parser = argparse.ArgumentParser()
parser.add_argument('--data', required=True)
args = parser.parse_args()
# Exercise deterministic fallback; live API is a separate explicit check.
os.environ.pop('GEMINI_API_KEY', None)
app = create_application()
window = OrchardGuard(); window.show()
beats = []
heartbeat = QTimer(); heartbeat.timeout.connect(lambda: beats.append(time.monotonic())); heartbeat.start(20)

def wait_events(milliseconds):
    # QTest.qWait can hold the Python GIL while the replay worker needs it.
    # A nested Qt event loop releases the GIL just like QApplication.exec().
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()

def wait_loaded():
    deadline = time.monotonic() + 30
    while window.pending is not None and time.monotonic() < deadline:
        wait_events(30)
    assert window.pending is None, 'background replay did not complete'
    assert window.results['metadata']['source'] == 'citrusfarm', window.integration.text()
    wait_events(100)

try:
    assert 'MOCK DATA' in window.mode.text()
    window.load_zip(args.data); wait_loaded()
    for scenario in range(3):
        window.scenario_box.setCurrentIndex(scenario); wait_loaded()
        window.timeline.setValue(450)
        assert window.farm.index == window.traj.index == window.error.index == window.index == 450
        assert window.results['frames'][450]['time'] > 44
        QTest.mouseClick(window.play, Qt.LeftButton); wait_events(300)
        QTest.mouseClick(window.play, Qt.LeftButton)
        assert window.index > 450
        window.timeline.setValue(450)
        if scenario:
            assert window.results['frames'][450]['policy']['state'] == 'Stop'
            assert 'Auto-stop triggered' in window.policy_label.text()
        Path('data').mkdir(exist_ok=True)
        assert window.grab().save(f'data/desktop-{scenario}.png')
        print(window.results['metadata']['scenario_label'],window.results['metrics'],flush=True)
        window.timeline.setValue(1600)
        assert window.grab().save(f'data/desktop-route-{scenario}.png')
        window.timeline.setValue(700)
        assert window.results['frames'][700]['policy']['state'] == 'Normal'
    # Add a canopy zone through the map mouse event, then verify recomputation.
    window.reset_scenario();wait_loaded()
    window.timeline.setValue(450)
    pose=window.results['frames'][450]['ground_truth']
    point=window.farm.project(pose['x'],pose['y']).toPoint()
    QTest.mouseClick(window.farm,Qt.LeftButton,pos=point);wait_loaded()
    assert len(window.results['metadata']['scenario']['trees'])==1
    assert 'SIMULATED' in window.results['metadata']['scenario_label']
    window.quality.setValue(70);wait_loaded()
    assert window.results['metadata']['scenario']['gps_quality']==.7
    window.reset_scenario();wait_loaded()
    assert not window.results['metadata']['scenario']['trees']
    # Switch to mock while real computation is running; stale output must not win.
    window.scenario_box.setCurrentIndex(0)
    window.real_toggle.setChecked(False)
    deadline=time.monotonic()+15
    while window.pending is not None and time.monotonic()<deadline:wait_events(30)
    assert window.results['metadata']['source']=='mock'
    assert 'MOCK DATA' in window.mode.text()
    assert len(beats)>10
    gaps=[b-a for a,b in zip(beats,beats[1:])]
    assert max(gaps)<1.5, f'UI heartbeat stalled {max(gaps):.3f}s'
    print(f'PASS native {app.platformName()}: ZIP loading, 3 scenarios, play/pause, seek, policy, mock switch; heartbeat max gap {max(gaps):.3f}s',flush=True)
finally:
    Path('data').mkdir(exist_ok=True)
    window.grab().save('data/desktop-last.png')
    window.close();app.processEvents()
