"""Advisory text only. The deterministic policy owns all speed decisions."""
import json
import math
import os
import urllib.request
from urllib.parse import quote


def dashboard_values(frame):
    return {'gps_decision': frame.get('gps_decision', 'unavailable'),
            'gps_reason': frame.get('gps_reason', 'Mock data'),
            'accepted_fix_age_s': frame.get('accepted_fix_age_s'),
            'position_std_m': frame.get('position_std_m'),
            'confidence_pct': frame.get('confidence_pct'), 'tolerance_m': frame.get('tolerance_m'),
            'receiver': frame.get('receiver', {'available': False}),
            'policy': frame.get('policy', {'state': 'Unavailable', 'reason': 'Mock replay'}),
            'fault_active': frame.get('fault_active', False)}


def state_key(values):
    # Bucket uncertainty to avoid requesting on every 10 Hz position update.
    std = values.get('position_std_m')
    bucket = None if std is None or not math.isfinite(std) else int(std * 2)
    return (values['gps_decision'], values['gps_reason'], values['policy']['state'],
            values['fault_active'], values['receiver'].get('available', False), bucket)


def local_summary(values):
    uncertainty = values.get('position_std_m')
    uncertainty = 'unavailable' if uncertainty is None else f'{uncertainty:.2f} m horizontal covariance summary'
    return (f"GPS {values['gps_decision']}: {values['gps_reason']}. Model uncertainty: {uncertainty}. "
            f"Local policy: {values['policy']['state']} — {values['policy']['reason']}. "
            'Replay continues; no physical actuation.')


def explain(values, opener=urllib.request.urlopen):
    fallback = local_summary(values)
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        return {'text': fallback, 'source': 'Local summary · GEMINI_API_KEY absent'}
    model = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
    prompt = ('Explain these dashboard values in at most three brief sentences. GPS health, model uncertainty, '
              'and controller recommendation are separate. The local policy has already decided the speed; '
              'do not propose or change that decision. Mention synthetic faults when active. This is replay '
              'without actuation. Do not infer independent accuracy or invent sensor facts. Values: ' + json.dumps(values, allow_nan=False))
    request = urllib.request.Request(
        'https://generativelanguage.googleapis.com/v1beta/models/' + quote(model, safe='') + ':generateContent',
        data=json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                         'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 350}}).encode(),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    try:
        with opener(request, timeout=12) as response:
            data = json.load(response)
        parts = data['candidates'][0]['content']['parts']
        text = ' '.join(p['text'] for p in parts if 'text' in p and not p.get('thought')).strip()
        if not text:
            raise ValueError('empty response')
        return {'text': text[:2000], 'source': 'Gemini advisory · local policy owns speed'}
    except Exception:
        # Never echo exception URLs, headers, credentials or remote response bodies.
        return {'text': fallback, 'source': 'Local summary · Gemini unavailable'}
