#!/usr/bin/env python3
"""
Extract a small complex64 chip from a real Sentinel-1 SLC measurement
GeoTIFF (full scene or single burst), in the exact format the rest of the
pipeline expects (reps/baq.py, reps/jp2.py, detector/*): a 2D complex64
.npy array.

Install rasterio

    python3 -m pip install rasterio

Where to find the measurement file:
  - A full SLC product (.SAFE folder once unzipped) has one GeoTIFF per
    subswath/polarization under measurement/, named like
    s1a-iw1-slc-vv-....tiff, pick one subswath/polarization.
  - An ASF SLC-BURST product is a single GeoTIFF (plus an XML annotation)
    per burst, already small, there's no subswath to choose.

Usage:
    python3 extract_chip.py measurement.tiff chip.npy \\
        --row-offset 5000 --col-offset 5000 --size 1024
"""
import argparse
import numpy as np
import rasterio
from rasterio.windows import Window


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('measurement_tiff', help='path to the SLC measurement GeoTIFF')
    ap.add_argument('output_npy', help='where to write the complex64 chip')
    ap.add_argument('--row-offset', type=int, default=0, help='starting row (default 0, i.e. top of the image)')
    ap.add_argument('--col-offset', type=int, default=0, help='starting column (default 0)')
    ap.add_argument('--size', type=int, default=1024, help='chip side length in pixels (default 1024)')
    args = ap.parse_args()

    with rasterio.open(args.measurement_tiff) as src:
        print(f'full image: {src.width} x {src.height}, dtype={src.dtypes[0]}, bands={src.count}')

        row0 = max(0, min(args.row_offset, src.height - 1))
        col0 = max(0, min(args.col_offset, src.width - 1))
        h = min(args.size, src.height - row0)
        w = min(args.size, src.width - col0)
        window = Window(col0, row0, w, h)

        chip = src.read(1, window=window)

    if not np.iscomplexobj(chip):
        print(f'warning: band dtype is {chip.dtype}, not complex -- this measurement file may not be an SLC product (check it is not a GRD/amplitude-only file)')
    chip = chip.astype(np.complex64)

    np.save(args.output_npy, chip)
    print(f'wrote {args.output_npy}: {chip.shape[0]}x{chip.shape[1]} complex64 ({chip.nbytes:,} bytes)')


if __name__ == '__main__':
    main()