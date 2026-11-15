"""Native demo parameter dialog."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QMessageBox
from frontend.policy import PolicyConfig


class DemoSettings(QDialog):
    def __init__(self, scenario, policy, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Replay and demo policy settings')
        layout = QFormLayout(self)
        self.fields = {}
        specs = [('fault_start_s', 'Simulated fault starts (s)', 30),
                 ('fault_end_s', 'Simulated fault ends (s)', 60), ('jump_m', 'Lateral jump (m)', 10),
                 ('tolerance_m', 'Evaluation tolerance (m)', 1), ('recovery_s', 'Evaluation sustained recovery (s)', 3),
                 ('slow_std_m', 'Slow: horizontal covariance summary (m)', policy.slow_std_m),
                 ('stop_std_m', 'Stop: horizontal covariance summary (m)', policy.stop_std_m),
                 ('slow_age_s', 'Slow: trusted-fix age (s)', policy.slow_age_s),
                 ('stop_age_s', 'Stop: trusted-fix age (s)', policy.stop_age_s),
                 ('policy_recovery_s', 'Policy recovery per step (s); independent of tolerance', policy.recovery_s)]
        for key, label, default in specs:
            box = QDoubleSpinBox(); box.setRange(.1, 10000); box.setDecimals(1)
            box.setValue(scenario.get(key, default)); self.fields[key] = box
            layout.addRow(label, box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)

    def accept(self):
        self.values = {k: v.value() for k, v in self.fields.items()}
        try:
            if self.values['fault_start_s'] >= self.values['fault_end_s']:
                raise ValueError('Fault start must precede fault end')
            self.policy = PolicyConfig(**{k: self.values[k] for k in ('slow_std_m', 'stop_std_m', 'slow_age_s', 'stop_age_s')},
                                       recovery_s=self.values['policy_recovery_s'])
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid settings', str(exc)); return
        super().accept()
