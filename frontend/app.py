"""Native PySide6 OrchardGuard prototype. Run: python -m frontend.app."""
from __future__ import annotations
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)
from frontend.mock_data import generate_mock_results

BG = "#111b24"
PANEL = "#1b2b36"
TEXT = "#ecf4f4"
MUTED = "#a8bdc6"
TRUTH = "#4fa8ff"
EST = "#ffb454"
BASELINE = "#a5a9b2"

class Sketch(QWidget):
    tree_added = Signal(float,float)
    def __init__(self, kind:str, parent=None):
        super().__init__(parent)
        self.kind=kind
        self.frames=[]
        self.index=0
        self.trees=[]
        self.setMinimumHeight(280 if kind=="farm" else 180)

    def set_data(self, frames, index, trees):
        self.frames,self.index,self.trees=frames,index,trees
        self.update()

    def limits(self):
        pts=[]
        for f in self.frames:
            for key in ("ground_truth","estimated","baseline"):
                pts.append((f[key]["x"],f[key]["y"]))
        for t in self.trees:pts.append((t["x"],t["y"]))
        if not pts:return (0,100,0,55)
        xs=[p[0] for p in pts];ys=[p[1] for p in pts]
        a,b=min(xs)-7,max(xs)+7;c,d=min(ys)-8,max(ys)+8
        return a,b,c,d

    def project(self,x,y):
        a,b,c,d=self.limits()
        w=max(1,self.width()-36);h=max(1,self.height()-36)
        # Equal X/Y scales, with centered padding.
        sc=min(w/max(0.001,b-a),h/max(0.001,d-c))
        ox=(self.width()-(b-a)*sc)/2
        oy=(self.height()-(d-c)*sc)/2
        return QPointF(ox+(x-a)*sc,self.height()-oy-(y-c)*sc)

    def mousePressEvent(self,event):
        if self.kind!="farm" or not self.frames:return
        a,b,c,d=self.limits()
        w=max(1,self.width()-36);h=max(1,self.height()-36)
        sc=min(w/max(0.001,b-a),h/max(0.001,d-c))
        ox=(self.width()-(b-a)*sc)/2
        oy=(self.height()-(d-c)*sc)/2
        x=a+(event.position().x()-ox)/sc
        y=c+(self.height()-oy-event.position().y())/sc
        self.tree_added.emit(x,y)

    def line(self,p,pts,color,width=2,dashed=False):
        if len(pts)<2:return
        pen=QPen(QColor(color),width)
        if dashed:pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        for i in range(1,len(pts)):
            p.drawLine(self.project(*pts[i-1]),self.project(*pts[i]))

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#152630" if self.kind=="farm" else PANEL))
        if not self.frames:return
        k=min(self.index,len(self.frames)-1)
        if self.kind=="farm":
            a,b,c,d=self.limits()
            p.setPen(Qt.NoPen)
            # Stylized orchard rows, NOT actual surveyed tree geometry.
            j=0
            while a+9+j*12<b:
                yy=c+8
                while yy<d:
                    center=self.project(a+9+j*12,yy)
                    p.setBrush(QColor("#315c43"))
                    p.drawEllipse(center,6,6)
                    yy+=10
                j+=1
            for tree in self.trees:
                center=self.project(tree["x"],tree["y"])
                p.setPen(QPen(QColor("#cfa45f"),1,Qt.DashLine))
                p.setBrush(QColor(222,148,70,35))
                point=self.project(tree["x"]+tree["radius_m"],tree["y"])
                rad=abs(point.x()-center.x())
                p.drawEllipse(center,rad,rad)
                p.setPen(Qt.NoPen);p.setBrush(QColor("#e6b55c"));p.drawEllipse(center,6,6)
        shown=self.frames[:k+1]
        for key,color,dash in (("ground_truth",TRUTH,False),("baseline",BASELINE,True),("estimated",EST,False)):
            self.line(p,[(f[key]["x"],f[key]["y"]) for f in shown],color,2,dash)
        f=self.frames[k]
        for key,color,r in (("ground_truth",TRUTH,5),("estimated",EST,7)):
            xy=self.project(f[key]["x"],f[key]["y"])
            p.setPen(QPen(QColor("#f0f4f5"),1))
            p.setBrush(QBrush(QColor(color)))
            p.drawEllipse(xy,r,r)
        p.setPen(QColor(MUTED))
        p.drawText(10,18,"CLICK TO ADD CANOPY ZONE" if self.kind=="farm" else "X–Y TRAJECTORY (meters)")

class ErrorPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.frames=[];self.index=0;self.setMinimumHeight(175)
    def set_data(self,frames,index):
        self.frames=frames;self.index=index;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor(PANEL))
        p.setPen(QColor(MUTED));p.drawText(12,17,"POSITION ERROR vs TIME (meters)")
        if not self.frames:return
        left,top,right,bottom=38,30,self.width()-13,self.height()-25
        maxv=max(0.2,max(max(f["position_error"],f["baseline_error"]) for f in self.frames)*1.15)
        n=len(self.frames)
        def xy(i,val):return QPointF(left+(right-left)*i/max(1,n-1),bottom-(bottom-top)*val/maxv)
        p.setPen(QPen(QColor("#536977"),1))
        p.drawLine(left,bottom,right,bottom);p.drawLine(left,top,left,bottom)
        p.drawText(4,top+5,f"{maxv:.1f}");p.drawText(9,bottom+3,"0")
        for key,color in (("baseline_error",BASELINE),("position_error",EST)):
            p.setPen(QPen(QColor(color),2))
            for i in range(1,min(self.index+1,n)):
                p.drawLine(xy(i-1,self.frames[i-1][key]),xy(i,self.frames[i][key]))
        i=min(self.index,n-1);p.setPen(QPen(QColor("#6b8291"),1,Qt.DashLine))
        cursor=xy(i,0).x();p.drawLine(QPointF(cursor,top),QPointF(cursor,bottom))

