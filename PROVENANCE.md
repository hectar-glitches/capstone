# Data provenance

## Source scene

Sentinel-1 IW burst, subswath IW3, 30 September 2026, over the Savannah
approach channel and anchorage.

AOI used for the ASF search:

    POLYGON((-80.95 31.85,-80.6 31.85,-80.6 32.05,-80.95 32.05,-80.95 31.85))

Downloaded from ASF Vertex (search.asf.alaska.edu) as an SLC burst product.
Local filename: `S1 IW3 2026-09-30 Burst.tiff`
Full burst: 24568 x 1507, dtype complex_int16, 1 band.

The burst file is not in this repo (too large). Re-download from ASF using
the AOI and date above.

## Chips

Tile positions were chosen with `survey.py`, which scores each 1024-wide
position by coefficient of variation of intensity, mean brightness, and raw
CFAR detection count. Open water sits near CV 1.0. Land is bright with high
CV. Water containing point targets is dark with high CV.

| file | contents | col | row | size | CV | mean dB | raw detections |
|---|---|---|---|---|---|---|---|
| `chip.npy` | empty open water | 21504 | 240 | 1024 | 1.04 | 23.1 | 0 |
| `chip_ships.npy` | open water with targets | 22528 | 240 | 1024 | 8.97 | 24.2 | 16 |

`chip_ships.npy` is the chip behind the current results.

Regenerate either with:

    python3 extract_chip.py "<burst>.tiff" chip_ships.npy \
        --col-offset 22528 --row-offset 240 --size 1024

## Note

Chips are gitignored (`*.npy`) but their compressed outputs are tracked.
This file is what makes the chips reproducible from the source scene.
