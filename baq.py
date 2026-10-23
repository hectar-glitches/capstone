#!/usr/bin/env python3
"""
Block-Adaptive Quantization (BAQ) for complex SAR samples.

Splits complex (I/Q) SAR data into separate I and Q planes, partitions each
plane into blocks, and quantizes each block to a fixed bit depth using a
scale factor derived from that block's own standard deviation -- the same
block-adaptive principle used operationally (Sentinel-1 FDBAQ, ERS,
RADARSAT), following the general approach described in Attema & Cafforio
and in Malz et al. (2012). This is a straightforward implementation of
that principle, not a byte-exact reproduction of any one mission's FDBAQ
lookup tables.

Input:  a .npy file containing a 2D complex64/complex128 array (raw/
        calibrated SAR samples -- range x azimuth, or whatever orientation
        your ingestion pipeline produces).
Output: a .npz file containing:
          - iq_codes: int8 array, shape (2, rows, cols) -- quantized I and Q
          - block_scales: float32 array, shape (2, n_blocks_row, n_blocks_col)
          - bits_per_sample, block_size, orig_shape, orig_dtype

Usage:
    python3 baq.py input_scene.npy output_baq.npz --bits 4 --block-size 128
"""
import argparse
import os
import sys

import numpy as np


def quantize_block(block: np.ndarray, bits: int, clip_sigma: float = 3.0):
    """Quantize one real-valued block to a signed `bits`-bit integer code.

    Uses the block's own standard deviation to set the clip range (a simple
    stand-in for the Lloyd-Max-optimized step sizes used in operational
    FDBAQ implementations), then uniformly quantizes the clipped range into
    2**bits signed levels.

    Returns (codes: int8 array same shape as block, step: float). A step of
    0.0 marks a degenerate (all-zero / constant) block; its codes are all
    zero and should be reconstructed as zero.
    """
    sigma = float(block.std())
    n_levels = 2 ** bits
    half = n_levels // 2  # signed range: [-half, half-1]

    if sigma < 1e-12:
        return np.zeros(block.shape, dtype=np.int8), 0.0

    clip_val = clip_sigma * sigma
    step = (2 * clip_val) / n_levels

    clipped = np.clip(block, -clip_val, clip_val)
    codes = np.floor((clipped + clip_val) / step).astype(np.int64) - half
    codes = np.clip(codes, -half, half - 1).astype(np.int8)

    return codes, step


def baq_encode_plane(plane: np.ndarray, bits: int, block_size: int, clip_sigma: float = 3.0):
    rows, cols = plane.shape
    n_br = (rows + block_size - 1) // block_size
    n_bc = (cols + block_size - 1) // block_size

    codes = np.zeros((rows, cols), dtype=np.int8)
    scales = np.zeros((n_br, n_bc), dtype=np.float32)

    for bi in range(n_br):
        r0, r1 = bi * block_size, min((bi + 1) * block_size, rows)
        for bj in range(n_bc):
            c0, c1 = bj * block_size, min((bj + 1) * block_size, cols)
            block = plane[r0:r1, c0:c1]
            block_codes, step = quantize_block(block, bits, clip_sigma)
            codes[r0:r1, c0:c1] = block_codes
            scales[bi, bj] = step

    return codes, scales


def baq_decode_plane(codes: np.ndarray, scales: np.ndarray, bits: int, block_size: int):
    """Inverse of baq_encode_plane -- reconstructs to the midpoint of each
    quantization bin. Used for the roundtrip sanity check."""
    rows, cols = codes.shape
    n_br, n_bc = scales.shape
    half = (2 ** bits) // 2
    out = np.zeros((rows, cols), dtype=np.float32)

    for bi in range(n_br):
        r0, r1 = bi * block_size, min((bi + 1) * block_size, rows)
        for bj in range(n_bc):
            c0, c1 = bj * block_size, min((bj + 1) * block_size, cols)
            step = scales[bi, bj]
            if step == 0.0:
                continue
            block_codes = codes[r0:r1, c0:c1].astype(np.float32)
            clip_val = step * half
            out[r0:r1, c0:c1] = (block_codes + half + 0.5) * step - clip_val

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_npy", help="path to a .npy file with a 2D complex array")
    ap.add_argument("output_npz", help="path to write the quantized output")
    ap.add_argument("--clip-sigma", type=float, default=3.0, help="quantizer clip point in block sigmas")
    ap.add_argument("--bits", type=int, default=4, help="bits per sample per plane (default 4)")
    ap.add_argument("--block-size", type=int, default=128, help="block side length in samples (default 128)")

    args = ap.parse_args()

    data = np.load(args.input_npy)
    if not np.iscomplexobj(data):
        sys.exit("error: input array must be complex (I/Q samples)")
    if data.ndim != 2:
        sys.exit("error: input array must be 2D (range x azimuth)")

    i_plane = data.real.astype(np.float32)
    q_plane = data.imag.astype(np.float32)

    i_codes, i_scales = baq_encode_plane(i_plane, args.bits, args.block_size, args.clip_sigma)
    q_codes, q_scales = baq_encode_plane(q_plane, args.bits, args.block_size, args.clip_sigma)
    iq_codes = np.stack([i_codes, q_codes], axis=0)
    block_scales = np.stack([i_scales, q_scales], axis=0)

    np.savez_compressed(
        args.output_npz,
        iq_codes=iq_codes,
        block_scales=block_scales,
        bits_per_sample=args.bits,
        block_size=args.block_size,
        orig_shape=np.array(data.shape),
        orig_dtype=str(data.dtype),
    )

    raw_bytes = data.nbytes
    out_bytes = os.path.getsize(args.output_npz)
    print(f"input samples: {data.shape[0]}x{data.shape[1]} ({data.dtype})")
    print(f"raw size:  {raw_bytes:,} bytes")
    print(f"BAQ size:  {out_bytes:,} bytes  ({args.bits} bits/sample/plane, block={args.block_size})")
    print(f"ratio:     {raw_bytes / out_bytes:.2f}x")


if __name__ == "__main__":
    main()