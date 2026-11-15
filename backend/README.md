# CitrusFarm replay

Install NumPy with `python -m pip install numpy`. Put the extracted
`orchardguard-sensors.zip` in the checkout's `data/` directory, or set
`ORCHARDGUARD_DATA` to its path. Keep the ZIP local. Call
`backend.run.run_localization(scenario)` from the checkout.

The ZIP contains wheel.csv, imu.csv, gps.csv, and the original gt.csv for
sequence 01_13B_Jackal. Replay uses bag-recording times because the IMU
header clock has repeated timestamps. Reference north/west positions are
converted to east/north. Its orientation is derived from path displacement
for visualization. The EKF and baselines share an initial pose from the
first 3 m of GPS travel, before synthetic faults start. A stationary
segment provides the initial IMU yaw-rate bias. Ground-truth position is
used for scoring and for triggering synthetic canopy zones.

The adaptive EKF uses a 2-D innovation gate and wheel speed plus gyro yaw
rate for prediction. A forced outage disables GPS corrections throughout
the replay. Quality and canopy degradation inject seeded GPS noise,
outliers, and dropouts. Satellite numbers are illustrative. The reference
and recorded GPS share an RTK source, so nominal error is not an
independent absolute-accuracy measurement.