class OrchardGuard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OrchardGuard — Desktop Localization Lab")
        self.resize(1200,790)
        self.scenario={"gps_quality":0.85,"outage_enabled":False,"trees":[],"random_seed":42}
        self.results={}
        self.index=0;self.playing=False
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.pending=None
        self.requested_scenario=None
        self.backend_error=""
        self.use_backend=False
        base=QWidget();self.setCentralWidget(base)
        root=QVBoxLayout(base);root.setSpacing(12);root.setContentsMargins(16,16,16,16)
        top=QHBoxLayout()
        title=QLabel("ORCHARDGUARD");title.setObjectName("title")
        top.addWidget(title);top.addStretch()
        self.mode=QLabel("MOCK DATA — SYNTHETIC TRAJECTORY");self.mode.setObjectName("warning")
        top.addWidget(self.mode);root.addLayout(top)
        body=QHBoxLayout();body.setSpacing(12);root.addLayout(body,1)
        left=QVBoxLayout();right=QVBoxLayout();body.addLayout(left,1);body.addLayout(right,1)
        left.addWidget(self.heading("Interactive orchard"))
        self.farm=Sketch("farm");self.farm.tree_added.connect(self.add_tree);left.addWidget(self.farm,1)
        self.scene=QLabel("Click orchard to place a virtual canopy zone (not measured tree locations).")
        self.scene.setWordWrap(True);left.addWidget(self.scene)
        self.zone_radius=QSpinBox();self.zone_radius.setRange(2,30)
        self.zone_radius.setValue(6);self.zone_radius.setSuffix(" m canopy radius")
        left.addWidget(self.zone_radius)
        ctl=QHBoxLayout()
        self.play=QPushButton("Play");self.play.clicked.connect(self.toggle_play);ctl.addWidget(self.play)
        reset=QPushButton("Restart");reset.clicked.connect(self.restart);ctl.addWidget(reset)
        clear=QPushButton("Clear trees");clear.clicked.connect(self.clear_trees);ctl.addWidget(clear)
        left.addLayout(ctl)
        left.addWidget(self.heading("Replay timeline"))
        self.timeline=QSlider(Qt.Horizontal);self.timeline.setRange(0,0)
        self.timeline.valueChanged.connect(self.scrub);left.addWidget(self.timeline)
        self.time_label=QLabel("0.0 s / 0.0 s");left.addWidget(self.time_label)
        left.addWidget(self.heading("GNSS reliability (synthetic)"))
        self.quality=QSlider(Qt.Horizontal);self.quality.setRange(0,100);self.quality.setValue(85)
        self.quality.valueChanged.connect(self.change_quality);left.addWidget(self.quality)
        self.quality_label=QLabel();left.addWidget(self.quality_label)
        self.outage=QCheckBox("Force complete GPS outage")
        self.outage.toggled.connect(self.change_outage);left.addWidget(self.outage)
        left.addWidget(self.heading("Playback speed"))
        self.speed=QSpinBox();self.speed.setRange(1,8);self.speed.setValue(2);self.speed.setSuffix("×")
        left.addWidget(self.speed)
        self.real_toggle=QCheckBox("Use CitrusFarm backend (when available)")
        self.real_toggle.toggled.connect(self.change_mode);left.addWidget(self.real_toggle)
        self.integration=QLabel("Synthetic demonstration — no real dataset loaded")
        self.integration.setWordWrap(True);left.addWidget(self.integration)
        right.addWidget(self.heading("Reference vs estimated pose"))
        self.traj=Sketch("trajectory");right.addWidget(self.traj,1)
        right.addWidget(self.heading("Localization error"))
        self.error=ErrorPlot();right.addWidget(self.error,1)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName("status")
        right.addWidget(self.status)
        legend=QLabel("BLUE  Ground truth   |   ORANGE  Estimated   |   GRAY  Wheel baseline")
        legend.setObjectName("muted");right.addWidget(legend)
        self.timer=QTimer(self);self.timer.setInterval(65);self.timer.timeout.connect(self.tick)
        self.poller=QTimer(self);self.poller.setInterval(100);self.poller.timeout.connect(self.poll_backend)
        self.update_scenario()

    def heading(self,t):
        l=QLabel(t);l.setObjectName("heading");return l
    def add_tree(self,x,y):
        self.scenario["trees"].append({"x":round(x,2),"y":round(y,2),"radius_m":float(self.zone_radius.value()),"severity":0.7})
        self.update_scenario()
    def clear_trees(self):
        self.scenario["trees"].clear();self.update_scenario()
    def change_quality(self,v):
        self.scenario["gps_quality"]=v/100;self.update_scenario()
    def change_outage(self,v):
        self.scenario["outage_enabled"]=v;self.update_scenario()
    def change_mode(self, enabled):
        self.use_backend=enabled
        self.backend_error=""
        self.update_scenario()

    def scrub(self, index):
        if self.results and self.results.get("frames"):
            self.index=min(index,len(self.results["frames"])-1)
            self.draw()

    @staticmethod
    def compute_backend(scenario):
        from backend.run import run_localization
        result=run_localization(scenario)
        if not isinstance(result,dict) or not result.get("frames"):
            raise ValueError("Backend returned no frames")
        if result.get("metadata",{}).get("source")!="citrusfarm":
            raise ValueError("Backend result must identify CitrusFarm source")
        return result

    def poll_backend(self):
        if self.pending is None or not self.pending.done():return
        future=self.pending;self.pending=None
        try:
            result=future.result()
        except Exception as exc:
            self.backend_error=f"{type(exc).__name__}: {exc}"
            result=generate_mock_results(self.scenario)
        if not self.use_backend:
            self.poller.stop()
            return
        if self.requested_scenario is not None:
            scenario=self.requested_scenario;self.requested_scenario=None
            self.start_backend(scenario)
            return
        self.apply_results(result)
        self.poller.stop()

    def start_backend(self,scenario):
        if self.pending is not None:
            self.requested_scenario=dict(scenario)
            self.integration.setText("Scenario queued; waiting for current calculation…")
            return
        self.integration.setText("Computing CitrusFarm localization in background…")
        self.pending=self.executor.submit(self.compute_backend,dict(scenario))
        self.poller.start()

    def apply_results(self,result):
        self.results=result
        self.index=min(self.index,len(result["frames"])-1)
        self.timeline.blockSignals(True)
        self.timeline.setRange(0,len(result["frames"])-1)
        self.timeline.setValue(self.index)
        self.timeline.blockSignals(False)
        source=result.get("metadata",{}).get("source","unknown")
        real=source=="citrusfarm"
        self.mode.setText("CITRUSFARM DATA" if real else "MOCK DATA — SYNTHETIC TRAJECTORY")
        self.integration.setText("Real recorded data; faults are synthetic." if real else
            ("Backend unavailable: "+self.backend_error+" — displaying mock data." if self.backend_error else
             "Synthetic demonstration — not measured CitrusFarm performance."))
        self.draw()

    def update_scenario(self):
        self.quality_label.setText(f"Quality: {self.scenario['gps_quality']:.0%}  |  Trees: {len(self.scenario['trees'])}")
        if self.use_backend:
            if not self.results:
                self.apply_results(generate_mock_results(self.scenario))
            self.start_backend(dict(self.scenario))
        else:
            self.requested_scenario=None
            self.backend_error=""
            self.apply_results(generate_mock_results(self.scenario))
    def draw(self):
        frames=self.results["frames"];self.farm.set_data(frames,self.index,self.scenario["trees"])
        self.traj.set_data(frames,self.index,[])
        self.error.set_data(frames,self.index)
        self.timeline.blockSignals(True);self.timeline.setValue(self.index);self.timeline.blockSignals(False)
        f=frames[self.index];m=self.results["metrics"]
        self.time_label.setText(f"{f['time']:.1f} s / {frames[-1]['time']:.1f} s")
        self.status.setText(f"t={f['time']:.2f}s  |  GPS: {f['gps_status'].upper()}  |  Current error: {f['position_error']:.2f} m  |  RMSE: {m['rmse_m']:.2f} m  |  σ: {f['position_std_m']:.2f} m")
    def toggle_play(self):
        self.playing=not self.playing
        self.play.setText("Pause" if self.playing else "Play")
        if self.playing:self.timer.start()
        else:self.timer.stop()
    def restart(self):
        self.index=0;self.draw()
    def tick(self):
        self.index=min(len(self.results["frames"])-1,self.index+self.speed.value())
        self.draw()
        if self.index==len(self.results["frames"])-1:self.playing=False;self.timer.stop();self.play.setText("Play")

    def closeEvent(self,event):
        self.timer.stop();self.poller.stop()
        self.executor.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)

def main():
    app=QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget { background: #111b24; color: #ecf4f4; font-family: Arial; font-size: 13px; }
        QLabel#title { font-size: 24px; font-weight: 800; color: #e9f3f2; }
        QLabel#heading { font-size: 15px; font-weight: 700; margin-top: 5px; }
        QLabel#warning { background: #764b20; color: #fff2d9; border-radius: 6px; padding: 8px; font-weight: bold; }
        QLabel#status { background: #1b2b36; border-radius: 8px; padding: 12px; }
        QLabel#muted { color: #a8bdc6; }
        QPushButton { background: #2c5868; border: 1px solid #487183; border-radius: 7px; padding: 9px; }
        QPushButton:hover { background: #376c7c; }
        QSpinBox { background: #1b2b36; padding: 5px; }
    """)
    window=OrchardGuard();window.show()
    return app.exec()

if __name__=="__main__":
    sys.exit(main())
