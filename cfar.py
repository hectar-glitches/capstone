#!/usr/bin/env python3
"""
Cell-Averaging CFAR (Constant False Alarm Rate) ship/dark-vessel detector,
built from scratch against sea-clutter statistics -- deliverable #2 of the
capstone (the from-scratch detector; a pretrained baseline like SNAP/
SSDD-HRSID is the proposal's documented week-one fallback, not what this
file implements).

How it works: for every pixel, estimate the local sea-clutter level from an
annulus of "training cells" around it (skipping a "guard" band right next to
the pixel so a bright target doesn't bias its own background estimate), then
flag the pixel as a detection if it exceeds that local background by more
than `threshold_db` decibels. This is the standard CA-CFAR formulation
(cell-averaging CFAR), the simplest member of the CFAR family and the usual
starting point before more adaptive variants (OS-CFAR, GOCA-CFAR, etc.).

Usage:
    python3 cfar.py scene_magnitude.npy --guard 2 --train 8 --threshold-db 13
"""
import argparse
import numpy as np
from scipy.ndimage import uniform_filter


def cfar_detect(magnitude: np.ndarray, guard: int = 2, train: int = 8, threshold_db: float = 13.0):
    """Cell-averaging CFAR over a real-valued magnitude (or intensity) image.

    guard: half-width of the guard band around the cell under test (CUT),
        in pixels. Cells this close to the CUT are excluded from the
        background estimate so a target's own energy doesn't leak into it.
    train: half-width of the training window beyond the guard band. The
        background level is the mean magnitude over the square annulus
        between `guard` and `guard+train` pixels from the CUT.
    threshold_db: how far above the local background (in dB) a pixel's
        magnitude must be to count as a detection.

    Returns (detections: bool array same shape as magnitude,
              background: float array, the estimated local clutter level).
    """
    outer = guard + train
    # Mean over the full (2*outer+1) box, and mean over the inner
    # (2*guard+1) box; subtracting the (area-weighted) inner mean from the
    # outer mean isolates the training annulus's average cheaply, without
    # looping pixel by pixel.
    outer_sum = uniform_filter(magnitude, size=2 * outer + 1, mode='reflect') * (2 * outer + 1) ** 2
    inner_sum = uniform_filter(magnitude, size=2 * guard + 1, mode='reflect') * (2 * guard + 1) ** 2
    train_cells = (2 * outer + 1) ** 2 - (2 * guard + 1) ** 2
    background = (outer_sum - inner_sum) / train_cells

    # Avoid log(0) in flat/zero regions.
    bg_safe = np.clip(background, 1e-6, None)
    mag_safe = np.clip(magnitude, 1e-6, None)
    excess_db = 20.0 * np.log10(mag_safe / bg_safe)

    detections = excess_db > threshold_db
    return detections, background


def cluster_detections(detections: np.ndarray, min_separation: int = 3):
    """Collapse a blob of adjacent detected pixels (one bright target usually
    lights up several neighboring pixels) into one point per connected blob,
    at that blob's centroid. Returns a list of (row, col) centroids."""
    from scipy.ndimage import label, center_of_mass

    labeled = np.empty(detections.shape, dtype=np.int32)
    n = label(detections, output=labeled)

    if n == 0:
        return []
    centroids = center_of_mass(detections, labeled, range(1, n + 1))
    return [(float(r), float(c)) for r, c in centroids]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_npy", help="path to a .npy file: either a complex scene or a real-valued magnitude/intensity array")
    ap.add_argument("--guard", type=int, default=2, help="guard-band half-width in pixels (default 2)")
    ap.add_argument("--train", type=int, default=8, help="training-window half-width beyond the guard band (default 8)")
    ap.add_argument("--threshold-db", type=float, default=13.0, help="detection threshold above local background, in dB (default 13)")
    args = ap.parse_args()

    data = np.load(args.input_npy)
    magnitude = np.abs(data) if np.iscomplexobj(data) else data.astype(np.float64)

    detections, background = cfar_detect(magnitude, args.guard, args.train, args.threshold_db)
    centroids = cluster_detections(detections)

    print(f"input: {magnitude.shape[0]}x{magnitude.shape[1]}, guard={args.guard}, train={args.train}, threshold={args.threshold_db} dB")
    print(f"flagged pixels: {int(detections.sum())}  ->  {len(centroids)} clustered detection(s)")
    for i, (r, c) in enumerate(centroids):
        snr_db = 20.0 * np.log10(magnitude[int(round(r)), int(round(c))] / max(background[int(round(r)), int(round(c))], 1e-6))
        print(f"  [{i}] row={r:.1f} col={c:.1f}  magnitude={magnitude[int(round(r)), int(round(c))]:.1f}  excess={snr_db:.1f} dB")


if __name__ == "__main__":
    main()