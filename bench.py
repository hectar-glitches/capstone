#!/usr/bin/env python3
"""
Batch benchmark harness.

Walks tile positions across a Sentinel-1 burst, and for every tile runs the
full comparison: raw CFAR detections as the reference, then every
representation at every parameter setting scored against it. Writes one CSV
row per (tile, method, parameter) so the whole sweep pools across chips
instead of resting on a single one.

This is what takes n from 16 to the hundreds.

Usage:
    python3 bench.py <burst.tiff> results.csv
    python3 bench.py <burst.tiff> results.csv --size 1024 --row-offset 240

Columns written:
    scene, col, row, cv, mean_db, zero_frac, n_raw   -- the tile itself
    method, param                                     -- representation + setting
    bits_per_cs, file_bytes                           -- rate, two ways
    n_det, matched, missed, false_alarms              -- detection outcome

Filter in analysis, not here. Land tiles and empty-water tiles are both
recorded, with the statistics needed to separate them later: open water sits
near cv 1.0, land is bright and high-cv, and water with targets is dark with
high cv.
"""
import argparse
import csv
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Works with a flat repo (baq.py at root) or the reps/ + detector/ layout.
try:
    from baq import baq_encode_plane, baq_decode_plane
    from jp2 import normalize_plane_to_u16, denormalize_plane, encode_plane_jp2
    from fdbaq import encode_plane as fdbaq_encode, decode_plane as fdbaq_decode, entropy_bits_per_sample
    from cfar import cfar_detect, cluster_detections
except ImportError:
    from reps.baq import baq_encode_plane, baq_decode_plane
    from reps.jp2 import normalize_plane_to_u16, denormalize_plane, encode_plane_jp2
    from reps.fdbaq import encode_plane as fdbaq_encode, decode_plane as fdbaq_decode, entropy_bits_per_sample
    from detector.cfar import cfar_detect, cluster_detections

GUARD, TRAIN, THRESH_DB, TOL = 2, 8, 13.0, 5.0
BLOCK = 128

BAQ_SIGMAS = [3.0, 6.0, 10.0, 16.0]
FDBAQ_SCALES = [1.0, 2.0, 4.0, 8.0]
JP2_PERCENTILES = [99.99, 99.999, 99.9999]


def detect(complex_arr):
    d, _ = cfar_detect(np.abs(complex_arr), GUARD, TRAIN, THRESH_DB)
    return cluster_detections(d)


def match(reference, other, tol=TOL):
    """Returns (matched_reference, unmatched_other)."""
    matched = sum(1 for r in reference
                  if any(np.hypot(r[0] - o[0], r[1] - o[1]) <= tol for o in other))
    unmatched = sum(1 for o in other
                    if not any(np.hypot(r[0] - o[0], r[1] - o[1]) <= tol for r in reference))
    return matched, unmatched


def code_entropy_bits(codes, n_levels):
    counts = np.bincount(np.asarray(codes).ravel().astype(np.int64) - int(np.min(codes)),
                         minlength=n_levels).astype(np.float64)
    counts = counts[counts > 0]
    p = counts / counts.sum()
    return float(-(p * np.log2(p)).sum())


def run_baq(chip, clip_sigma):
    i_c, i_s = baq_encode_plane(chip.real.astype(np.float32), 4, BLOCK, clip_sigma)
    q_c, q_s = baq_encode_plane(chip.imag.astype(np.float32), 4, BLOCK, clip_sigma)
    rec = (baq_decode_plane(i_c, i_s, 4, BLOCK) + 1j * baq_decode_plane(q_c, q_s, 4, BLOCK))
    bits = 2 * code_entropy_bits(i_c, 16)
    return rec.astype(np.complex64), bits, None


