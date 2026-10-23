import numpy as np
from PIL import Image
c = np.load('chip.npy')
I = np.abs(c)**2
db = 10*np.log10(I + 1e-12)
cv = I.std()/I.mean()
bright = (db > db.mean() + 15).sum()
print(f'CV(intensity) = {cv:.2f}   bright pixels (>mean+15dB): {bright}')
lo, hi = np.percentile(db, [5, 99])
img = np.clip((db-lo)/(hi-lo), 0, 1)
Image.fromarray((img*255).astype('uint8')).save('chip.png')
