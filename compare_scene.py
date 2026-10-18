#!/usr/bin/env python3
"""
Run the from-scratch CFAR detector against a real scene chip and its BAQ
and JPEG2000 representations.

Expects you've already run, for the same chip:
    python3 reps/baq.py   <chip>.npy <prefix>_baq.npz   --bits 4 --block-size 128
    python3 reps/jp2.py   <chip>.npy <prefix>_jp2       --ratio 20

Usage:
    python3 compare_real_scene.py <chip>.npy <prefix>_baq.npz <prefix>_jp2
        [--guard 2] [--train 8] [--threshold-db 13] [--tolerance-px 5]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reps.baq import baq_decode_plane
from reps.jp2 import denormalize_plane
from detector.cfar import cfar_detect, cluster_detections


def load_raw(path):
    data = np.load(path)
    if not np.iscomplexobj(data):
        sys.exit(f'error: {path} is not a complex array')
    return np.abs(data)


def load_baq_reconstruction(npz_path):
    z = np.load(npz_path)
    bits, block = int(z['bits_per_sample']), int(z['block_size'])
    i_codes, q_codes = z['iq_codes'][0], z['iq_codes'][1]
    i_scales, q_scales = z['block_scales'][0], z['block_scales'][1]
    i_rec = baq_decode_plane(i_codes, i_scales, bits, block)
    q_rec = baq_decode_plane(q_codes, q_scales, bits, block)
    return np.abs(i_rec + 1j * q_rec)


def load_jp2_reconstruction(jp2_prefix):
    meta = np.load(f'{jp2_prefix}_meta.npz')
    i_clip, q_clip = float(meta['i_clip']), float(meta['q_clip'])
    i_u16 = np.array(Image.open(f'{jp2_prefix}_I.jp2'))
    q_u16 = np.array(Image.open(f'{jp2_prefix}_Q.jp2'))
    i_rec = denormalize_plane(i_u16, i_clip)
    q_rec = denormalize_plane(q_u16, q_clip)
    return np.abs(i_rec + 1j * q_rec)


def run_cfar(magnitude, label, cfar_kw):
    detections, background = cfar_detect(magnitude, **cfar_kw)
    centroids = cluster_detections(detections)
    print(f'{label:>10}: {len(centroids)} detection(s)')
    return centroids


def match_rate(reference, other, tol):
    if not reference:
        return 1.0
    matched = sum(
        1 for r in reference
        if any(np.hypot(r[0] - o[0], r[1] - o[1]) <= tol for o in other)
    )
    return matched / len(reference)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('raw_npy', help='the original chip .npy (complex)')
    ap.add_argument('baq_npz', help='output of reps/baq.py for this chip')
    ap.add_argument('jp2_prefix', help='output prefix used with reps/jp2.py for this chip (without _I.jp2 etc.)')
    ap.add_argument('--guard', type=int, default=2)
    ap.add_argument('--train', type=int, default=8)
    ap.add_argument('--threshold-db', type=float, default=13.0)
    ap.add_argument('--tolerance-px', type=float, default=5.0)
    ap.add_argument('--out', default=None, help='optional path to save results as .npz')
    args = ap.parse_args()

    cfar_kw = dict(guard=args.guard, train=args.train, threshold_db=args.threshold_db)
    print(f'CFAR params: {cfar_kw}\n')

    raw_mag = load_raw(args.raw_npy)
    baq_mag = load_baq_reconstruction(args.baq_npz)
    jp2_mag = load_jp2_reconstruction(args.jp2_prefix)

    raw_det = run_cfar(raw_mag, 'raw', cfar_kw)
    baq_det = run_cfar(baq_mag, 'baq', cfar_kw)
    jp2_det = run_cfar(jp2_mag, 'jp2', cfar_kw)

    tol = args.tolerance_px
    print()
    print(f'baq detections confirmed by raw: {match_rate(baq_det, raw_det, tol):.0%}  (of {len(baq_det)} baq detections)')
    print(f'jp2 detections confirmed by raw: {match_rate(jp2_det, raw_det, tol):.0%}  (of {len(jp2_det)} jp2 detections)')
    print(f'raw detections missed by baq:    {1 - match_rate(raw_det, baq_det, tol):.0%}  (of {len(raw_det)} raw detections)')
    print(f'raw detections missed by jp2:    {1 - match_rate(raw_det, jp2_det, tol):.0%}  (of {len(raw_det)} raw detections)')

    baq_unconfirmed = sum(1 for d in baq_det if not any(np.hypot(d[0] - r[0], d[1] - r[1]) <= tol for r in raw_det))
    jp2_unconfirmed = sum(1 for d in jp2_det if not any(np.hypot(d[0] - r[0], d[1] - r[1]) <= tol for r in raw_det))
    print(f'\nbaq detections with no match in raw (candidate false alarms): {baq_unconfirmed}')
    print(f'jp2 detections with no match in raw (candidate false alarms): {jp2_unconfirmed}')
    print('\n(no ground truth here -- these are raw-vs-compressed agreement numbers, not validated recall/false-alarm rates)')

    if args.out:
        np.savez(
            args.out,
            raw_detections=np.array(raw_det), baq_detections=np.array(baq_det), jp2_detections=np.array(jp2_det),
            cfar_params=np.array([cfar_kw['guard'], cfar_kw['train'], cfar_kw['threshold_db']]),
        )
        print(f'\nsaved {args.out}')


if __name__ == '__main__':
    main()