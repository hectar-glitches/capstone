#!/usr/bin/env python3
"""
Vessel candidate detector for Sentinel-1 SAR.

Takes a SAR image and returns ranked candidate vessel locations as a CSV.
Accepts either a .npy complex chip or a GeoTIFF (full burst or scene), and
tiles large rasters with windowed reads so memory stays flat regardless of
input size.

    python3 detect_vessels.py burst.tiff candidates.csv
    python3 detect_vessels.py chip_ships.npy candidates.csv --min-contrast 18

What it does per tile:
  - skips tiles that are mostly zero padding (burst edges)
  - measures clutter statistics: coefficient of variation of intensity and
    mean backscatter. Homogeneous sea sits near CV 1.0; land is bright and
    textured. Both are recorded per candidate so land can be filtered after
    the fact rather than guessed at up front.
  - runs CA-CFAR, then merges flagged pixels within a radius into one object
    so a smeared vessel is counted once rather than a dozen times

Per candidate it reports position, peak backscatter, contrast over the local
sea, and physical extent in metres. Extent matters: a one-pixel blip is
usually speckle, while a vessel is tens to hundreds of metres, and the length
is also what you eventually match against an AIS record.

Geographic coordinates are emitted when the raster carries a transform or
ground control points. Sentinel-1 SLC products are in radar geometry and
often carry neither, in which case pixel coordinates are all you get here and
geocoding needs the geolocation grid from the product's annotation XML.
"""
import argparse
import csv
import os
import sys

import numpy as np
from scipy.ndimage import (label, center_of_mass, binary_dilation,
                           generate_binary_structure, iterate_structure)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from cfar import cfar_detect
except ImportError:
    from detector.cfar import cfar_detect

RANGE_M, AZIMUTH_M = 2.3, 14.0          # Sentinel-1 IW SLC nominal pixel spacing


def cluster(det, merge):
    """Centroids, one per object, merging flagged pixels within `merge` pixels."""
    if not det.any():
        return [], None
    if merge > 0:
        st = iterate_structure(generate_binary_structure(2, 2), merge)
        lab, n = label(binary_dilation(det, structure=st))
        lab = lab * det
    else:
        lab, n = label(det)
    ids = [i for i in range(1, n + 1) if (lab == i).any()]
    if not ids:
        return [], None
    return list(zip(ids, center_of_mass(det, lab, ids))), lab


def analyse_tile(chip, row_off, col_off, args):
    """Returns (tile_stats, [candidate dicts]) for one tile of complex samples."""
    inten = np.abs(chip) ** 2
    if inten.mean() == 0:
        return None, []

    zero_frac = float((inten == 0).mean())
    cv = float(inten.std() / inten.mean())
    mean_db = float(10 * np.log10(inten.mean()))
    stats = dict(cv=round(cv, 3), mean_db=round(mean_db, 2), zero_frac=round(zero_frac, 4))
    if zero_frac > args.max_zero_frac:
        return stats, []

    mag = np.abs(chip)
    det, background = cfar_detect(mag, args.guard, args.train, args.threshold_db)
    objs, lab = cluster(det, args.merge)
    if not objs:
        return stats, []

    db = 20 * np.log10(mag + 1e-6)
    sea_db = float(np.median(db))

    out = []
    for oid, (r, c) in objs:
        mask = lab == oid
        rr, cc = np.nonzero(mask)
        pad = max(args.merge, 3)
        r0, r1 = max(0, rr.min() - pad), min(mag.shape[0], rr.max() + pad + 1)
        c0, c1 = max(0, cc.min() - pad), min(mag.shape[1], cc.max() + pad + 1)
        peak_db = float(db[r0:r1, c0:c1].max())

        extent_az = (rr.max() - rr.min() + 1) * AZIMUTH_M
        extent_rg = (cc.max() - cc.min() + 1) * RANGE_M

        out.append(dict(
            row=round(row_off + r, 1), col=round(col_off + c, 1),
            peak_db=round(peak_db, 1),
            contrast_db=round(peak_db - sea_db, 1),
            pixels=int(mask.sum()),
            extent_azimuth_m=round(extent_az, 1),
            extent_range_m=round(extent_rg, 1),
            **stats,
        ))
    return stats, out


