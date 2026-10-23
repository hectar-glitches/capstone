import sys, numpy as np, rasterio
from rasterio.windows import Window
from cfar import cfar_detect, cluster_detections
size, row = 1024, 240
with rasterio.open(sys.argv[1]) as src:
    print(f'{"col":>7} {"CV":>6} {"meandB":>8} {"zeros":>7} {"CFAR":>5}')
    for col in range(0, src.width - size, size):
        a = src.read(1, window=Window(col, row, size, size)).astype(np.complex64)
        I = np.abs(a)**2
        if I.mean() == 0:
            continue
        det, _ = cfar_detect(np.abs(a), guard=2, train=8, threshold_db=13.0)
        n = len(cluster_detections(det))
        print(f'{col:>7} {I.std()/I.mean():>6.2f} {10*np.log10(I.mean()):>8.1f} {(I==0).mean():>6.1%} {n:>5}')
