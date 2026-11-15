#!/usr/bin/env python3
"""
Render a SAR chip as a figure: the full chip with CFAR objects circled, plus a
zoom on the brightest object corrected to true ground geometry.

    python3 figure_chip.py chip_ships.npy vessel.png
    python3 figure_chip.py chip_ships.npy out.png --threshold-db 13 --merge 5

Needs matplotlib on top of what the pipeline already uses:
    pip install matplotlib

Two things this handles that a naive render gets wrong:

1. The stretch. Mapping percentiles across black-to-white spends almost the
   whole grey range on speckle, because with a million pixels even the 99.5th
   percentile is still sea. Anchoring black at the scene median and white a
   fixed number of dB above it keeps speckle dark and lets targets read.

2. The aspect. Sentinel-1 IW pixels are about 2.3 m in range and 14 m in
   azimuth, so a square pixel grid stretches the scene roughly sixfold across
   track. A ship looks like a thin diagonal streak until you correct for it.
"""
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from scipy.ndimage import (label, center_of_mass, binary_dilation,
                           generate_binary_structure, iterate_structure)

from cfar import cfar_detect

RANGE_M, AZIMUTH_M = 2.3, 14.0          # Sentinel-1 IW SLC pixel spacing
INK, MUTED, MARK = "#141413", "#6b6b68", "#1B8C99"


def cluster(det, merge, min_pixels=2):
    """One centroid per object, merging flagged pixels within `merge` pixels.
    Objects smaller than `min_pixels` are dropped as speckle outliers, which
    is the same rule demo.py applies, so the two agree on the count."""
    if not det.any():
        return []
    if merge > 0:
        st = iterate_structure(generate_binary_structure(2, 2), merge)
        lab, n = label(binary_dilation(det, structure=st))
        lab = lab * det
    else:
        lab, n = label(det)
    ids = [i for i in range(1, n + 1) if (lab == i).sum() >= min_pixels]
    return [] if not ids else [tuple(map(float, c)) for c in center_of_mass(det, lab, ids)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chip_npy")
    ap.add_argument("out_png")
    ap.add_argument("--guard", type=int, default=2)
    ap.add_argument("--train", type=int, default=8)
    ap.add_argument("--threshold-db", type=float, default=13.0)
    ap.add_argument("--merge", type=int, default=5, help="object merge radius in pixels")
    ap.add_argument("--span-db", type=float, default=32.0, help="dB above the median mapped to white")
    ap.add_argument("--ground-m", type=float, default=300.0, help="side length of the zoom panel, in metres")
    args = ap.parse_args()

    chip = np.load(args.chip_npy)
    db = 20 * np.log10(np.abs(chip) + 1e-6)
    med = float(np.median(db))
    norm = lambda a: np.clip((a - med) / args.span_db, 0, 1)

    det, _ = cfar_detect(np.abs(chip), args.guard, args.train, args.threshold_db)
    objs = cluster(det, args.merge)
    print(f"{len(objs)} object(s); sea median {med:.1f} dB")
    if not objs:
        raise SystemExit("nothing detected - lower --threshold-db or pick another chip")

    # brightest object, by the peak anywhere in its neighbourhood
    def peak_near(r, c, pad=20):
        r0, c0 = max(0, int(r) - pad), max(0, int(c) - pad)
        return float(db[r0:int(r) + pad, c0:int(c) + pad].max())
    objs.sort(key=lambda rc: -peak_near(*rc))
    R, C = objs[0]
    peak = peak_near(R, C)
    print(f"brightest: row {R:.0f} col {C:.0f}, peak {peak:.1f} dB, {peak - med:.1f} dB over sea")

    half_r = max(4, int(args.ground_m / 2 / AZIMUTH_M))
    half_c = max(8, int(args.ground_m / 2 / RANGE_M))
    r1, r2 = max(0, int(R) - half_r), min(db.shape[0], int(R) + half_r)
    c1, c2 = max(0, int(C) - half_c), min(db.shape[1], int(C) + half_c)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.5, 5.6),
                                   gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.1})

    axL.imshow(norm(db), cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    for r, c in objs:
        axL.add_patch(Circle((c, r), 45, fill=False, ec=MARK, lw=1.4))
    axL.add_patch(Rectangle((c1, r1), c2 - c1, r2 - r1, fill=False, ec=MARK, lw=1.6))
    axL.set_xticks([]); axL.set_yticks([])
    axL.set_title(f"{db.shape[1]} × {db.shape[0]} pixels, shown square\n"
                  f"{len(objs)} CFAR object(s) at {args.threshold_db:g} dB",
                  fontsize=10.5, color=INK, loc="left", pad=8)

    axR.imshow(norm(db[r1:r2, c1:c2]), cmap="gray", vmin=0, vmax=1,
               interpolation="nearest", aspect=AZIMUTH_M / RANGE_M)
    axR.set_xticks([]); axR.set_yticks([])
    axR.set_title(f"Brightest object, {args.ground_m:.0f} m × {args.ground_m:.0f} m of real ground\n"
                  f"peak {peak:.0f} dB — {peak - med:.0f} dB above the sea around it",
                  fontsize=10.5, color=INK, loc="left", pad=8)

    for a in (axL, axR):
        for s in a.spines.values():
            s.set_edgecolor("#d5d5d2")

    fig.text(0.012, 0.02,
             f"Single-look complex, unfiltered. Black is the scene median, white is {args.span_db:g} dB above it. "
             f"Range {RANGE_M} m per pixel, azimuth {AZIMUTH_M} m — the right panel corrects for that, the left does not.",
             fontsize=8.8, color=MUTED)
    fig.savefig(args.out_png, dpi=175, bbox_inches="tight", facecolor="white")
    print(f"wrote {args.out_png}")


if __name__ == "__main__":
    main()
