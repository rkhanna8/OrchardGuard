"""Shared visual language for the native dashboard and dialogs."""
STYLE = '''
QWidget { background: #0c131c; color: #e6edf5; font-family: "Avenir Next", "Segoe UI", sans-serif; font-size: 12px; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #0c131c; }
QFrame#card { background: #131f2c; border: 1px solid #253446; border-radius: 10px; }
QFrame#card QLabel { background: transparent; }
QLabel#title { font-size: 24px; font-weight: 800; letter-spacing: 2px; color: #dffcf0; }
QLabel#heading { font-size: 13px; font-weight: 700; color: #d6e3ef; }
QLabel#muted { color: #8fa5ba; font-size: 11px; }
QLabel#value { font-size: 25px; font-weight: 700; color: #f5f9ff; }
QLabel#warning { background: #45371f; color: #f9d389; border-radius: 6px; padding: 7px 11px; font-weight: 700; }
QLabel#warning[real="true"] { background: #153e35; color: #8aefc8; }
QLabel#status { background: #131f2c; border: 1px solid #2b4054; border-radius: 8px; padding: 12px; line-height: 1.5; }
QLabel#confidence { font-size: 16px; font-weight: 700; color: #8ae5d5; padding: 8px 0; }
QLabel#policy { background: #17372e; color: #a5f1cb; border: 1px solid #2c6150; padding: 12px; border-radius: 8px; }
QLabel#policy[level="Slow"] { background: #403320; color: #ffcf80; border-color: #76613e; }
QLabel#policy[level="Stop"] { background: #442932; color: #ffb7c4; border-color: #7b4554; }
QPushButton { background: #1c2b3b; border: 1px solid #34495e; border-radius: 6px; padding: 8px 12px; font-weight: 600; }
QPushButton:hover { background: #2a4055; border-color: #5c7b98; }
QPushButton:pressed { background: #142332; }
QPushButton:disabled { color: #627184; border-color: #263440; }
QPushButton#primary { background: #58d6ac; color: #0b2921; border-color: #58d6ac; }
QPushButton#primary:hover { background: #8be7c6; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #192736; border: 1px solid #35495e; border-radius: 5px; padding: 7px; min-height: 18px; }
QComboBox QAbstractItemView { background: #192736; selection-background-color: #2d5364; }
QSlider::groove:horizontal { height: 5px; background: #283a4c; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #57cba9; border-radius: 2px; }
QSlider::handle:horizontal { background: #c7f7e6; width: 13px; margin: -5px 0; border-radius: 6px; }
QCheckBox { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #5b738a; border-radius: 3px; background: #162433; }
QCheckBox::indicator:checked { background: #5dd5af; border: 3px solid #2d6956; }
QTabWidget::pane { border: 1px solid #27394c; border-radius: 7px; background: #101c28; }
QTabBar::tab { background: #111d29; color: #93a8bd; padding: 8px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #93edcf; border-bottom: 2px solid #5dd5af; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #101b27; width: 7px; }
QScrollBar::handle:vertical { background: #385168; min-height: 30px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #e5f1fa; background: #24384b; border: 1px solid #4c6880; padding: 5px; }
'''
