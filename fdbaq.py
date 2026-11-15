#!/usr/bin/env python3
"""
FDBAQ (Flexible Dynamic Block Adaptive Quantization) as specified for
Sentinel-1, applied to complex SAR samples.

This is the real scheme. The difference that matters for detection: FDBAQ reconstructs to
*non-uniformly spaced* levels (finer near zero, coarser toward the tail)
scaled by a per-block factor, rather than uniformly dividing a +/- k*sigma
range.

Tables below are the Sentinel-1 Level-0 decoding tables (ESA Level-0 Data
Decoding Package, pp. 78-80):
  - BRCn  : simple reconstruction values, used when THIDX is small
  - NRLn  : Normalized Reconstruction Levels per Bit Rate Code
  - SF    : Sigma Factor table, indexed by Threshold Index (THIDX)

Decode rule, per the spec:
    if THIDX <= simple_threshold[BRC]:  value = sign * BRCn[THIDX]
    else:                               value = sign * NRLn[mcode] * SF[THIDX]

IMPORTANT, and this is the interesting part for the capstone: the spec
defines *decoding*. How an encoder picks BRC and THIDX per block is not
specified -- that choice is the rate-allocation decision, and it is exactly
the thing this project argues should be task-aware. The default policy here
("sigma") picks THIDX so that SF[THIDX] ~= the block's standard deviation,
which is the natural clutter-driven choice and the direct analogue of
baq.py's sigma-based clip.

Usage:
    python3 fdbaq.py input_scene.npy output_fdbaq.npz --brc 4 --block-size 128
    python3 fdbaq.py input_scene.npy out.npz --thidx-scale 2.0   # looser tail
"""
import argparse
import os
import sys

import numpy as np

# --- Sentinel-1 L0 decoding tables (ESA L0 Data Decoding Package pp. 78-80) ---

BRC_SIMPLE = {
    0: np.array([3., 3., 3.16, 3.53], dtype=np.float64),
    1: np.array([4., 4., 4.08, 4.37], dtype=np.float64),
    2: np.array([6., 6., 6., 6.15, 6.5, 6.88], dtype=np.float64),
    3: np.array([9., 9., 9., 9., 9.36, 9.50, 10.1], dtype=np.float64),
    4: np.array([15., 15., 15., 15., 15., 15., 15.22, 15.50, 16.05], dtype=np.float64),
}

NRL = {
    0: np.array([.3637, 1.0915, 1.8208, 2.6406], dtype=np.float64),
    1: np.array([.3042, .9127, 1.5216, 2.1313, 2.8426], dtype=np.float64),
    2: np.array([.2305, .6916, 1.1528, 1.6140, 2.0754, 2.5369, 3.1191], dtype=np.float64),
    3: np.array([.1702, .5107, .8511, 1.1916, 1.5321, 1.8726, 2.2131, 2.5536, 2.8942, 3.3744], dtype=np.float64),
    4: np.array([.1130, .3389, .5649, .7908, 1.0167, 1.2428, 1.4687, 1.6947, 1.9206, 2.1466,
                 2.3725, 2.5985, 2.8244, 3.0504, 3.2764, 3.6623], dtype=np.float64),
}

# THIDX value at or below which the simple BRC table is used instead of NRL*SF
SIMPLE_THIDX_MAX = {0: 3, 1: 3, 2: 5, 3: 6, 4: 8}

