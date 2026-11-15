# Localization backend

`backend.run.run_localization(scenario)` loads the sensor ZIP selected by `data_path`, `ORCHARDGUARD_DATA`, or `data/orchardguard-sensors.zip` and returns the shared desktop contract.

The PR #1 midpoint prediction and Joseph-form EKF correction are retained. Gated and ungated fusion share wheel speed, IMU yaw rate, initialization, validity/freshness checks, and measurement covariance; the latter bypasses only the innovation gate. Wheel-only and wheel+IMU trajectories share the initial pose and receive no position corrections.

See the root [README](../README.md) for timestamps, coordinate conversion, scientific caveats, receiver extraction, evaluation definitions, scenarios, measured results, and launch instructions. `recording.py`, `diagnostics.py`, and `evaluation.py` separate loading, optional causal receiver context, and post-processed RTK evaluation. No reference is fused.
