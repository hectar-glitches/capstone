import sys, numpy as np
from fdbaq import load_fdbaq_reconstruction
from cfar import cfar_detect, cluster_detections

raw = np.load(sys.argv[1])
rec = load_fdbaq_reconstruction(sys.argv[2])
def det(x):
    d, _ = cfar_detect(np.abs(x), 2, 8, 13.0)
    return cluster_detections(d)
r, f = det(raw), det(rec)
hit = sum(1 for a in r if any(np.hypot(a[0]-b[0], a[1]-b[1]) <= 5 for b in f))
fa  = sum(1 for b in f if not any(np.hypot(a[0]-b[0], a[1]-b[1]) <= 5 for a in r))
print(f'raw {len(r)}   fdbaq {len(f)}   recall {hit}/{len(r)} ({hit/max(len(r),1):.0%})   false alarms {fa}')