_SF_LIST = [
    0., 0.630, 1.250, 1.880, 2.510, 3.130, 3.760, 4.390, 5.010, 5.640, 6.270, 6.890, 7.520,
    8.150, 8.770, 9.40, 10.030, 10.650, 11.280, 11.910, 12.530, 13.160, 13.790, 14.410,
    15.040, 15.670, 16.290, 16.920, 17.550, 18.170, 18.80, 19.430, 20.050, 20.680, 21.310,
    21.930, 22.560, 23.190, 23.810, 24.440, 25.070, 25.690, 26.320, 26.950, 27.570, 28.20,
    28.830, 29.450, 30.080, 30.710, 31.330, 31.960, 32.590, 33.210, 33.840, 34.470, 35.090,
    35.720, 36.350, 36.970, 37.60, 38.230, 38.850, 39.480, 40.110, 40.730, 41.360, 41.990,
    42.610, 43.240, 43.870, 44.490, 45.120, 45.750, 46.370, 47., 47.630, 48.250, 48.880,
    49.510, 50.130, 50.760, 51.390, 52.010, 52.640, 53.270, 53.890, 54.520, 55.150, 55.770,
    56.40, 57.030, 57.650, 58.280, 58.910, 59.530, 60.160, 60.790, 61.410, 62.040, 62.980,
    64.240, 65.490, 66.740, 68., 69.250, 70.50, 71.760, 73.010, 74.260, 75.520, 76.770,
    78.020, 79.280, 80.530, 81.780, 83.040, 84.290, 85.540, 86.80, 88.050, 89.30, 90.560,
    91.810, 93.060, 94.320, 95.570, 96.820, 98.080, 99.330, 100.580, 101.840, 103.090,
    104.340, 105.60, 106.850, 108.10, 109.350, 110.610, 111.860, 113.110, 114.370, 115.620,
    116.870, 118.130, 119.380, 120.630, 121.890, 123.140, 124.390, 125.650, 126.90, 128.150,
    129.410, 130.660, 131.910, 133.170, 134.420, 135.670, 136.930, 138.180, 139.430, 140.690,
    141.940, 143.190, 144.450, 145.70, 146.950, 148.210, 149.460, 150.710, 151.970, 153.220,
    154.470, 155.730, 156.980, 158.230, 159.490, 160.740, 161.990, 163.250, 164.50, 165.750,
    167.010, 168.260, 169.510, 170.770, 172.020, 173.270, 174.530, 175.780, 177.030, 178.290,
    179.540, 180.790, 182.050, 183.30, 184.550, 185.810, 187.060, 188.310, 189.570, 190.820,
    192.070, 193.330, 194.580, 195.830, 197.090, 198.340, 199.590, 200.850, 202.10, 203.350,
    204.610, 205.860, 207.110, 208.370, 209.620, 210.870, 212.130, 213.380, 214.630, 215.890,
    217.140, 218.390, 219.650, 220.90, 222.150, 223.410, 224.660, 225.910, 227.170, 228.420,
    229.670, 230.930, 232.180, 233.430, 234.690, 235.940, 237.190, 238.450, 239.70, 240.950,
    242.210, 243.460, 244.710, 245.970, 247.220, 248.470, 249.730, 250.980, 252.230, 253.490,
    254.740, 255.990, 255.990,
]
SF = np.array(_SF_LIST, dtype=np.float64)


def choose_thidx(sigma: float, scale: float = 1.0) -> int:
    """Pick the Threshold Index whose Sigma Factor best matches `scale * sigma`.

    This is the encoder-side rate-allocation decision. The spec does not
    define it. `scale` = 1.0 is the clutter-driven default; raising it widens
    the representable range and is the FDBAQ analogue of loosening baq.py's
    clip_sigma.
    """
    target = scale * sigma
    if target <= 0:
        return 0
    return int(np.argmin(np.abs(SF - target)))


def quantize_block(block: np.ndarray, brc: int, thidx: int):
    """Quantize one real-valued block to FDBAQ magnitude codes + signs.

    Returns (mcodes uint8, signs int8). Reconstruction is handled by
    dequantize_block using the same (brc, thidx).
    """
    levels = NRL[brc]
    signs = np.where(block < 0, -1, 1).astype(np.int8)
    mag = np.abs(block)

    if thidx <= SIMPLE_THIDX_MAX[brc]:
        # Simple-reconstruction regime: a single magnitude per block.
        return np.zeros(block.shape, dtype=np.uint8), signs

    scaled = mag / SF[thidx]
    # Nearest non-uniform level. Levels are sorted, so use midpoints.
    edges = (levels[:-1] + levels[1:]) / 2.0
    mcodes = np.searchsorted(edges, scaled).astype(np.uint8)
    return mcodes, signs


def dequantize_block(mcodes: np.ndarray, signs: np.ndarray, brc: int, thidx: int) -> np.ndarray:
    if thidx <= SIMPLE_THIDX_MAX[brc]:
        value = BRC_SIMPLE[brc][min(thidx, len(BRC_SIMPLE[brc]) - 1)]
        return signs.astype(np.float64) * value
    return signs.astype(np.float64) * NRL[brc][mcodes] * SF[thidx]


def encode_plane(plane: np.ndarray, brc: int, block_size: int, thidx_scale: float = 1.0):
    rows, cols = plane.shape
    n_br = (rows + block_size - 1) // block_size
    n_bc = (cols + block_size - 1) // block_size

    mcodes = np.zeros((rows, cols), dtype=np.uint8)
    signs = np.ones((rows, cols), dtype=np.int8)
    thidx = np.zeros((n_br, n_bc), dtype=np.uint8)

    for bi in range(n_br):
        r0, r1 = bi * block_size, min((bi + 1) * block_size, rows)
        for bj in range(n_bc):
            c0, c1 = bj * block_size, min((bj + 1) * block_size, cols)
            block = plane[r0:r1, c0:c1]
            t = choose_thidx(float(block.std()), thidx_scale)
            m, s = quantize_block(block, brc, t)
            mcodes[r0:r1, c0:c1] = m
            signs[r0:r1, c0:c1] = s
            thidx[bi, bj] = t

    return mcodes, signs, thidx


