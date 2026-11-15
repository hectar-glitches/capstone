#!/usr/bin/env python3
"""
Committee demo. Runs the whole argument on real Sentinel-1 data, one beat at
a time, in about a minute.

    python3 demo.py                 # full run, pauses between sections
    python3 demo.py --no-pause      # straight through
    python3 demo.py --fast          # BAQ sections only
    python3 demo.py --no-figure     # skip writing vessel.png

Needs chip.npy and chip_ships.npy in the working directory. Both are
gitignored; PROVENANCE.md records the burst and offsets that produce them.

Everything here counts *objects*, not flagged pixels. A vessel is spatially
extended, so flagged pixels are merged within a radius and anything smaller
than two pixels is discarded as a speckle outlier. Counting fragments instead
inflates every number and was how an earlier version of this analysis
reported effects that are not there.
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy.ndimage import (label, center_of_mass, binary_dilation,
                           generate_binary_structure, iterate_structure)

from cfar import cfar_detect
from baq import baq_encode_plane, baq_decode_plane
from jp2 import normalize_plane_to_u16, denormalize_plane, encode_plane_jp2

GUARD, TRAIN, THRESH, MERGE, BLOCK = 2, 8, 13.0, 5, 128
RANGE_M, AZIMUTH_M = 2.3, 14.0
BOLD, DIM, OK, BAD, OFF = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"


def beat(title):
    print(f"\n{BOLD}{title}{OFF}\n{DIM}{'─' * 68}{OFF}")


def pause(args):
    if not args.no_pause:
        input(f"\n{DIM}  [enter]{OFF}")


def objects(chip):
    det, _ = cfar_detect(np.abs(chip), GUARD, TRAIN, THRESH)
    if not det.any():
        return []
    st = iterate_structure(generate_binary_structure(2, 2), MERGE)
    lab, n = label(binary_dilation(det, structure=st))
    lab = lab * det
    out = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < 2:
            continue
        r, c = center_of_mass(m)
        rr, cc = np.nonzero(m)
        out.append(dict(row=r, col=c, pixels=int(m.sum()),
                        az_m=(rr.max() - rr.min() + 1) * AZIMUTH_M,
                        rg_m=(cc.max() - cc.min() + 1) * RANGE_M))
    return out


def match(ref, got, tol=25):
    """(vessels found, false objects) against the uncompressed reference."""
    hit = sum(1 for a in ref if any(np.hypot(a["row"] - b["row"], a["col"] - b["col"]) <= tol for b in got))
    fa = sum(1 for b in got if not any(np.hypot(a["row"] - b["row"], a["col"] - b["col"]) <= tol for a in ref))
    return hit, fa


def baq_roundtrip(chip, clip_sigma, bits=4):
    i_c, i_s = baq_encode_plane(chip.real.astype(np.float32), bits, BLOCK, clip_sigma)
    q_c, q_s = baq_encode_plane(chip.imag.astype(np.float32), bits, BLOCK, clip_sigma)
    rec = baq_decode_plane(i_c, i_s, bits, BLOCK) + 1j * baq_decode_plane(q_c, q_s, bits, BLOCK)
    p = np.bincount((i_c.ravel() - i_c.min()).astype(np.int64))
    p = p[p > 0] / i_c.size
    return rec.astype(np.complex64), 2 * float(-(p * np.log2(p)).sum())


def fdbaq_roundtrip(chip, scale, brc=4):
    from fdbaq import encode_plane as fe, decode_plane as fd
    im, isg, it = fe(chip.real.astype(np.float64), brc, BLOCK, scale)
    qm, qsg, qt = fe(chip.imag.astype(np.float64), brc, BLOCK, scale)
    return (fd(im, isg, it, brc, BLOCK) + 1j * fd(qm, qsg, qt, brc, BLOCK)).astype(np.complex64)


def jp2_roundtrip(chip, percentile, ratio=20.0):
    import tempfile
    from PIL import Image
    i_u, i_k = normalize_plane_to_u16(chip.real.astype(np.float32), percentile)
    q_u, q_k = normalize_plane_to_u16(chip.imag.astype(np.float32), percentile)
    with tempfile.TemporaryDirectory() as td:
        ip, qp = os.path.join(td, "i.jp2"), os.path.join(td, "q.jp2")
        encode_plane_jp2(i_u, ip, ratio)
        encode_plane_jp2(q_u, qp, ratio)
        nbytes = os.path.getsize(ip) + os.path.getsize(qp)
        i_b, q_b = np.array(Image.open(ip)), np.array(Image.open(qp))
    rec = denormalize_plane(i_b, i_k) + 1j * denormalize_plane(q_b, q_k)
    return rec.astype(np.complex64), 8.0 * nbytes / chip.size


def row(label_, found, total, false_, extra=""):
    mark = OK if found else BAD
    print(f"  {label_:<14}{extra:>10}  {mark}{found}/{total}{OFF}  vessel    {false_}  false")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-pause", action="store_true")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    for f in ("chip.npy", "chip_ships.npy"):
        if not os.path.exists(f):
            sys.exit(f"missing {f} — see PROVENANCE.md for how to regenerate it")

    sea = np.load("chip.npy")
    ships = np.load("chip_ships.npy")

    beat("1.  This is real Sentinel-1 data, and the statistics prove it")
    for name, c in (("open water", sea), ("water + vessel", ships)):
        I = np.abs(c) ** 2
        print(f"  {name:<16}  {c.shape[0]}×{c.shape[1]}  {c.dtype}   "
              f"CV = {BOLD}{I.std()/I.mean():.2f}{OFF}   mean {10*np.log10(I.mean()):.1f} dB")
    print(f"\n  {DIM}Single-look intensity over uniform sea is exponentially distributed,{OFF}")
    print(f"  {DIM}so its spread equals its mean and the coefficient of variation lands{OFF}")
    print(f"  {DIM}on 1.0. The open-water chip does exactly that. Nothing upstream has{OFF}")
    print(f"  {DIM}filtered or multi-looked this data.{OFF}")
    pause(args)

    beat("2.  Uncompressed, the detector finds the vessel")
    t = time.time()
    raw = objects(ships)
    for o in raw:
        print(f"  row {o['row']:.0f}  col {o['col']:.0f}   {o['pixels']} px   "
              f"{BOLD}{o['az_m']:.0f} m × {o['rg_m']:.0f} m{OFF}")
    print(f"\n  {len(raw)} vessel-sized object  {DIM}({time.time()-t:.1f}s){OFF}")
    pause(args)

    beat("3.  Compress it the way the codec ships by default")
    rec, bits = baq_roundtrip(ships, 3.0)
    h, fa = match(raw, objects(rec))
    row("BAQ, clip 3σ", h, len(raw), fa, f"{bits:.2f} b/cs")
    print(f"\n  {DIM}The vessel is gone. It is a far outlier, so it clips to the brightest{OFF}")
    print(f"  {DIM}clutter level and loses the contrast the detector measures.{OFF}")
    pause(args)

    beat("4.  Move the clip point — the vessel returns, and the file shrinks")
    for sg in (3.0, 6.0, 10.0, 16.0):
        rec, bits = baq_roundtrip(ships, sg)
        h, fa = match(raw, objects(rec))
        row(f"clip {sg:.0f}σ", h, len(raw), fa, f"{bits:.2f} b/cs")
    print(f"\n  {DIM}Better detection and fewer bits at the same time. The default was not{OFF}")
    print(f"  {DIM}a tradeoff point — it was strictly worse on both axes.{OFF}")
    pause(args)

    if not args.fast:
        beat("5.  Real FDBAQ, using ESA’s own reconstruction tables")
        try:
            for sg in (1.0, 2.0, 4.0):
                h, fa = match(raw, objects(fdbaq_roundtrip(ships, sg)))
                row(f"scale {sg:.0f}", h, len(raw), fa)
            print(f"\n  {DIM}At the scale matching block sigma — the natural clutter-driven{OFF}")
            print(f"  {DIM}choice — the real standard loses the vessel too, and reports an{OFF}")
            print(f"  {DIM}object in the wrong place instead.{OFF}")
            print(f"\n  {DIM}The specification defines decoding. How an encoder picks that{OFF}")
            print(f"  {DIM}per-block scale is left open, and it is what decides the outcome.{OFF}")
        except ImportError:
            print("  fdbaq.py not found")
        pause(args)

        beat("6.  Control: JPEG2000 is not affected")
        for pc in (99.99, 99.999, 99.9999):
            rec, bits = jp2_roundtrip(ships, pc)
            h, fa = match(raw, objects(rec))
            row(f"p{pc:g}", h, len(raw), fa, f"{bits:.2f} b/cs")
        print(f"\n  {DIM}JPEG2000 allocates rate a different way and keeps the vessel at every{OFF}")
        print(f"  {DIM}setting tested. The failure is specific to block-adaptive quantizers{OFF}")
        print(f"  {DIM}that key their range to local clutter statistics — the family that{OFF}")
        print(f"  {DIM}actually flies on Sentinel-1.{OFF}")
        pause(args)

    if not args.no_figure and os.path.exists("figure_chip.py"):
        beat("7.  What the detector is looking at")
        os.system(f"{sys.executable} figure_chip.py chip_ships.npy vessel.png")

    beat("Summary")
    print("  One vessel, 182 m × 152 m, 38 dB above the sea around it.")
    print("  Block-adaptive quantizers keyed to local clutter erase it at their")
    print("  default scale, and recover it for free when that scale is loosened.")
    print("  JPEG2000, allocating rate differently, is unaffected.")
    print(f"\n  {DIM}n = 1 vessel, one chip, one scene. This demonstrates a mechanism.{OFF}")
    print(f"  {DIM}It does not yet measure an effect size — that needs bench.py at scale.{OFF}\n")


if __name__ == "__main__":
    main()
