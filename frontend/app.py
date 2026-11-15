"""Native PySide6 OrchardGuard prototype. Run: python -m frontend.app."""
from __future__ import annotations
import math
import sys
import os
import copy
import time
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QImage, QTransform, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
    QComboBox, QFileDialog, QDialog, QScrollArea, QTabWidget)
from frontend.mock_data import generate_mock_results
from frontend.policy import PolicyConfig, apply_policy
from frontend.settings import DemoSettings
from frontend.advisor import dashboard_values, local_summary, state_key, explain
from frontend.map_registration import MATRIX, IMAGE


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
        self.real=False
        self._limits=None
        self.map_image=QImage(str(IMAGE)) if kind=='farm' else QImage()
        self.setMinimumHeight(290)

    def set_data(self, frames, index, trees):
        if self.frames is not frames or self.trees != trees:
            self._limits=None
        self.frames,self.index,self.trees=frames,index,trees
        self.update()

    def limits(self):
        if self._limits is not None:return self._limits
        pts=[]
        for f in self.frames:
            for key in ("ground_truth","estimated","baseline","ungated"):
                if key not in f:continue
                pts.append((f[key]["x"],f[key]["y"]))
        for t in self.trees:pts.append((t["x"],t["y"]))
        if not pts:return (0,100,0,55)
        xs=[p[0] for p in pts];ys=[p[1] for p in pts]
        a,b=min(xs)-7,max(xs)+7;c,d=min(ys)-8,max(ys)+8
        self._limits=(a,b,c,d)
        return self._limits

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
        p.drawPolyline(QPolygonF([self.project(x,y) for x,y in pts]))

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#152630" if self.kind=="farm" else PANEL))
        if not self.frames:return
        k=min(self.index,len(self.frames)-1)
        if self.kind=="farm" and self.real and not self.map_image.isNull():
            inverse=np.linalg.inv(np.vstack((MATRIX.T,[0,0,1])))
            def image_point(u,v):
                x,y,_=inverse @ np.array([u,v,1.0]);return self.project(x,y)
            origin=image_point(0,0);px=image_point(1,0);py=image_point(0,1)
            p.save();p.setTransform(QTransform(px.x()-origin.x(),px.y()-origin.y(),
                                             py.x()-origin.x(),py.y()-origin.y(),origin.x(),origin.y()))
            p.drawImage(0,0,self.map_image);p.restore()
        if self.kind=="farm":
            a,b,c,d=self.limits()
            p.setPen(Qt.NoPen)
            # Stylized orchard rows, NOT actual surveyed tree geometry.
            j=0
            while not self.real and a+9+j*12<b:
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
        if self.kind=='trajectory':
            a,b,c,d=self.limits();p.setPen(QPen(QColor('#294052'),1))
            for x in range(math.ceil(a/10)*10,math.floor(b/10)*10+1,10):p.drawLine(self.project(x,c),self.project(x,d))
            for y in range(math.ceil(c/10)*10,math.floor(d/10)*10+1,10):p.drawLine(self.project(a,y),self.project(b,y))
        shown=self.frames[:k+1]
        for key,color,dash in (("ground_truth",TRUTH,False),("baseline",BASELINE,True),("estimated",EST,False), ("ungated","#ee80b8",True), ("wheel_imu","#8dc7bd",True)):
            if key not in shown[0] or (key=="wheel_imu" and self.kind=="farm"):continue
            self.line(p,[(f[key]["x"],f[key]["y"]) for f in shown],color,2,dash)
        f=self.frames[k]
        if self.real and f.get('position_covariance'):
            cov=np.array(f['position_covariance']);values,vectors=np.linalg.eigh(cov)
            if np.all(values>0):
                angles=np.linspace(0,2*math.pi,65)
                offsets=vectors @ (np.sqrt(values[:,None]*5.991)*np.array([np.cos(angles),np.sin(angles)]))
                self.line(p,[(f['estimated']['x']+v[0],f['estimated']['y']+v[1]) for v in offsets.T], '#ffd58a',1)
        for key,color,r in (("ground_truth",TRUTH,5),("baseline",BASELINE,4),("ungated","#ee80b8",4),("estimated",EST,7)):
            if key not in f:continue
            xy=self.project(f[key]["x"],f[key]["y"])
            p.setPen(QPen(QColor("#f0f4f5"),1))
            p.setBrush(QBrush(QColor(color)))
            p.drawEllipse(xy,r,r)
        scale=abs(self.project(10,0).x()-self.project(0,0).x())
        p.setPen(QPen(QColor('#f1f6fc'),2));p.drawLine(QPointF(16,self.height()-25),QPointF(16+scale,self.height()-25))
        p.drawText(16,self.height()-32,'10 m · ENU')
        p.fillRect(QRectF(0,0,self.width(),27),QColor(12,19,28,205))
        p.setPen(QColor(MUTED))
        p.drawText(10,18,("SEQ 01 · WHITE ROUTE BAKED INTO FIGURE" if self.real else "CLICK TO ADD CANOPY ZONE") if self.kind=="farm" else "X–Y TRAJECTORY (meters)")

class ErrorPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.frames=[];self.index=0;self.setMinimumHeight(170);self.setMaximumHeight(230);self.fault_interval=(0,0)
    def set_data(self,frames,index):
        self.frames=frames;self.index=index;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor(PANEL))
        p.setPen(QColor(MUTED));p.drawText(12,17,"POSITION ERROR vs TIME (meters)")
        if not self.frames:return
        left,top,right,bottom=38,30,self.width()-13,self.height()-25
        maxv=max(0.2,max(max(f["position_error"],f["baseline_error"],f.get("ungated_error",0)) for f in self.frames)*1.15)
        n=len(self.frames)
        duration=max(.001,self.frames[-1]['time'])
        def tx(t):return left+(right-left)*t/duration
        def xy(i,val):return QPointF(tx(self.frames[i]['time']),bottom-(bottom-top)*val/maxv)
        start,end=self.fault_interval
        if end>start:
            x1,x2=tx(max(0,start)),tx(min(duration,end))
            if x2>x1:p.fillRect(QRectF(x1,top,x2-x1,bottom-top),QColor(230,132,87,22))
        p.setPen(QPen(QColor('#2b3d50'),1))
        for fraction in (.25,.5,.75):
            y=bottom-(bottom-top)*fraction;p.drawLine(QPointF(left,y),QPointF(right,y))
        p.setPen(QColor(MUTED))
        for fraction in (0,.25,.5,.75,1):
            t=duration*fraction;p.drawText(QPointF(tx(t)-10,bottom+17),f'{t:.0f}s')
        p.setPen(QPen(QColor("#536977"),1))
        p.drawLine(left,bottom,right,bottom);p.drawLine(left,top,left,bottom)
        p.drawText(4,top+5,f"{maxv:.1f}");p.drawText(9,bottom+3,"0")
        for key,color in (("baseline_error",BASELINE),("position_error",EST),("ungated_error","#ee80b8")):
            if key not in self.frames[0]:continue
            p.setPen(QPen(QColor(color),2))
            p.drawPolyline(QPolygonF([xy(i,self.frames[i][key]) for i in range(min(self.index+1,n))]))
        i=min(self.index,n-1);p.setPen(QPen(QColor("#6b8291"),1,Qt.DashLine))
        cursor=xy(i,0).x();p.drawLine(QPointF(cursor,top),QPointF(cursor,bottom))

