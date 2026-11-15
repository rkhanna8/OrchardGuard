"""Display-only registration of the original Sequence 01 annotated figure.

Pixel/metric route-turn correspondences manually identified on original 3183x939
image. No transform is applied to estimators or evaluation. White route is baked
into the source. Registration is approximate aerial context, not a surveyed map.
"""
from pathlib import Path
import numpy as np

# Control turns distributed over the full reference, including the distinctive
# lower excursion near the right side. Metric points are reference ENU.
CONTROL = [((6.00, 39.93), (333, 316)), ((21.80, 7.31), (533, 717)),
           ((31.16, 47.50), (653, 221)), ((118.69, 46.55), (1732, 227)),
           ((202.75, -.205), (2745, 800)), ((218.92, 52.22), (2954, 153))]
CHECK = [((8.66, 7.65), (369, 713)), ((16.63, 40.25), (467, 311)),
         ((49.96, 7.48), (878, 714)), ((80.93, 46.55), (1260, 230)),
         ((158.21, 45.75), (2210, 239))]
MATRIX = np.linalg.lstsq(np.array([[x, y, 1] for (x, y), _ in CONTROL]),
                       np.array([p for _, p in CONTROL]), rcond=None)[0]
IMAGE = Path(__file__).parent / 'assets/seq01.png'


def pixel(x, y):
    return np.array([x, y, 1]) @ MATRIX


def validation():
    return [{'metric': xy, 'image': target, 'residual_px': float(np.linalg.norm(pixel(*xy) - target))}
            for xy, target in CHECK]