def geocode(src, cands):
    """Attach lat/lon to each candidate when the raster carries a usable
    transform or ground control points. Returns True if it managed it.

    Sentinel-1 SLC is in radar geometry and frequently carries neither, in
    which case the product's annotation XML holds a geolocation grid of
    line/pixel to lat/lon tie points and geocoding means interpolating that.
    """
    from rasterio.transform import xy, from_gcps
    from rasterio.warp import transform as warp_transform

    transform, crs = None, None
    gcps, gcp_crs = src.gcps
    if gcps:
        transform, crs = from_gcps(gcps), gcp_crs
    elif src.crs is not None and not src.transform.is_identity:
        transform, crs = src.transform, src.crs
    if transform is None or crs is None:
        return False

    rows = [c["row"] for c in cands]
    cols = [c["col"] for c in cands]
    xs, ys = xy(transform, rows, cols)
    lons, lats = warp_transform(crs, "EPSG:4326", xs, ys)
    for c, lon, lat in zip(cands, lons, lats):
        c["lon"] = round(float(lon), 6)
        c["lat"] = round(float(lat), 6)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help=".npy complex chip, or a GeoTIFF burst/scene")
    ap.add_argument("out_csv")
    ap.add_argument("--tile", type=int, default=1024, help="tile size for large rasters (default 1024)")
    ap.add_argument("--guard", type=int, default=2)
    ap.add_argument("--train", type=int, default=8)
    ap.add_argument("--threshold-db", type=float, default=13.0)
    ap.add_argument("--merge", type=int, default=5, help="object merge radius in pixels")
    ap.add_argument("--max-zero-frac", type=float, default=0.05)
    ap.add_argument("--min-contrast", type=float, default=0.0,
                    help="drop candidates below this dB over the local sea median")
    ap.add_argument("--min-pixels", type=int, default=2,
                    help="drop candidates smaller than this many pixels. A vessel is "
                         "spatially extended; a single flagged pixel is almost always "
                         "a speckle outlier that happened to cross threshold (default 2)")
    ap.add_argument("--max-cv", type=float, default=0.0,
                    help="if >0, drop candidates from tiles above this CV (crude land filter)")
    args = ap.parse_args()

    cands = []
    geo = False

    if args.image.lower().endswith(".npy"):
        chip = np.load(args.image)
        if not np.iscomplexobj(chip):
            sys.exit("error: .npy must hold complex samples")
        stats, found = analyse_tile(chip, 0, 0, args)
        print(f"1 tile  cv={stats['cv']} mean={stats['mean_db']}dB  ->  {len(found)} candidate(s)")
        cands = found
    else:
        import rasterio
        from rasterio.windows import Window
        with rasterio.open(args.image) as src:
            print(f"{src.width} x {src.height}, dtype={src.dtypes[0]}")
            rows = range(0, src.height, args.tile)
            cols = range(0, src.width, args.tile)
            total = len(list(rows)) * len(list(cols))
            k = 0
            for r0 in range(0, src.height, args.tile):
                h = min(args.tile, src.height - r0)
                for c0 in range(0, src.width, args.tile):
                    k += 1
                    w = min(args.tile, src.width - c0)
                    chip = src.read(1, window=Window(c0, r0, w, h)).astype(np.complex64)
                    stats, found = analyse_tile(chip, r0, c0, args)
                    if stats is None:
                        continue
                    if found:
                        print(f"[{k}/{total}] r{r0} c{c0}  cv={stats['cv']:.2f} "
                              f"mean={stats['mean_db']:.1f}dB  -> {len(found)}")
                    cands.extend(found)
            if cands:
                try:
                    geo = geocode(src, cands)
                except Exception as e:
                    print(f"geocoding unavailable: {e}")
            print("geocoded to lat/lon" if geo else
                  "no usable transform or GCPs - pixel coordinates only "
                  "(geocoding needs the geolocation grid from the annotation XML)")

    before = len(cands)
    if args.min_pixels > 1:
        cands = [c for c in cands if c["pixels"] >= args.min_pixels]
    if args.min_contrast > 0:
        cands = [c for c in cands if c["contrast_db"] >= args.min_contrast]
    if args.max_cv > 0:
        cands = [c for c in cands if c["cv"] <= args.max_cv]
    cands.sort(key=lambda c: -c["contrast_db"])

    if not cands:
        print(f"no candidates survived filtering ({before} before filters)")
        return

    fields = ["row", "col"] + (["lat", "lon"] if geo else []) + \
             ["peak_db", "contrast_db", "pixels",
              "extent_azimuth_m", "extent_range_m", "cv", "mean_db", "zero_frac"]
    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(cands)

    print(f"\n{len(cands)} candidate(s) written to {args.out_csv}"
          f"{f' ({before - len(cands)} filtered out)' if before != len(cands) else ''}\n")
    print(f'{"row":>9} {"col":>9} {"peak":>7} {"contrast":>9} {"az_m":>7} {"rg_m":>7}')
    for c in cands[:20]:
        print(f'{c["row"]:>9.0f} {c["col"]:>9.0f} {c["peak_db"]:>7.1f} '
              f'{c["contrast_db"]:>9.1f} {c["extent_azimuth_m"]:>7.0f} {c["extent_range_m"]:>7.0f}')
    if len(cands) > 20:
        print(f"... and {len(cands) - 20} more")


if __name__ == "__main__":
    main()
