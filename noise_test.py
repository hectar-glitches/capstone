#!/usr/bin/env python3
"""
Does raising the noise floor by a known amount cost vessel detections?

This tests the contrast-loss model directly. The model says that when a
quantizer adds noise at a given signal-to-quantization-noise ratio, the
vessel-to-sea contrast that CFAR measures falls by

    loss_dB = 10 * log10(1 + 1/SQNR)

because the quantization noise lands on the background while the vessel's
own power is unchanged. Here we add noise at exactly that level, measure
what the contrast actually does, and count which vessels survive.

    python3 noise_test.py chip_ships.npy
    python3 noise_test.py scene.npy --labels vessels.csv --trials 50
    python3 noise_test.py chip_ships.npy --sqnr 28 13.4 9.8 3.2

WHAT THIS DOES AND DOES NOT MODEL

The noise added here is white and uniform, which is what the model assumes.
Real FDBAQ's error is neither: it is signal-dependent, and focusing
redistributes a bright target's own quantization error into the sea around
it, forming a halo that sits exactly where CFAR estimates its background.
So this experiment is the model's best case. Running real FDBAQ later and
differencing the two measurements is how the halo gets quantified.

Reference vessels come from the uncompressed run unless --labels is given.
"""
import argparse
import csv
import os
import sys

import numpy as np
from scipy.ndimage import (label, center_of_mass, binary_dilation,
                           generate_binary_structure, iterate_structure)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfar import cfar_detect

RANGE_M, AZIMUTH_M = 2.3, 14.0


# ---------------------------------------------------------------- detection

def objects(chip, guard, train, thresh_db, merge, min_px):
    """One entry per vessel-sized object. Carries its own clustering because
    cfar.py's cluster_detections ignores its min_separation argument."""
    det, _ = cfar_detect(np.abs(chip), guard, train, thresh_db)
    if not det.any():
        return []
    st = iterate_structure(generate_binary_structure(2, 2), merge)
    lab, n = label(binary_dilation(det, structure=st))
    lab = lab * det
    out = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < min_px:
            continue
        r, c = center_of_mass(m)
        rr, cc = np.nonzero(m)
        out.append(dict(row=float(r), col=float(c), pixels=int(m.sum()),
                        length_m=max((rr.max() - rr.min() + 1) * AZIMUTH_M,
                                     (cc.max() - cc.min() + 1) * RANGE_M)))
    return out


def match(ref, got, tol):
    hit = [any(np.hypot(a["row"] - b["row"], a["col"] - b["col"]) <= tol for b in got)
           for a in ref]
    false_ = sum(1 for b in got
                 if not any(np.hypot(a["row"] - b["row"], a["col"] - b["col"]) <= tol
                            for a in ref))
    return hit, false_


# ----------------------------------------------------------------- contrast

def contrast_db(chip, row, col, peak_rad=3, guard=2, train=8):
    """Vessel peak over local sea, in dB, measured the way CFAR sees it.

    The background comes from an annulus with the same geometry as the
    detector's training ring, so the number tracks what actually decides
    detection. Median, not mean, so one bright pixel cannot inflate it.

    `peak_rad` must be kept small. The maximum over a window of N noise
    samples sits roughly sqrt(ln N) standard deviations above the mean, so a
    wide window makes the measured peak rise with added noise and hides the
    very contrast loss being measured. For a dim target that bias is
    comparable to the signal itself. Use the smallest radius that still
    tolerates the label's positional error.
    """
    inten = np.abs(chip) ** 2
    r, c = int(round(row)), int(round(col))
    H, W = inten.shape

    r0, r1 = max(0, r - peak_rad), min(H, r + peak_rad + 1)
    c0, c1 = max(0, c - peak_rad), min(W, c + peak_rad + 1)
    if r1 <= r0 or c1 <= c0:
        return np.nan
    peak = inten[r0:r1, c0:c1].max()

    outer = guard + train
    R0, R1 = max(0, r - outer), min(H, r + outer + 1)
    C0, C1 = max(0, c - outer), min(W, c + outer + 1)
    box = inten[R0:R1, C0:C1]
    mask = np.ones(box.shape, bool)
    gr0, gr1 = max(0, r - guard - R0), min(box.shape[0], r + guard + 1 - R0)
    gc0, gc1 = max(0, c - guard - C0), min(box.shape[1], c + guard + 1 - C0)
    mask[gr0:gr1, gc0:gc1] = False
    ring = box[mask]
    if ring.size == 0 or peak <= 0:
        return np.nan
    sea = np.median(ring)
    if sea <= 0:
        return np.nan
    return float(10 * np.log10(peak / sea))


