"""Sequence 01 ZIP loader. All replay clocks are bag-recording seconds."""
import csv
import io
import math
import json
import re
from pathlib import Path
from functools import lru_cache
from zipfile import ZipFile
import numpy as np


@lru_cache(maxsize=2)
def load(path, modified_ns, size):
    with ZipFile(path) as archive:
        manifests=[n for n in archive.namelist() if n.rsplit('/',1)[-1]=='metadata.json']
        if len(manifests)>1:raise ValueError('Multiple recording metadata files')
        manifest=json.loads(archive.read(manifests[0])) if manifests else {}
        parents={str(Path(n).parent) for n in archive.namelist() if Path(n).name in ('wheel.csv','imu.csv','gps.csv','gt.csv')}
        if len(parents)!=1:raise ValueError('Mixed sensor folders in ZIP')
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
            raw=stream.read().decode('utf-8-sig')
            ref = np.loadtxt(io.StringIO(raw), delimiter=',', usecols=(0, 1, 2),ndmin=2)
        match=re.search(r"(?:file:.*?)([0-9]{2}_[A-Za-z0-9]+_Jackal)",raw)
        inferred=match.group(1) if match else None
        sequence=manifest.get('sequence') or inferred or 'unidentified-recording'
        if inferred and inferred!=sequence:raise ValueError('Sequence metadata conflicts with reference header')
        declared=manifest.get('sensor_sequences',{})
        if any(value!=sequence for value in declared.values()):raise ValueError('Mixed sequence metadata')
        diagnostic_members=[n for n in archive.namelist() if Path(n).name=='receiver_state.csv']
        if len(diagnostic_members)>1:raise ValueError('Multiple receiver diagnostic files')
        diagnostic_member=diagnostic_members[0] if diagnostic_members else None
    if not np.isfinite(wheel).all() or not np.isfinite(imu).all() or not np.isfinite(ref[:,0]).all():
        raise ValueError('Nonfinite controls or reference')
    if np.any(np.diff(ref[:, 0]) <= 0) or not 1e9 < ref[0, 0] < 2e9:
        raise ValueError('Reference timestamps must be increasing Unix seconds')
    if len(ref)<2:raise ValueError('Reference requires at least two timestamps')
    valid = (np.isfinite(gps[:, 1:3]).all(axis=1) & (gps[:, 3] >= 0) &
             (np.abs(gps[:,1])<=90) & (np.abs(gps[:,2])<=180))
    gps[~valid,3]=-1
    if np.sum(valid) < 2:
        raise ValueError('No global initialization: need at least two valid GPS fixes')
    origin = gps[np.flatnonzero(valid)[0], 1:3].copy()
    if 'origin_lla' in manifest:
        origin=np.asarray(manifest['origin_lla'][:2],dtype=float)
        if origin.shape!=(2,) or not np.isfinite(origin).all():raise ValueError('Invalid coordinate origin')
    lat = math.radians(origin[0])
    scale = 1 - .00669437999014 * math.sin(lat)**2
    latitudes = gps[:, 1].copy()
    gps[:, 1] = np.deg2rad(gps[:, 2] - origin[1]) * 6378137 * math.cos(lat) / math.sqrt(scale)
    gps[:, 2] = np.deg2rad(latitudes - origin[0]) * 6378137 * (1 - .00669437999014) / scale**1.5
    gps[:, 9] *= 1e-9  # Header acquisition seconds only for freshness checks.
    reference_frame=manifest.get('reference_frame','north_west')
    if reference_frame=='north_west':ref[:, 1], ref[:, 2] = -ref[:, 2].copy(), ref[:, 1].copy()
    elif reference_frame!='enu':raise ValueError('Unsupported reference frame')
    if 'time_bounds_unix_s' in manifest:
        lo,hi=manifest['time_bounds_unix_s']
        if any(a[0,0]<lo-.001 or a[-1,0]>hi+.001 for a in (wheel,imu,gps)):
            raise ValueError('Recording timestamps conflict with declared sequence bounds')
    overlap = [max(a[0, 0] for a in (wheel, imu, gps, ref)), min(a[-1, 0] for a in (wheel, imu, gps, ref))]
    if overlap[1] - overlap[0] < 5:
        raise ValueError('Sensor and reference streams do not overlap')
    mask = valid & (gps[:, 0] >= overlap[0]) & (gps[:, 0] <= overlap[1])
    reference_at_gps = sample_reference(ref,gps[mask,0])
    discrepancy = np.linalg.norm(gps[mask, 1:3] - reference_at_gps, axis=1)
    if not np.isfinite(discrepancy).any():raise ValueError('No usable reference overlap')
    # Legacy Sequence 01 registration/diagnostics must never leak to another ZIP.
    matched_seq01=(sequence=='01_13B_Jackal' and abs(gps[0,0]-1689715609.2088385)<.01
                   and np.linalg.norm(origin-np.array([33.96341370886354,-117.34673623283803]))<1e-7)
    if sequence=='01_13B_Jackal' and not matched_seq01:
        raise ValueError('Sequence 01 identity does not match its timestamp/origin fingerprint')
    fixture=manifest.get('source')=='fixture'
    audit = {'sequence':sequence, 'source':'mock' if fixture else 'citrusfarm',
             'recording_kind':'fixture' if fixture else 'recorded', 'map_registered':bool(matched_seq01),
             'origin_lla':origin.tolist(),'diagnostics_member':diagnostic_member,
             'bag_timestamp_units': 'Unix nanoseconds converted to seconds',
             'reference_timestamp_units': 'Unix seconds', 'overlap_unix_s': overlap,
             'sensor_frames': {'wheel': wf, 'imu': imf, 'gps': gf},
             'reference_transform': 'east=-ty, north=tx; shared first-GPS origin; no fitted estimator alignment',
             'gps_reference_median_m': float(np.nanmedian(discrepancy)),
             'gps_reference_max_m': float(np.nanmax(discrepancy)),
             'gyro_wheel_yaw_rate_correlation': (float(np.corrcoef(np.interp(wheel[:, 0], imu[:, 0], imu[:, 1]), wheel[:, 2])[0, 1]) if np.std(wheel[:,2])>1e-10 and np.std(imu[:,1])>1e-10 else None)}
    return wheel, imu, gps, ref, audit


def sample_reference(ref,times,max_gap=.5):
    """Interpolate evaluation only; absent samples and long gaps stay NaN."""
    times=np.asarray(times)
    right=np.searchsorted(ref[:,0],times,side='left');right=np.clip(right,0,len(ref)-1)
    left=np.maximum(0,right-1)
    result=np.column_stack([np.interp(times,ref[:,0],ref[:,j]) for j in (1,2)])
    exact=np.abs(ref[right,0]-times)<1e-6
    valid=(times>=ref[0,0]) & (times<=ref[-1,0]) & ((ref[right,0]-ref[left,0]<=max_gap)|exact)
    result[~valid]=np.nan
    return result


def recording_diagnostics(path,audit,override=None):
    from backend.diagnostics import load_diagnostics, parse_diagnostics
    if override:return load_diagnostics(override)
    member=audit.get('diagnostics_member')
    if member:
        with ZipFile(path) as archive:
            with archive.open(member) as stream:return parse_diagnostics(csv.DictReader(io.TextIOWrapper(stream)))
    if audit.get('map_registered'):
        return load_diagnostics(Path(__file__).resolve().parents[1]/'data/receiver_state.csv')
    return [],[]