def run_fdbaq(chip, scale, brc=4):
    i_m, i_sg, i_t = fdbaq_encode(chip.real.astype(np.float64), brc, BLOCK, scale)
    q_m, q_sg, q_t = fdbaq_encode(chip.imag.astype(np.float64), brc, BLOCK, scale)
    rec = (fdbaq_decode(i_m, i_sg, i_t, brc, BLOCK) + 1j * fdbaq_decode(q_m, q_sg, q_t, brc, BLOCK))
    bits = 2 * entropy_bits_per_sample(i_m, brc)
    return rec.astype(np.complex64), bits, None


def run_jp2(chip, percentile, ratio=20.0):
    i_u16, i_clip = normalize_plane_to_u16(chip.real.astype(np.float32), percentile)
    q_u16, q_clip = normalize_plane_to_u16(chip.imag.astype(np.float32), percentile)
    with tempfile.TemporaryDirectory() as td:
        ip, qp = os.path.join(td, "i.jp2"), os.path.join(td, "q.jp2")
        encode_plane_jp2(i_u16, ip, ratio)
        encode_plane_jp2(q_u16, qp, ratio)
        nbytes = os.path.getsize(ip) + os.path.getsize(qp)
        from PIL import Image
        i_back = np.array(Image.open(ip))
        q_back = np.array(Image.open(qp))
    rec = (denormalize_plane(i_back, i_clip) + 1j * denormalize_plane(q_back, q_clip))
    bits = 8.0 * nbytes / chip.size
    return rec.astype(np.complex64), bits, nbytes


def methods():
    for s in BAQ_SIGMAS:
        yield "baq", s, lambda c, s=s: run_baq(c, s)
    for s in FDBAQ_SCALES:
        yield "fdbaq", s, lambda c, s=s: run_fdbaq(c, s)
    for p in JP2_PERCENTILES:
        yield "jp2", p, lambda c, p=p: run_jp2(c, p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("burst_tiff")
    ap.add_argument("out_csv")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--row-offset", type=int, default=240)
    ap.add_argument("--max-zero-frac", type=float, default=0.05,
                    help="skip tiles with more zero padding than this (default 0.05)")
    args = ap.parse_args()

    import rasterio
    from rasterio.windows import Window

    scene = os.path.basename(args.burst_tiff)
    size, row = args.size, args.row_offset
    rows_out = []

    with rasterio.open(args.burst_tiff) as src:
        print(f"{src.width} x {src.height}, dtype={src.dtypes[0]}")
        cols = list(range(0, src.width - size, size))
        for n, col in enumerate(cols, 1):
            chip = src.read(1, window=Window(col, row, size, size)).astype(np.complex64)
            I = np.abs(chip) ** 2
            if I.mean() == 0:
                continue
            zero_frac = float((I == 0).mean())
            if zero_frac > args.max_zero_frac:
                print(f"[{n}/{len(cols)}] col {col}: skipped, {zero_frac:.1%} padding")
                continue

            cv = float(I.std() / I.mean())
            mean_db = float(10 * np.log10(I.mean()))
            raw_det = detect(chip)
            print(f"[{n}/{len(cols)}] col {col}: cv={cv:.2f} mean={mean_db:.1f}dB raw={len(raw_det)}")

            base = dict(scene=scene, col=col, row=row, cv=round(cv, 3),
                        mean_db=round(mean_db, 2), zero_frac=round(zero_frac, 4),
                        n_raw=len(raw_det))

            for name, param, fn in methods():
                rec, bits, nbytes = fn(chip)
                det = detect(rec)
                matched, false_alarms = match(raw_det, det)
                rows_out.append({**base, "method": name, "param": param,
                                 "bits_per_cs": round(bits, 3),
                                 "file_bytes": nbytes if nbytes else "",
                                 "n_det": len(det), "matched": matched,
                                 "missed": len(raw_det) - matched,
                                 "false_alarms": false_alarms})

    if not rows_out:
        sys.exit("no usable tiles found")

    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    total_raw = sum(r["n_raw"] for r in rows_out if r["method"] == "baq" and r["param"] == BAQ_SIGMAS[0])
    print(f"\nwrote {args.out_csv}: {len(rows_out)} rows, {total_raw} raw detections pooled across tiles")


if __name__ == "__main__":
    main()
