#!/usr/bin/env python3
"""
JPEG2000 representation for complex SAR samples.

Splits complex (I/Q) SAR data into separate I and Q planes, normalizes each
plane to uint16 using a 99.99th-percentile clip (not a min/max scale -- a
few extreme pixels would otherwise blow out the normalization and crush
everything else into a handful of codes), then encodes each plane as its
own JPEG2000 image at a chosen compression ratio.

Uses Pillow's JPEG2000 plugin (backed by libopenjp2, i.e. the OpenJPEG
reference implementation) rather than glymur, since glymur isn't
installable in every environment -- functionally equivalent, both are
OpenJPEG under the hood.

Input:  a .npy file containing a 2D complex64/complex128 array (raw/
        calibrated SAR samples).
Output: <output_prefix>_I.jp2, <output_prefix>_Q.jp2, and
        <output_prefix>_meta.npz (per-plane clip values needed to invert
        the normalization back to approximate physical units).

Usage:
    python3 jp2.py input_scene.npy output_prefix --ratio 20
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

PERCENTILE = 99.99


def normalize_plane_to_u16(plane: np.ndarray, percentile: float = PERCENTILE):
    """Clip a real-valued plane at the given percentile of |plane| (not
    plain min/max) and linearly map [-clip_val, clip_val] -> [0, 65535].

    Returns (uint16 array, clip_val). clip_val is what you need to invert
    the mapping later: value ~= scaled/65535 * 2*clip_val - clip_val.
    """
    abs_plane = np.abs(plane)
    clip_val = float(np.percentile(abs_plane, percentile))
    if clip_val < 1e-12:
        return np.zeros(plane.shape, dtype=np.uint16), 0.0

    clipped = np.clip(plane, -clip_val, clip_val)
    scaled = (clipped + clip_val) / (2 * clip_val) * 65535.0
    return np.round(scaled).astype(np.uint16), clip_val


def denormalize_plane(u16_plane: np.ndarray, clip_val: float):
    """Inverse of normalize_plane_to_u16, for roundtrip sanity-checking."""
    if clip_val == 0.0:
        return np.zeros(u16_plane.shape, dtype=np.float32)
    scaled = u16_plane.astype(np.float32)
    return scaled / 65535.0 * (2 * clip_val) - clip_val


def encode_plane_jp2(u16_plane: np.ndarray, path: str, ratio: float):
    """Encode a uint16 plane as JPEG2000 at a target compression ratio
    (e.g. ratio=20 means the encoder targets ~1/20th the raw size).
    irreversible=True selects the lossy 9-7 DWT, which is what makes the
    ratio meaningful; the reversible 5-3 transform is lossless and ignores
    the ratio target."""
    im = Image.fromarray(u16_plane)
    im.save(path, format="JPEG2000", quality_mode="rates", quality_layers=[ratio], irreversible=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_npy", help="path to a .npy file with a 2D complex array")
    ap.add_argument("output_prefix", help="output path prefix, e.g. out/scene1 -> out/scene1_I.jp2 etc.")
    ap.add_argument("--ratio", type=float, default=20.0, help="target compression ratio per plane (default 20)")
    ap.add_argument("--percentile", type=float, default=99.99)
    args = ap.parse_args()

    data = np.load(args.input_npy)
    if not np.iscomplexobj(data):
        sys.exit("error: input array must be complex (I/Q samples)")
    if data.ndim != 2:
        sys.exit("error: input array must be 2D (range x azimuth)")

    i_plane = data.real.astype(np.float32)
    q_plane = data.imag.astype(np.float32)

    i_u16, i_clip = normalize_plane_to_u16(i_plane, args.percentile)
    q_u16, q_clip = normalize_plane_to_u16(q_plane, args.percentile)

    i_path = f"{args.output_prefix}_I.jp2"
    q_path = f"{args.output_prefix}_Q.jp2"
    encode_plane_jp2(i_u16, i_path, args.ratio)
    encode_plane_jp2(q_u16, q_path, args.ratio)

    meta_path = f"{args.output_prefix}_meta.npz"
    np.savez(
        meta_path,
        i_clip=i_clip,
        q_clip=q_clip,
        percentile=PERCENTILE,
        ratio=args.ratio,
        orig_shape=np.array(data.shape),
        orig_dtype=str(data.dtype),
    )

    raw_bytes = data.nbytes
    out_bytes = os.path.getsize(i_path) + os.path.getsize(q_path) + os.path.getsize(meta_path)
    print(f"input samples: {data.shape[0]}x{data.shape[1]} ({data.dtype})")
    print(f"raw size:  {raw_bytes:,} bytes")
    print(f"I clip (p{PERCENTILE}): {i_clip:.6g}   Q clip: {q_clip:.6g}")
    print(f"JP2 size:  {out_bytes:,} bytes  (I={os.path.getsize(i_path):,}, Q={os.path.getsize(q_path):,}, target ratio={args.ratio})")
    print(f"ratio:     {raw_bytes / out_bytes:.2f}x  (actual, vs. {args.ratio} target per plane)")


if __name__ == "__main__":
    main()