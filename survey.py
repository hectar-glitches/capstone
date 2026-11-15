#!/usr/bin/env python3
"""
Score tiles of a scene so you can pick chips worth working on.

Takes a .tiff, or a Sentinel-1 .SAFE.zip read in place with no extraction.
Per tile it reports the coefficient of variation of intensity, mean
backscatter, how far the tile sits above the thermal noise floor, and how
many vessel-sized objects CFAR finds.

    python3 survey.py scene.tiff
    python3 survey.py product.SAFE.zip --swath IW3 --pol vh
    python3 survey.py product.SAFE.zip --swath IW3 --pol vh --rows 2000 6000 10000

Open water sits near CV 1.0. Land is bright with high CV. Water holding
point targets is dark with high CV.

STNR is signal power over thermal noise power, taken from the product's own
noise calibration file. It matters because FDBAQ chooses each block's bit
rate from exactly this ratio, so a tile's STNR predicts how many bits the
satellite spent there. A tile near 0 dB is noise-limited, which is where
detection is most fragile and where extra quantization noise should bite.
"""
import argparse, csv, os, sys, zipfile
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from rasterio.windows import Window
from cfar import cfar_detect, cluster_detections


def from_zip(path, swath, pol):
    """GDAL path to a measurement raster inside a .SAFE.zip, plus its noise LUT."""
    zf = zipfile.ZipFile(path)
    key = f"-{swath.lower()}-slc-{pol.lower()}-"
    # .endswith(".tiff") matters: the measurement folder also holds a
    # <name>.tiff.msk validity mask, which is 8-bit and all 255. Opening that
    # by mistake gives a constant image and silently wrong statistics.
    meas = [n for n in zf.namelist() if "/measurement/" in n and key in n.lower()
            and n.lower().endswith(".tiff")]
    noise = [n for n in zf.namelist() if "noise-" in n and key in n.lower()]
    if not meas:
        sys.exit(f"no {swath} {pol} measurement in {os.path.basename(path)}")
    lut = None
    if noise:
        root = ET.fromstring(zf.read(noise[0]))
        v = root.findall("noiseRangeVectorList/noiseRangeVector")
        if v:
            mid = v[len(v) // 2]
            px = np.array([int(x) for x in mid.find("pixel").text.split()])
            val = np.array([float(x) for x in mid.find("noiseRangeLut").text.split()])
            lut = (px, val)
    return f"/vsizip/{os.path.abspath(path)}/{meas[0]}", lut


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help=".tiff, or a .SAFE.zip with --swath and --pol")
    ap.add_argument("--swath", default="IW3")
    ap.add_argument("--pol", default="vh")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--rows", type=int, nargs="+", default=None,
                    help="row offsets to scan (default: four spread down the scene)")
    ap.add_argument("--labels", help="SARFish SLC_validation.csv, to count "
                                     "labelled objects per tile")
    ap.add_argument("--product", help="product identifier to filter labels by; "
                                      "default is taken from the zip filename")
    ap.add_argument("--threshold-db", type=float, default=13.0)
    ap.add_argument("--min-pixels", type=int, default=2)
    args = ap.parse_args()

    # labelled object positions, in this swath's own pixel space
    pts = []
    if args.labels:
        prod = args.product or os.path.basename(args.path).split(".SAFE")[0]
        sw = args.swath.upper().replace("IW", "")
        with open(args.labels) as f:
            for r in csv.DictReader(f):
                if r["SLC_product_identifier"] == prod and r["swath_index"] == sw:
                    pts.append((float(r["detect_scene_row"]),
                                float(r["detect_scene_column"])))
        print(f"{len(pts)} labelled object(s) in {prod} swath {sw}")

    lut = None
    src_path = args.path
    if args.path.lower().endswith(".zip"):
        src_path, lut = from_zip(args.path, args.swath, args.pol)

    with rasterio.open(src_path) as src:
        print(f"{src.width} x {src.height}  {src.dtypes[0]}"
              f"{'' if lut is None else '   noise LUT loaded'}")
        rows = args.rows or list(np.linspace(args.size, src.height - 2*args.size, 4).astype(int))
        print(f"\n{'row':>7} {'col':>7} {'CV':>6} {'meandB':>8} {'noisedB':>8}"
              f" {'I/N dB':>8} {'zeros':>7} {'CFAR':>5}"
              f"{'' if not pts else format('labels', '>7')}")
        for row in rows:
            for col in range(0, src.width - args.size, args.size):
                a = src.read(1, window=Window(col, row, args.size, args.size)).astype(np.complex64)
                I = np.abs(a) ** 2
                if I.mean() == 0:
                    continue
                noise_db, ratio_db = float("nan"), float("nan")
                if lut is not None:
                    # Measured intensity already contains the thermal noise, so
                    # report total-over-noise rather than subtracting. A tile at
                    # 0 dB is pure noise; +10 dB means signal dominates. Over
                    # calm water in cross-pol the sea can sit at the noise floor,
                    # and subtracting first would clamp to a meaningless number.
                    n = float(np.interp(col + args.size/2, lut[0], lut[1]))
                    noise_db = 10*np.log10(n)
                    ratio_db = 10*np.log10(I.mean() / n)
                det, _ = cfar_detect(np.abs(a), guard=2, train=8,
                                     threshold_db=args.threshold_db)
                k = len(cluster_detections(det, min_pixels=args.min_pixels))
                print(f"{row:>7} {col:>7} {I.std()/I.mean():>6.2f}"
                      f" {10*np.log10(I.mean()):>8.1f} {noise_db:>8.1f}"
                      f" {ratio_db:>8.1f} {(I==0).mean():>6.1%} {k:>5}"
                      + ("" if not pts else
                         f"{sum(1 for y, x in pts if row <= y < row+args.size and col <= x < col+args.size):>7}"))


if __name__ == "__main__":
    main()
