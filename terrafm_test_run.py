from terrafm import terrafm_base
import torch


x = torch.randn(1, 12, 224, 224)
model = terrafm_base()
state_dict = torch.load('TerraFM-B.pth', map_location='cpu')
msg = model.load_state_dict(state_dict, strict=False)
print(msg)
y = model(x)
print(f'Output shape: {y.shape}')