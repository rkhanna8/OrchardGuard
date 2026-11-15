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
    return [{'metric': xy, 'image': target, 'residual_px': float(np.linalg.norm(np.array([*xy, 1]) @ ORIGINAL_MATRIX - target))}
            for xy, target in CHECK]

# The cleaned image changed framing and includes generated details. Register
# surviving tree-row landmarks to the original; never interpret added trees as
# surveyed geometry. Coordinates are (original px, cleaned px).
ORIGINAL_MATRIX=MATRIX.copy()
CLEAN_LANDMARKS=[((224,274),(153,186)),((620,194),(422,132)),
                 ((1248,194),(850,132)),((2048,194),(1390,132)),
                 ((2990,274),(2036,186)),((226,754),(153,516)),
                 ((1248,754),(850,516)),((2990,754),(2036,516))]
CLEAN_CHECK=[((700,354),(477,240)),((1562,594),(1067,405)),((2510,674),(1715,460))]
CLEAN_AFFINE=np.linalg.lstsq(np.array([[*p,1] for p,_ in CLEAN_LANDMARKS]),
                            np.array([q for _,q in CLEAN_LANDMARKS]),rcond=None)[0]
MATRIX=np.vstack((ORIGINAL_MATRIX.T,[0,0,1])).T @ CLEAN_AFFINE
IMAGE=Path(__file__).parent/'assets/seq01-clean.png'


def clean_validation():
    return [float(np.linalg.norm(np.array([*p,1])@CLEAN_AFFINE-q)) for p,q in CLEAN_CHECK]
