#!/usr/bin/env python3
"""
Look inside a Sentinel-1 .SAFE.zip without unzipping it.

GDAL can read a file inside a zip archive through its /vsizip/ virtual
filesystem, so a 7 GB product stays as a 3.6 GB zip on disk and nothing is
extracted. Reads are windowed, so memory stays flat too.

    python3 probe_safe.py data/sarfish_sample/SLC/validation/*.zip

Prints, per subswath and polarisation: image size, pixel spacing, incidence
angle, burst layout, and the thermal noise floor from the product's own
calibration files. The noise floor matters because FDBAQ picks each block's
bit rate from the ratio of signal to thermal noise, so it is the reference
every rate-selection experiment needs.
"""
import argparse
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np


def vsizip(zip_path, inner):
    """GDAL path for a file inside a zip. The archive is not extracted."""
    return f"/vsizip/{os.path.abspath(zip_path)}/{inner}"


def text(root, path, default=None):
    el = root.find(path)
    return el.text if el is not None else default


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip_path")
    ap.add_argument("--open-rasters", action="store_true", default=True,
                    help="also open each measurement file to confirm zip reads work")
    args = ap.parse_args()

    zf = zipfile.ZipFile(args.zip_path)
    names = zf.namelist()
    meas = sorted(n for n in names if "/measurement/" in n and n.endswith(".tiff"))
    annos = sorted(n for n in names if "/annotation/" in n and n.endswith(".xml")
                   and "/calibration/" not in n)
    noises = sorted(n for n in names if "noise-" in n and n.endswith(".xml"))

    print(f"{os.path.basename(args.zip_path)}")
    print(f"  {len(meas)} measurement rasters, {len(annos)} annotations, "
          f"{len(noises)} noise files")
    print(f"  compressed {os.path.getsize(args.zip_path)/2**30:.2f} GB, "
          f"uncompressed {sum(i.file_size for i in zf.infolist())/2**30:.2f} GB\n")

    for a in annos:
        root = ET.fromstring(zf.read(a))
        swath = text(root, "adsHeader/swath")
        pol = text(root, "adsHeader/polarisation")
        info = root.find("imageAnnotation/imageInformation")
        lines = int(text(root, "imageAnnotation/imageInformation/numberOfLines", 0))
        samples = int(text(root, "imageAnnotation/imageInformation/numberOfSamples", 0))
        rg = float(text(root, "imageAnnotation/imageInformation/rangePixelSpacing", "nan"))
        az = float(text(root, "imageAnnotation/imageInformation/azimuthPixelSpacing", "nan"))
        inc = text(root, "imageAnnotation/imageInformation/incidenceAngleMidSwath", "?")
        bursts = root.findall("swathTiming/burstList/burst")
        lpb = text(root, "swathTiming/linesPerBurst", "?")
        spb = text(root, "swathTiming/samplesPerBurst", "?")

        print(f"  {swath} {pol}")
        print(f"     {samples} x {lines}   spacing {rg:.3f} m range, {az:.3f} m azimuth"
              f"   incidence {float(inc):.2f} deg" if inc != "?" else "")
        print(f"     {len(bursts)} bursts, {lpb} lines x {spb} samples each")

        # geographic corners from the geolocation grid
        pts = root.findall("geolocationGrid/geolocationGridPointList/geolocationGridPoint")
        if pts:
            lats = [float(p.find("latitude").text) for p in pts]
            lons = [float(p.find("longitude").text) for p in pts]
            print(f"     lat {min(lats):.3f} to {max(lats):.3f}, "
                  f"lon {min(lons):.3f} to {max(lons):.3f}")

        # thermal noise floor
        nf = [n for n in noises if os.path.basename(a)[:-4] in n]
        if nf:
            nroot = ET.fromstring(zf.read(nf[0]))
            vecs = nroot.findall("noiseRangeVectorList/noiseRangeVector")
            if vecs:
                vals = np.array([float(x) for x
                                 in vecs[len(vecs)//2].find("noiseRangeLut").text.split()])
                vals = vals[vals > 0]
                if vals.size:
                    print(f"     thermal noise LUT  median {np.median(vals):.1f}"
                          f"  ({10*np.log10(np.median(vals)):.1f} dB)"
                          f"  min {vals.min():.1f}  max {vals.max():.1f}")

        if args.open_rasters:
            m = [x for x in meas if os.path.basename(a)[:-4].replace("-", "") 
                 in os.path.basename(x).replace("-", "").replace("_SARFish", "")]
            if m:
                try:
                    import rasterio
                    with rasterio.open(vsizip(args.zip_path, m[0])) as src:
                        print(f"     raster opens from zip: {src.width} x {src.height}"
                              f"  {src.dtypes[0]}  {src.count} band(s)")
                except Exception as e:
                    print(f"     raster open FAILED: {type(e).__name__}: {e}")
        print()

    print("Nothing was extracted. To read a window later, use the same /vsizip/ path:")
    if meas:
        print(f"  {vsizip(args.zip_path, meas[0])}")


if __name__ == "__main__":
    main()
