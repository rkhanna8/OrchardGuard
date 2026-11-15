# Orchard imagery

`seq01.png` is the original annotated Sequence 01 figure supplied by the user, from [CitrusFarm](https://ucr-robotics.github.io/Citrus-Farm-Dataset/sequence.html). It supplies route correspondences for the display registration; it is no longer the operator background.

`seq01-clean.png` is the user's generated clean image. Its framing and some details differ. Eight surviving row/tree landmarks register it to the original; three withheld landmarks have 1.72, 3.93 and 6.44 pixel residuals. Added/generated trees are not surveyed geometry. The application labels the clean view as illustrative.

`frontend/map_registration.py` contains both transformations and all control/check points. Image registration never changes estimator positions or metric errors. Only the matching Sequence 01 timestamp/origin fingerprint enables this image; other sequences open Metric view.
