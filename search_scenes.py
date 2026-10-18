#!/usr/bin/env python3
"""
Search for Sentinel-1 scenes over a coastal AOI using asf_search.

This also checks SLC-BURST products, which are single bursts (roughly a
1/9th-ish slice of a full IW scene) rather than whole ~7.4GB scenes, which
is the actual fix for the big-file problem: a burst still has phase-preserved
I/Q data (unlike GRD), so it still works for the BAQ/JPEG2000/CFAR pipeline,
just at a much smaller download size.

Setup (run this on your own machine, not in a sandbox without PyPI access):

    python3 -m pip install asf_search
    # or: conda install -c conda-forge asf_search

You also need a free NASA Earthdata Login account to actually download
anything (not needed just to search):
    https://urs.earthdata.nasa.gov/users/new

Usage:
    python3 search_scenes.py                # search only, no download
    python3 search_scenes.py --download 0    # download result #0 from the
                                              # burst search (prompts for
                                              # your Earthdata username/password)
"""
import argparse
import asf_search as asf


AOI_WKT = (
    'POLYGON((-80.95 31.85, -80.60 31.85, -80.60 32.05, '
    '-80.95 32.05, -80.95 31.85))'
)

START = '2026-07-01T00:00:00Z'
END = '2026-10-18T00:00:00Z'


def fmt_bytes(n):
    if not n:
        return '?'
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def print_results(label, results):
    print(f'\n{label}: {len(results)} result(s)')
    for i, r in enumerate(results):
        p = r.properties
        size = fmt_bytes(p.get('bytes'))
        print(
            f'  [{i}] {p.get("fileName")}\n'
            f'      start={p.get("startTime")}  '
            f'pol={p.get("polarization")}  '
            f'beamMode={p.get("beamModeType") or p.get("beamMode")}  '
            f'size={size}'
        )


def search_full_scenes():
    return asf.geo_search(
        platform=[asf.PLATFORM.SENTINEL1],
        intersectsWith=AOI_WKT,
        start=START,
        end=END,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=[asf.BEAMMODE.IW],
        maxResults=10,
    )


def search_bursts():
    return asf.geo_search(
        platform=[asf.PLATFORM.SENTINEL1],
        intersectsWith=AOI_WKT,
        start=START,
        end=END,
        dataset=asf.DATASET.SLC_BURST,
        maxResults=10,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--download', type=int, default=None, help='index of a burst result to download (prompts for Earthdata login)')
    args = ap.parse_args()

    full_scenes = search_full_scenes()
    print_results('Full SLC scenes', full_scenes)

    bursts = search_bursts()
    print_results('SLC bursts (same AOI, much smaller files)', bursts)

    if args.download is not None:
        if not bursts:
            print('\nNo burst results to download.')
            return
        target = bursts[args.download]
        print(f'\nDownloading {target.properties.get("fileName")} '
              f'({fmt_bytes(target.properties.get("bytes"))}) ...')
        import getpass
        username = input('Earthdata username: ')
        password = getpass.getpass('Earthdata password: ')
        session = asf.ASFSession().auth_with_creds(username, password)
        target.download(path='.', session=session)
        print('Done.')


if __name__ == '__main__':
    main()