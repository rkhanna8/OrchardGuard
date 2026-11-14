# Shared API contract v1 — freeze before parallel coding

The desktop frontend must run independently on synthetic mock data. The localization backend exposes:

```python
from backend.run import run_localization
result = run_localization(scenario)
```

No HTTP server, ROS2 topics, or web UI is required. Results are plain serializable Python dicts / JSON.

## Scenario (input)
```json
{
  "gps_quality": 0.8,
  "outage_enabled": false,
  "trees": [
    {"x": 12.0, "y": 8.0, "radius_m": 5.0, "severity": 0.7}
  ],
  "random_seed": 42
}
```
- `gps_quality` is simulated quality in [0, 1], **not literally a calibrated satellite count**. A UI can display a satellite-count analogy if explicitly marked approximate.
- Tree center/radius are in reference ENU meters; severity in [0,1]. User placements simulate canopy degradation when reference robot enters the zone. Reference is *never a filter measurement*.
- `outage_enabled`: if true, no valid GPS corrections; backend determines changes to observations.
- Identical inputs and seed must produce identical outputs.

## Result (output)
```json
{
  "metadata": {
    "source": "mock",
    "sequence": "synthetic-demo",
    "coordinate_frame": "local_enu",
    "units": "meters",
    "scenario_label": "Illustrative demonstration"
  },
  "frames": [
    {
      "time": 0.0,
      "ground_truth": {"x": 0.0, "y": 0.0, "yaw": 0.0},
      "estimated": {"x": 0.1, "y": -0.1, "yaw": 0.02},
      "baseline": {"x": 0.0, "y": 0.0},
      "position_error": 0.141421,
      "baseline_error": 0.0,
      "position_std_m": 0.3,
      "gps_status": "nominal",
      "gps_accepted": true,
      "satellites": 12
    }
  ],
  "metrics": {
    "rmse_m": 0.141421,
    "baseline_rmse_m": 0.0,
    "max_error_m": 0.141421
  }
}
```

Frames sorted by increasing `time`, seconds from sequence start. Coordinates in meters, yaw radians. `gps_status` one of `nominal`, `degraded`, `outage`. `position_std_m` is an interpretable uncertainty summary derived from covariance for real mode; not guaranteed frequentist confidence coverage. Error fields must satisfy Euclidean distance to the common reference per frame. `metadata.source` MUST be `mock` or `citrusfarm`. UI clearly marks mock. Additional fields allowed, but existing keys must remain.

## Integration policy
Frontend uses `frontend.mock_data.generate_mock_results(scenario)` today. When real backend is ready, frontend imports `backend.run.run_localization`; catch `NotImplementedError` and display **MOCK DATA** prominently. Never silently relabel mock as real. The two graphs and robot scene use frame positions from the same result, synchronized by time index. UI must not invent a second localization model.

## Ownership
Shared schema changes need approval from both people. Keep `sample_scenario.json` and `sample_results.json` in sync if changed.