class OrchardGuard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OrchardGuard — Desktop Localization Lab")
        self.resize(1340,900)
        self.setMinimumSize(1050,740)
        self.scenario={"gps_quality":1.0,"outage_enabled":False,"trees":[],"random_seed":42}
        self.results={}
        self.index=0;self.playing=False
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.pending=None
        self.requested_scenario=None
        self.backend_error=""
        self.use_backend=False
        self.policy_config=PolicyConfig()
        self.advisor_executor=ThreadPoolExecutor(max_workers=1)
        self.advisor_pending=None
        self.advisor_signature=None
        self.advisor_generation=0
        self.advisor_last_request=0
        self.applied_scenario=copy.deepcopy(self.scenario)
        base=QWidget();self.setCentralWidget(base)
        root=QVBoxLayout(base);root.setSpacing(12);root.setContentsMargins(20,16,20,14)
        top=QHBoxLayout()
        branding=QVBoxLayout();branding.setSpacing(0)
        title=QLabel('ORCHARDGUARD');title.setObjectName('title');branding.addWidget(title)
        subtitle=QLabel('LOCALIZATION LAB  /  CITRUSFARM SEQUENCE 01');subtitle.setObjectName('muted');branding.addWidget(subtitle)
        top.addLayout(branding);top.addStretch()
        self.mode=QLabel('MOCK DATA — SYNTHETIC TRAJECTORY');self.mode.setObjectName('warning');top.addWidget(self.mode)
        select=QPushButton('Open sensor ZIP');select.clicked.connect(self.select_zip);top.addWidget(select)
        root.addLayout(top)
        summary=QHBoxLayout();summary.setSpacing(10)
        self.kpis={}
        for key,title,unit in [('error','CURRENT RTK REFERENCE ERROR','m'),('rmse','GATED EKF · REPLAY RMSE','m'),('std','MODEL UNCERTAINTY · √trace(P)','m'),('sat','RECORDED SATELLITES','')]:
            card=QFrame();card.setObjectName('card');box=QVBoxLayout(card);box.setContentsMargins(14,10,14,10);box.setSpacing(2)
            label=QLabel(title);label.setObjectName('muted');box.addWidget(label)
            value=QLabel('—');value.setObjectName('value');box.addWidget(value);self.kpis[key]=value
            summary.addWidget(card,1)
        root.addLayout(summary)
        body=QHBoxLayout();body.setSpacing(14);root.addLayout(body,1)
        left=QVBoxLayout();left.setSpacing(9);body.addLayout(left,1)
        map_header=QHBoxLayout();map_header.addWidget(self.heading('Orchard replay'))
        map_header.addStretch()
        map_header.addWidget(QLabel('<span style="color:#66baff">● RTK reference</span>   <span style="color:#ffc06a">● Gated EKF</span>   <span style="color:#ed87c1">● Ungated</span>   <span style="color:#a5a9b2">● Wheel</span>'))
        left.addLayout(map_header)
        self.map_tabs=QTabWidget()
        self.farm=Sketch('farm');self.farm.tree_added.connect(self.add_tree)
        self.traj=Sketch('trajectory')
        self.map_tabs.addTab(self.farm,'Orchard image');self.map_tabs.addTab(self.traj,'Metric view')
        left.addWidget(self.map_tabs,4)
        self.scene=QLabel();self.scene.setObjectName('muted');self.scene.setWordWrap(True);left.addWidget(self.scene)
        self.error=ErrorPlot();left.addWidget(self.error,2)
        playback=QHBoxLayout()
        self.play=QPushButton('Play');self.play.setObjectName('primary');self.play.clicked.connect(self.toggle_play);playback.addWidget(self.play)
        restart=QPushButton('Restart');restart.clicked.connect(self.restart);playback.addWidget(restart)
        self.speed=QSpinBox();self.speed.setRange(1,8);self.speed.setValue(2);self.speed.setSuffix('×');self.speed.setToolTip('Replay speed');playback.addWidget(self.speed)
        self.timeline=QSlider(Qt.Horizontal);self.timeline.setRange(0,0);self.timeline.valueChanged.connect(self.scrub);playback.addWidget(self.timeline,1)
        self.time_label=QLabel('0.0 / 0.0 s');self.time_label.setMinimumWidth(115);playback.addWidget(self.time_label)
        left.addLayout(playback)
        right_widget=QWidget();right=QVBoxLayout(right_widget);right.setSpacing(10);right.setContentsMargins(0,0,6,0)
        right_scroll=QScrollArea();right_scroll.setWidgetResizable(True);right_scroll.setWidget(right_widget)
        right_scroll.setMinimumWidth(350);right_scroll.setMaximumWidth(400);body.addWidget(right_scroll)
        right.addWidget(self.heading('Scenario & receiver health'))
        self.scenario_box=QComboBox();self.scenario_box.addItems(['Recorded GPS','Simulated timed outage','Simulated lateral jump'])
        self.scenario_box.currentIndexChanged.connect(self.select_scenario);right.addWidget(self.scenario_box)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName('status');right.addWidget(self.status)
        self.confidence_label=QLabel();self.confidence_label.setWordWrap(True);self.confidence_label.setObjectName('confidence');right.addWidget(self.confidence_label)
        self.policy_label=QLabel();self.policy_label.setWordWrap(True);self.policy_label.setObjectName('policy');right.addWidget(self.policy_label)
        details=QTabWidget();right.addWidget(details)
        controls=QWidget();control=QVBoxLayout(controls);control.setSpacing(10)
        controls_caption=QLabel('SIMULATED GNSS INPUT FAULTS');controls_caption.setObjectName('muted');control.addWidget(controls_caption)
        self.quality_label=QLabel();control.addWidget(self.quality_label)
        self.quality=QSlider(Qt.Horizontal);self.quality.setRange(0,100);self.quality.setValue(100);self.quality.setTracking(False)
        self.quality.valueChanged.connect(self.change_quality);control.addWidget(self.quality)
        self.outage=QCheckBox('Override: full GPS outage after initialization');self.outage.toggled.connect(self.change_outage);control.addWidget(self.outage)
        zones=QHBoxLayout()
        self.zone_radius=QSpinBox();self.zone_radius.setRange(2,30);self.zone_radius.setValue(6);self.zone_radius.setSuffix(' m zone');zones.addWidget(self.zone_radius)
        clear=QPushButton('Clear zones');clear.clicked.connect(self.clear_trees);zones.addWidget(clear);control.addLayout(zones)
        tip=QLabel('Click the orchard to add an obstruction zone. Trees are synthetic, not surveyed canopy.');tip.setWordWrap(True);tip.setObjectName('muted');control.addWidget(tip)
        settings=QPushButton('Fault timing / tolerance / policy…');settings.clicked.connect(self.settings);control.addWidget(settings)
        reset=QPushButton('Reset scenario');reset.clicked.connect(self.reset_scenario);control.addWidget(reset)
        self.real_toggle=QCheckBox('Use recorded CitrusFarm sensors');self.real_toggle.toggled.connect(self.change_mode);control.addWidget(self.real_toggle)
        control.addStretch();details.addTab(controls,'Controls')
        evaluation=QWidget();ev=QVBoxLayout(evaluation)
        self.metrics_label=QLabel();self.metrics_label.setWordWrap(True);self.metrics_label.setTextFormat(Qt.RichText);ev.addWidget(self.metrics_label);ev.addStretch();details.addTab(evaluation,'Evaluation')
        advisory=QWidget();adv=QVBoxLayout(advisory)
        self.advice=QLabel();self.advice.setWordWrap(True);adv.addWidget(self.advice);adv.addStretch();details.addTab(advisory,'Advisor')
        right.addStretch()
        self.integration=QLabel('Synthetic demonstration — no real dataset loaded');self.integration.setWordWrap(True);self.integration.setObjectName('muted');root.addWidget(self.integration)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.tick)
        self.poller=QTimer(self);self.poller.setInterval(100);self.poller.timeout.connect(self.poll_backend)
        self.advisor_poller=QTimer(self);self.advisor_poller.setInterval(200);self.advisor_poller.timeout.connect(self.poll_advisor);self.advisor_poller.start()
        self.update_scenario()

    def select_zip(self):
        path,_=QFileDialog.getOpenFileName(self,'Select Sequence 01 sensor ZIP',str(Path.home()/'Documents'),'ZIP archives (*.zip)')
        if path:self.load_zip(path)

    def load_zip(self,path):
        self.scenario['data_path']=path
        if self.real_toggle.isChecked():self.update_scenario()
        else:self.real_toggle.setChecked(True)

    def select_scenario(self,index):
        self.scenario['scenario_type']=('recorded','outage','jump')[index]
        self.scenario['outage_enabled']=False
        self.outage.blockSignals(True);self.outage.setChecked(False);self.outage.blockSignals(False)
        self.update_scenario()

    def settings(self):
        dialog=DemoSettings(self.scenario,self.policy_config,self)
        if dialog.exec()==QDialog.Accepted:
            self.scenario.update(dialog.values);self.policy_config=dialog.policy
            self.update_scenario()

    def heading(self,t):
        l=QLabel(t);l.setObjectName("heading");return l
    def add_tree(self,x,y):
        self.scenario["trees"].append({"x":round(x,2),"y":round(y,2),"radius_m":float(self.zone_radius.value()),"severity":0.7})
        self.update_scenario()
    def reset_scenario(self):
        path=self.scenario.get('data_path')
        self.scenario={'gps_quality':1.0,'outage_enabled':False,'trees':[],'random_seed':42,'scenario_type':'recorded'}
        if path:self.scenario['data_path']=path
        self.policy_config=PolicyConfig()
        for widget,value in ((self.quality,100),(self.scenario_box,0)):
            widget.blockSignals(True)
            if widget is self.quality:widget.setValue(value)
            else:widget.setCurrentIndex(value)
            widget.blockSignals(False)
        self.outage.blockSignals(True);self.outage.setChecked(False);self.outage.blockSignals(False)
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
            self.advisor_generation+=1
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
        failure=None
        try:
            result=future.result()
        except Exception as exc:
            failure=f"{type(exc).__name__}: {exc}"
        if not self.use_backend:
            self.poller.stop()
            return
        if self.requested_scenario is not None:
            scenario=self.requested_scenario;self.requested_scenario=None
            self.start_backend(scenario)
            return
        if failure:
            self.backend_error=failure
            self.integration.setText('REAL DATA FAILED — '+failure+' · Previous display retained; choose Mock explicitly to change mode.')
            self.mode.setText('LOAD FAILED · PREVIOUS DISPLAY')
            self.play.setEnabled(False)
        else:
            self.backend_error=''
            self.apply_results(result)
            self.play.setEnabled(True)
        self.poller.stop()

    def start_backend(self,scenario):
        if self.pending is not None:
            self.requested_scenario=copy.deepcopy(scenario)
            self.integration.setText("Scenario queued; waiting for current calculation…")
            return
        self.play.setEnabled(False)
        self.integration.setText("Computing CitrusFarm localization in background… Previous replay remains displayed.")
        self.computing_scenario=copy.deepcopy(scenario)
        self.pending=self.executor.submit(self.compute_backend,copy.deepcopy(scenario))
        self.poller.start()

    def apply_results(self,result):
        self.advisor_generation+=1
        self.play.setEnabled(True)
        self.results=apply_policy(result,self.policy_config) if result['metadata']['source']=='citrusfarm' else result
        self.applied_scenario=copy.deepcopy(result['metadata'].get('scenario',self.scenario))
        self.farm.real=self.traj.real=result['metadata']['source']=='citrusfarm'
        self.scene.setText('Original annotated Sequence 01 figure; white route is baked in. Approximate route registration, not surveyed canopy. Ellipse: 95% Gaussian model region.' if self.farm.real else 'Synthetic orchard; click to place virtual canopy zones.')
        self.index=min(self.index,len(result["frames"])-1)
        self.timeline.blockSignals(True)
        self.timeline.setRange(0,len(result["frames"])-1)
        self.timeline.setValue(self.index)
        self.timeline.blockSignals(False)
        source=result.get("metadata",{}).get("source","unknown")
        real=source=="citrusfarm"
        self.mode.setText("RECORDED DATA · SEQ 01" if real else "MOCK DATA — SYNTHETIC TRAJECTORY")
        self.mode.setProperty('real',real);self.mode.style().unpolish(self.mode);self.mode.style().polish(self.mode)
        self.integration.setText("Real recorded data; faults are synthetic." if real else
            ("Backend unavailable: "+self.backend_error+" — displaying mock data." if self.backend_error else
             "Synthetic demonstration — not measured CitrusFarm performance."))
        self.draw()

    def update_scenario(self):
        self.playing=False;self.timer.stop();self.play.setText('Play')
        self.advisor_generation+=1
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
        frames=self.results["frames"];self.farm.set_data(frames,self.index,self.applied_scenario.get("trees",[]))
        self.traj.set_data(frames,self.index,[])
        self.error.set_data(frames,self.index)
        self.timeline.blockSignals(True);self.timeline.setValue(self.index);self.timeline.blockSignals(False)
        f=frames[self.index];m=self.results["metrics"]
        real=self.results['metadata']['source']=='citrusfarm'
        for key,value in [('error',f"{f['position_error']:.2f} m"),('rmse',f"{m['rmse_m']:.2f} m"),('std',f"{f['position_std_m']:.2f} m"),('sat',str(f['satellites']) if f.get('satellites') is not None else 'Unavailable')]:
            self.kpis[key].setText(value if real else '—  mock')
        self.error.fault_interval=self.results['metadata'].get('fault_interval_s',[0,0])
        self.time_label.setText(f"{f['time']:.1f} s / {frames[-1]['time']:.1f} s")
        if self.results['metadata']['source']=='mock':
            self.status.setText(f"MOCK DATA · GPS {f['gps_status']} · illustrative error {f['position_error']:.2f} m")
            self.confidence_label.setText('Model confidence unavailable in mock mode')
            self.policy_label.setText('Demo policy unavailable in mock mode')
            self.metrics_label.setText('Illustrative trajectory; not measured CitrusFarm results')
            self.advice.setText('Local summary · Select a sensor ZIP for measured replay.')
            return
        receiver=f['receiver']
        diagnostics=(f"{f['satellites']} satellites · {receiver['fix_mode']} · RTK fixed flag {receiver['rtk_mode_fix']} · "
                     f"system / IO / NAP flags {receiver['system_error']}/{receiver['io_error']}/{receiver['swift_nap_error']} · age {receiver['age_s']:.1f}s"
                     if receiver['available'] else f"Receiver diagnostics unavailable ({receiver['reason']})")
        fault=self.results['metadata']['fault_interval_s']
        label=self.results['metadata']['scenario_label']
        self.status.setText(f"{label} · {'FAULT ACTIVE' if f['fault_active'] else 'fault inactive'} · interval {fault[0]:.1f}–{fault[1]:.1f}s\n"
                            f"GPS {f['gps_decision'].upper()}: {f['gps_reason']}\n"
                            f"Last accepted fix {f['accepted_fix_age_s']:.1f}s ago\n{diagnostics}\n"
                            f"Current error against post-processed RTK reference: {f['position_error']:.2f} m")
        conf=f.get('confidence_pct')
        self.confidence_label.setText(f"Model estimate: {conf:.1f}% within {f['tolerance_m']:.1f} m" if conf is not None else 'Model estimate: invalid or uninitialized')
        policy=f['policy']
        if self.policy_label.property('level')!=policy['state']:
            self.policy_label.setProperty('level',policy['state']);self.policy_label.style().unpolish(self.policy_label);self.policy_label.style().polish(self.policy_label)
        self.policy_label.setText(f"{policy['state'].upper()} · {policy['speed_scale']:.0%} nominal speed\n{policy['reason']}"+
                                  ('\nAuto-stop triggered · replay continues' if policy['state']=='Stop' else '')+'\nDemo only · no physical actuation')
        rows=['<b>Whole-replay error against RTK reference</b><br>GPS and post-processed reference share an RTK source.<br><br>']
        names={'gated':'Gated EKF','ungated':'Ungated fusion','wheel_imu':'Wheel + IMU','wheel_only':'Wheel odometry'}
        for name,metrics in m['comparisons'].items():
            within=metrics['fault_within_tolerance_s']
            within='N/A' if within is None else f"{within:.1f} / {metrics['fault_duration_s']:.1f} s"
            recovery=metrics['recovery_status'] if metrics['recovery_s'] is None else f"{metrics['recovery_s']:.1f} s"
            rows.append(f"<b>{names.get(name,name)}</b><br>RMSE {metrics['rmse_m']:.2f} m · Peak {metrics['peak_error_m']:.2f} m<br>Within tolerance during fault: {within}<br>Recovery: {recovery}<br><br>")
        rows.append('Recovery includes the sustained dwell period. Initialization uses GPS position and the first 3 m course, before faults start.')
        self.metrics_label.setText(''.join(rows))
        self.update_advisor(f)

    def update_advisor(self,frame):
        values=dashboard_values(frame)
        signature=(self.advisor_generation,state_key(values))
        if signature!=self.advisor_signature:
            self.advisor_signature=signature
            self.advice.setText('Local summary · '+local_summary(values))
            self.advisor_requested=(signature,values,frame['time'])
        if not os.environ.get('GEMINI_API_KEY'):
            return
        if self.advisor_pending is None and getattr(self,'advisor_requested',None) and time.monotonic()-self.advisor_last_request>=2:
            request=self.advisor_requested;self.advisor_requested=None
            self.advisor_pending=(request,self.advisor_executor.submit(explain,request[1]))
            self.advisor_last_request=time.monotonic()

    def poll_advisor(self):
        if self.advisor_pending is not None:
            request,future=self.advisor_pending
            if future.done():
                self.advisor_pending=None
                response=future.result()
                if request[0]==self.advisor_signature and self.results['metadata']['source']=='citrusfarm':
                    self.advice.setText(f"{response['source']} · snapshot t={request[2]:.1f}s\n{response['text']}")
        if self.results.get('metadata',{}).get('source')=='citrusfarm':
            self.update_advisor(self.results['frames'][self.index])

    def toggle_play(self):
        self.playing=not self.playing
        self.play.setText("Pause" if self.playing else "Play")
        if self.playing:self.timer.start()
        else:self.timer.stop()
    def restart(self):
        self.advisor_generation+=1;self.index=0;self.draw()
    def tick(self):
        self.index=min(len(self.results["frames"])-1,self.index+self.speed.value())
        self.draw()
        if self.index==len(self.results["frames"])-1:self.playing=False;self.timer.stop();self.play.setText("Play")

    def closeEvent(self,event):
        self.timer.stop();self.poller.stop();self.advisor_poller.stop()
        self.advisor_executor.shutdown(wait=False,cancel_futures=True)
        self.executor.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)

def create_application():
    app=QApplication(sys.argv)
    from frontend.theme import STYLE
    app.setStyleSheet(STYLE)
    return app

def main():
    app=create_application()
    window=OrchardGuard();window.show()
    if '--data' in sys.argv:
        window.load_zip(sys.argv[sys.argv.index('--data')+1])
    return app.exec()

if __name__=="__main__":
    sys.exit(main())