# -------------------------------------------------------------------- noise

def add_noise(chip, sqnr_db, sea_power, rng):
    """Add white complex noise so the quantizer's SQNR equals sqnr_db.

    SQNR is referenced to what the quantizer actually sees, which over ocean
    is the sea, so sea_power is the reference rather than the chip mean. A
    single bright vessel would otherwise drag the mean up and understate the
    noise. For complex noise E[|n|^2] = 2*sigma^2, hence the factor of two.
    """
    noise_power = sea_power / 10 ** (sqnr_db / 10)
    s = np.sqrt(noise_power / 2)
    n = rng.normal(0, s, chip.shape) + 1j * rng.normal(0, s, chip.shape)
    return (chip + n).astype(np.complex64)


predicted_loss_db = lambda sqnr_db: 10 * np.log10(1 + 10 ** (-sqnr_db / 10))


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chip", help=".npy of complex samples")
    ap.add_argument("--labels", help="SARFish SLC_validation.csv, or any CSV with "
                                     "row,col columns; default uses the uncompressed run")
    ap.add_argument("--product", help="product identifier, for a SARFish label file")
    ap.add_argument("--swath", default="IW3", help="subswath, for a SARFish label file")
    ap.add_argument("--chip-offset", type=int, nargs=2, metavar=("ROW", "COL"),
                    help="where this chip sits in the full swath, so SARFish label "
                         "coordinates can be translated into chip coordinates")
    ap.add_argument("--sqnr", type=float, nargs="+",
                    default=[28.0, 20.0, 16.0, 13.4, 9.8, 6.0, 3.2],
                    help="SQNR values in dB to test (default spans today's 13.4 "
                         "and the candidate change's 3.2)")
    ap.add_argument("--trials", type=int, default=20,
                    help="noise realisations per SQNR (default 20)")
    ap.add_argument("--guard", type=int, default=2)
    ap.add_argument("--train", type=int, default=8)
    ap.add_argument("--threshold-db", type=float, default=13.0)
    ap.add_argument("--merge", type=int, default=5)
    ap.add_argument("--min-pixels", type=int, default=2)
    ap.add_argument("--tol", type=float, default=25.0,
                    help="matching radius in pixels")
    ap.add_argument("--peak-radius", type=int, default=3,
                    help="half-width of the window the vessel peak is taken "
                         "from; keep small (default 3), see contrast_db")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="write per-vessel results to this CSV")
    args = ap.parse_args()

    chip = np.load(args.chip)
    if not np.iscomplexobj(chip):
        sys.exit("error: need complex samples")
    rng = np.random.default_rng(args.seed)

    # SQNR is a ratio of mean powers, but a plain mean would be dragged up by
    # the vessels. Single-look sea intensity is exponential, whose median is
    # ln(2) of its mean, so dividing the median by ln(2) estimates the mean
    # robustly.
    inten = np.abs(chip) ** 2
    sea_power = float(np.median(inten)) / np.log(2)
    print(f"{args.chip}   {chip.shape[0]} x {chip.shape[1]}   {chip.dtype}")
    print(f"sea power (mean, from the median) {sea_power:.1f}"
          f"   = {10*np.log10(sea_power):.1f} dB\n")

    # reference vessels
    if args.labels:
        ref = []
        with open(args.labels) as f:
            rd = csv.DictReader(f)
            sarfish = "detect_scene_row" in (rd.fieldnames or [])
            r0, c0 = args.chip_offset or (0, 0)
            sw = args.swath.upper().replace("IW", "")
            for d in rd:
                if sarfish:
                    # SARFish positions are in the full swath's pixel space, so
                    # subtract where this chip starts. Labels outside the chip
                    # are dropped. vessel_length_m is only filled where AIS
                    # supplied it, so most dark vessels have no length.
                    if args.product and d["SLC_product_identifier"] != args.product:
                        continue
                    if d["swath_index"] != sw:
                        continue
                    r = float(d["detect_scene_row"]) - r0
                    c = float(d["detect_scene_column"]) - c0
                    if not (0 <= r < chip.shape[0] and 0 <= c < chip.shape[1]):
                        continue
                    ref.append(dict(row=r, col=c,
                                    length_m=float(d["vessel_length_m"] or "nan"),
                                    source=d["source"], confidence=d["confidence"]))
                else:
                    ref.append(dict(row=float(d["row"]), col=float(d["col"]),
                                    length_m=float(d.get("length_m") or "nan")))
        dark = sum(1 for v in ref if v.get("source") == "manual")
        print(f"{len(ref)} labelled object(s) inside this chip"
              f"{f', {dark} with no AIS match' if dark else ''}")
    else:
        ref = objects(chip, args.guard, args.train, args.threshold_db,
                      args.merge, args.min_pixels)
        print(f"{len(ref)} reference vessel(s) from the uncompressed run")
    if not ref:
        sys.exit("no reference vessels")

    base = np.array([contrast_db(chip, v["row"], v["col"], args.peak_radius,
                                 args.guard, args.train) for v in ref])
    for v, b in zip(ref, base):
        L = v.get("length_m", float("nan"))
        print(f"   row {v['row']:7.0f}  col {v['col']:7.0f}  "
              f"length {'    -  ' if L != L else format(L, '6.0f') + ' m'}"
              f"   contrast {b:5.1f} dB   {v.get('source', '')}")

    print(f"\n{args.trials} noise realisations per level, "
          f"CFAR threshold {args.threshold_db:g} dB\n")
    print(f"{'SQNR':>7} {'predicted':>11} {'measured':>14} {'detected':>11} "
          f"{'false':>7}")
    print(f"{'(dB)':>7} {'loss (dB)':>11} {'loss (dB)':>14} {'':>11} {'':>7}")
    print("  " + "-" * 56)

    rows = []
    for sq in sorted(args.sqnr, reverse=True):
        losses, hits, falses = [], np.zeros(len(ref)), []
        for _ in range(args.trials):
            noisy = add_noise(chip, sq, sea_power, rng)
            cur = np.array([contrast_db(noisy, v["row"], v["col"],
                                        args.peak_radius, args.guard, args.train)
                            for v in ref])
            losses.append(base - cur)
            got = objects(noisy, args.guard, args.train, args.threshold_db,
                          args.merge, args.min_pixels)
            hit, fa = match(ref, got, args.tol)
            hits += np.array(hit, float)
            falses.append(fa)

        losses = np.array(losses)
        m, sd = np.nanmean(losses), np.nanstd(np.nanmean(losses, axis=1))
        rate = hits / args.trials
        print(f"{sq:>7.1f} {predicted_loss_db(sq):>11.2f} "
              f"{m:>9.2f} +/-{sd:<4.2f} {rate.mean():>10.0%} "
              f"{np.mean(falses):>7.2f}")

        for v, b, l, r in zip(ref, base, np.nanmean(losses, axis=0), rate):
            rows.append(dict(sqnr_db=sq, row=round(v["row"], 1), col=round(v["col"], 1),
                             length_m=v.get("length_m", float("nan")),
                             source=v.get("source", ""),
                             contrast_db=round(float(b), 2),
                             predicted_loss_db=round(float(predicted_loss_db(sq)), 3),
                             measured_loss_db=round(float(l), 3),
                             detection_rate=round(float(r), 3)))

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {args.out}  ({len(rows)} rows)")

    print("\nIf measured tracks predicted, uniform added noise explains the loss.")
    print("Real FDBAQ should do worse, and that gap is the halo.")


if __name__ == "__main__":
    main()
