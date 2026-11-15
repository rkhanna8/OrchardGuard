# GPS trust timer follow-up

Reproduced on Sequence 01, Recorded GPS, no zones, full-outage off, seed 42, default policy. Same-time frame: 132.4 s.

| Quality | Correction age before → after | Trusted age before → after | Policy before → after | Uncertainty / reference error (unchanged) |
|---|---|---|---|---|
| 60% | 0.012318 → 0.012318 s | 132.400 → 0.012318 s | Stop → Normal | 0.421634 / 0.185884 m |
| 62% | 0.012318 → 0.012318 s | 132.400 → 0.012318 s | Stop → Normal | 0.412769 / 0.318174 m |

The 62% reproduction matches the screenshot's rounded uncertainty/error. Before the fix, `healthy = local_quality == 1 and receiver_ok` prevented every moderate-quality correction from resetting `last_trusted`. `last_accepted` advanced normally. The Stop predicate was trusted age ≥8 s; uncertainty was below the 3 m Stop threshold. This was an overly restrictive trust classification, not a stale UI clock or a bad accepted-fix timestamp.

New `FixTrust` observes accepted innovations without modifying EKF states, covariance, correction acceptance or the existing recovery shadow. It requires ≥10 accepted fixes spanning ≥2 s in a rolling 3 s window; gaps between accepted samples ≤0.8 s; mean innovation magnitude ≤0.75 m; mean NIS ≤3; measurement covariance trace ≤2 m²; and no reported receiver fault. Rejections/unhealthy candidates reset evidence. Missing samples cannot refresh trust. Excessive noise or inconsistent innovations do not renew trust. The observer uses neither reference error nor slider percentage. Healthy guarded fixes retain the existing direct renewal rule. This is motion-consistency evidence, not protection against every slow GPS bias.

Both ages and the trust explanation now appear beside GPS state. Frames and opportunity logs include the two replay-relative timestamps. At 132.4 s both timestamps after the change are 132.387682 s. Policy frames log each immediate Stop predicate. Stop reasons use configured values, for example `No trusted GPS fix for 12.0 s (stop limit: 10 s)` in the configurable-threshold regression. Defaults remain Slow 1 m / 2 s, Stop 3 m / 8 s, 3 s sustained recovery per step, speeds 100% / 35% / 0%.

The model probability had already moved to **Diagnostics**; it was not removed. It is now labeled **Model-estimated chance of being within [tolerance] m**, computed from the displayed frame's 2-D covariance and tolerance. At the default 1 m tolerance: 99.6% at 60% quality and 99.7% at 62%. Near-one is displayed `>99.9%`, never rounded to 100%. Measured error remains separate. These two replay runs have 100% empirical within-1-m coverage in their degraded segments, versus mean model estimates about 99.3% / 99.5%; this single correlated-RTK replay does not calibrate the probability. Earlier outage coverage was far more conservative (69.94% empirical versus 5.57% model). It remains in Diagnostics, not promoted to the main view.

## Verification

- Full suite: **42 tests passed in 19.060 s**, with the real ZIP enabled.
- Focused regressions: sustained moderate fixes at 60% and 62%; unchanged exact EKF errors; unhealthy/high-noise/inconsistent samples; true outage to Stop; 10 m jump with zero accepted faulty fixes; sustained recovery; configured threshold explanations; probability rounding.
- One native desktop launch passed both quality settings at 132.4 s, separate age labels, Normal state and Diagnostics percentage. Screenshots were inspected. Restart, scrubbing back to the frame, and rapid 60→62 slider changes passed; superseded worker output did not replace the current scenario.
- Screenshots and before/after JSON/logs remain ignored under `data/trust-*`. No raw recordings were added to Git.

Reproduce:

```bash
ORCHARDGUARD_TEST_DATA="$HOME/Documents/orchardguard-sensors.zip" \
  /tmp/orchardguard-qt-test/bin/python -m unittest discover -s tests -v
/tmp/orchardguard-qt-test/bin/python tools/verify_trust_desktop.py \
  "$HOME/Documents/orchardguard-sensors.zip"
```

The earlier [verification report](verification.md) describes the pre-follow-up policy rule. Its localization metrics remain valid: this change only observes the existing estimator and adjusts policy trust/UI reporting.


## 38% follow-up

The supplied t14/t26 screenshots show different zone layouts (two zones versus
one). Exact click coordinates are not recoverable from them. A controlled test
used seed 42 and a 6 m, severity-0.7 zone centered at ENU (6,20); no-zone results
were checked separately. The original 2 m² per-fix covariance-trace cap excluded
all 38% corrections regardless of sustained evidence. It has been replaced by
window mean-noise variance ≤0.25 m² (sum of R traces / sample count²), retaining
the existing sample-count, duration, gap, innovation-mean and NIS conditions.
This uses known independent simulated noise, not reference error. Correlated or
slowly biased GPS remains a limitation; the percentage is not calibrated.

The initial trusted timestamp is a real valid GPS sample used for course
initialization, so its age legitimately equaled replay time until another fix
qualified. The UI and policy now derive age from `last_trusted_time_s`, without
falling back to playback time or a stale age field. Explicit null shows “No
trusted fix yet”; missing/future/non-finite timestamps hide the age card. The
bottom playback clock is unchanged.

| Controlled canopy run | Trusted age before → after | Policy before → after |
|---|---|---|
| t14 s | 14 → 3.000666 s | Stop → Slow (2 s Slow threshold) |
| t26 s | 26 → 0.007100 s | Stop → Slow (sustained recovery pending) |

Correction ages remain 0.004946 / 0.007100 s, and reference errors remain
0.565635 / 0.303344 m; the EKF is unchanged. The no-zone run has the same age
changes and reference errors 0.512907 / 0.316778 m. Thus this reproduces the
reported trust failure, but not the exact second screenshot's zone geometry.

Six focused tests passed in 7.338 s, covering 38% canopy, 60/62%, actual outage
with zero accepted fixes and Stop, recovery, 10 m jump rejection, timestamp
validation, policy thresholds and probability formatting. One native desktop
check passed t14→t26→t14 scrubbing (90.1%→96.3%→90.1% within 1 m), changing
tolerance to 0.5 m (44.3% at t14), invalid covariance, null trusted timestamp and
missing timestamp. The large percentage occupies the previous uncertainty card;
covariance magnitude remains in the side panel and measured error stays separate.
The full suite was not rerun for this focused patch.
