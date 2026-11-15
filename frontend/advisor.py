"""Offline operator summary. No API calls or credentials are used."""
import math


def dashboard_values(frame):
    return {k:frame.get(k) for k in ('gps_decision','gps_reason','trusted_fix_age_s','accepted_fix_age_s',
             'position_std_m','confidence_pct','tolerance_m','receiver','policy','fault_active','position_error','candidate_health')}


def state_key(values):
    return (values.get('gps_decision'),values.get('gps_reason'),(values.get('policy') or {}).get('state'),values.get('fault_active'))


def local_summary(values):
    policy=values.get('policy') or {'state':'Unavailable','reason':'No localization result'}
    decision=values.get('gps_decision')
    if decision=='unavailable':condition='GPS is unavailable. Position continues from wheel speed and IMU turning rate.'
    elif values.get('candidate_health')=='degraded':condition='GPS is weak or simulated as degraded. The filter combines wheel and IMU prediction with cautious GPS corrections.'
    elif decision=='rejected':condition='The latest GPS position disagrees with the prediction and was not used. Position continues from wheel speed and IMU turning rate.'
    elif 'recovery' in policy.get('reason','').lower():condition='GPS corrections have resumed. The controller is waiting for sustained recovery.'
    else:condition='GPS corrections are available. Wheel speed and IMU turning rate continue predicting between fixes.'
    error=values.get('position_error')
    measured='Reference unavailable at this moment.' if error is None else f'Measured replay error against RTK reference: {error:.2f} m.'
    return f"{condition} Recommended action: {policy['state']}. {policy['reason']}. {measured}"


def explain(values,opener=None):
    return {'text':local_summary(values),'source':'Offline summary'}