def decode_plane(mcodes: np.ndarray, signs: np.ndarray, thidx: np.ndarray, brc: int, block_size: int):
    rows, cols = mcodes.shape
    n_br, n_bc = thidx.shape
    out = np.zeros((rows, cols), dtype=np.float64)

    for bi in range(n_br):
        r0, r1 = bi * block_size, min((bi + 1) * block_size, rows)
        for bj in range(n_bc):
            c0, c1 = bj * block_size, min((bj + 1) * block_size, cols)
            out[r0:r1, c0:c1] = dequantize_block(
                mcodes[r0:r1, c0:c1], signs[r0:r1, c0:c1], brc, int(thidx[bi, bj])
            )
    return out


def load_fdbaq_reconstruction(npz_path: str) -> np.ndarray:
    """Reconstruct the complex array from an fdbaq.py output. Import this from
    compare_scene.py to score FDBAQ alongside BAQ and JPEG2000."""
    z = np.load(npz_path)
    brc, block = int(z["brc"]), int(z["block_size"])
    i_rec = decode_plane(z["mcodes"][0], z["signs"][0], z["thidx"][0], brc, block)
    q_rec = decode_plane(z["mcodes"][1], z["signs"][1], z["thidx"][1], brc, block)
    return (i_rec + 1j * q_rec).astype(np.complex64)


def entropy_bits_per_sample(mcodes: np.ndarray, brc: int) -> float:
    """Rate-honest estimate: zeroth-order entropy of the magnitude codes, plus
    one sign bit. Reported per real sample (double it for bits/complex sample).
    Avoids reimplementing the Huffman tables while still charging for the bits
    actually needed."""
    counts = np.bincount(mcodes.ravel(), minlength=len(NRL[brc])).astype(np.float64)
    p = counts[counts > 0] / counts.sum()
    return float(-(p * np.log2(p)).sum()) + 1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_npy")
    ap.add_argument("output_npz")
    ap.add_argument("--brc", type=int, default=4, choices=[0, 1, 2, 3, 4],
                    help="Bit Rate Code: 0=4 levels ... 4=16 levels (default 4)")
    ap.add_argument("--block-size", type=int, default=128)
    ap.add_argument("--thidx-scale", type=float, default=1.0,
                    help="multiplier on block sigma when choosing THIDX (default 1.0)")
    args = ap.parse_args()

    data = np.load(args.input_npy)
    if not np.iscomplexobj(data):
        sys.exit("error: input array must be complex (I/Q samples)")

    i_plane = data.real.astype(np.float64)
    q_plane = data.imag.astype(np.float64)

    i_m, i_s, i_t = encode_plane(i_plane, args.brc, args.block_size, args.thidx_scale)
    q_m, q_s, q_t = encode_plane(q_plane, args.brc, args.block_size, args.thidx_scale)

    np.savez_compressed(
        args.output_npz,
        mcodes=np.stack([i_m, q_m]), signs=np.stack([i_s, q_s]), thidx=np.stack([i_t, q_t]),
        brc=args.brc, block_size=args.block_size, thidx_scale=args.thidx_scale,
        orig_shape=np.array(data.shape),
    )

    bps = entropy_bits_per_sample(i_m, args.brc)
    recon = load_fdbaq_reconstruction(args.output_npz)
    raw_bytes = data.nbytes
    out_bytes = os.path.getsize(args.output_npz)

    print(f"input samples: {data.shape[0]}x{data.shape[1]} ({data.dtype})")
    print(f"BRC {args.brc} ({len(NRL[args.brc])} levels), block={args.block_size}, thidx_scale={args.thidx_scale}")
    print(f"rate:      {2*bps:.2f} bits/complex sample (entropy + sign, rate-honest)")
    print(f"file size: {out_bytes:,} bytes  vs raw {raw_bytes:,}  ({raw_bytes/out_bytes:.2f}x)")
    print(f"max |x|:   input {np.abs(data).max():.1f}  ->  reconstructed {np.abs(recon).max():.1f}")


if __name__ == "__main__":
    main()