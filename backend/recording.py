"""Sequence 01 ZIP loader. All replay clocks are bag-recording seconds."""
import csv
import io
import math
from functools import lru_cache
from zipfile import ZipFile
import numpy as np


@lru_cache(maxsize=2)
def load(path, modified_ns, size):
    with ZipFile(path) as archive:
        def rows(name):
            matches = [n for n in archive.namelist() if n.rsplit('/', 1)[-1] == name + '.csv']
            if len(matches) != 1:
                raise ValueError(f'ZIP requires exactly one {name}.csv')
            return archive.open(matches[0])
        def read(name, fields):
            with rows(name) as stream:
                data = list(csv.DictReader(io.TextIOWrapper(stream)))
            a = np.array([[int(r['bag_time_ns']) * 1e-9, *(float(r[f]) for f in fields)] for r in data])
            if not len(a) or not np.isfinite(a[:, 0]).all() or np.any(np.diff(a[:, 0]) <= 0):
                raise ValueError(f'{name}: empty or non-increasing bag timestamps')
            if not 1e9 < a[0, 0] < 2e9:
                raise ValueError(f'{name}: expected Unix nanoseconds in bag_time_ns')
            return a, sorted({r.get('frame_id', '') for r in data})
        wheel, wf = read('wheel', ['speed_mps', 'yaw_rate_rad_s'])
        imu, imf = read('imu', ['gyro_z_rad_s'])
        # Preserve invalid fixes so decision/reason reporting remains faithful.
        gps, gf = read('gps', ['latitude_deg', 'longitude_deg', 'fix_status', 'cov_ee', 'cov_nn',
                              'cov_en', 'cov_ne', 'covariance_type', 'header_time_ns'])
        with rows('gt') as stream:
            ref = np.loadtxt(stream, delimiter=',', usecols=(0, 1, 2))
    if not np.isfinite(wheel).all() or not np.isfinite(imu).all() or not np.isfinite(ref).all():
        raise ValueError('Nonfinite controls or reference')
    if np.any(np.diff(ref[:, 0]) <= 0) or not 1e9 < ref[0, 0] < 2e9:
        raise ValueError('Reference timestamps must be increasing Unix seconds')
    valid = np.isfinite(gps[:, 1:3]).all(axis=1) & (gps[:, 3] >= 0)
    if np.sum(valid) < 2:
        raise ValueError('No global initialization: need at least two valid GPS fixes')
    origin = gps[np.flatnonzero(valid)[0], 1:3].copy()
    lat = math.radians(origin[0])
    scale = 1 - .00669437999014 * math.sin(lat)**2
    latitudes = gps[:, 1].copy()
    gps[:, 1] = np.deg2rad(gps[:, 2] - origin[1]) * 6378137 * math.cos(lat) / math.sqrt(scale)
    gps[:, 2] = np.deg2rad(latitudes - origin[0]) * 6378137 * (1 - .00669437999014) / scale**1.5
    gps[:, 9] *= 1e-9  # Header acquisition seconds only for freshness checks.
    ref[:, 1], ref[:, 2] = -ref[:, 2].copy(), ref[:, 1].copy()
    overlap = [max(a[0, 0] for a in (wheel, imu, gps, ref)), min(a[-1, 0] for a in (wheel, imu, gps, ref))]
    if overlap[1] <= overlap[0]:
        raise ValueError('Sensor and reference streams do not overlap')
    mask = valid & (gps[:, 0] >= overlap[0]) & (gps[:, 0] <= overlap[1])
    reference_at_gps = np.column_stack([np.interp(gps[mask, 0], ref[:, 0], ref[:, j]) for j in (1, 2)])
    discrepancy = np.linalg.norm(gps[mask, 1:3] - reference_at_gps, axis=1)
    audit = {'bag_timestamp_units': 'Unix nanoseconds converted to seconds',
             'reference_timestamp_units': 'Unix seconds', 'overlap_unix_s': overlap,
             'sensor_frames': {'wheel': wf, 'imu': imf, 'gps': gf},
             'reference_transform': 'east=-ty, north=tx; shared first-GPS origin; no fitted estimator alignment',
             'gps_reference_median_m': float(np.median(discrepancy)),
             'gps_reference_max_m': float(np.max(discrepancy)),
             'gyro_wheel_yaw_rate_correlation': float(np.corrcoef(np.interp(wheel[:, 0], imu[:, 0], imu[:, 1]), wheel[:, 2])[0, 1])}
    return wheel, imu, gps, ref, audit
