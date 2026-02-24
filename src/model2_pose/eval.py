# model2_pose Evaluation loop
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from PIL import Image
from torchvision import transforms, models

class PoseDataset(Dataset):
    def __init__(self, csv_path, img_size=224):
        self.df = pd.read_csv(csv_path)
        self.tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
        ])
    def __len__(self): return len(self.df)
    def __getitem__(self, i):
        r = self.df.iloc[i]
        x = self.tf(Image.open(r["img_path"]).convert("RGB"))
        y = torch.tensor([r["yaw_deg"], r["pitch_deg"], r["roll_deg"]], dtype=torch.float32)
        return x, y

def build_model():
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, 3)
    return m

@torch.no_grad()
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = Path("outputs/checkpoints/model2_pose/best.pt")
    data_root = Path("data/processed/model2_pose")
    test_csv = data_root / "test.csv"

    ds = PoseDataset(test_csv)
    dl = DataLoader(ds, batch_size=256, shuffle=False, num_workers=0)

    m = build_model().to(device)
    state = torch.load(ckpt, map_location=device, weights_only=False)["model"]
    # Strip "net." prefix from checkpoint keys if present
    state = {k.replace("net.", ""): v for k, v in state.items()}
    m.load_state_dict(state)
    m.eval()

    mae = torch.zeros(3, device=device)
    n = 0
    for x,y in dl:
        x,y = x.to(device), y.to(device)
        p = m(x)
        mae += (p-y).abs().sum(dim=0)
        n += x.size(0)

    mae = (mae / n).cpu().numpy()
    print(f"TEST MAE (deg): yaw={mae[0]:.2f}, pitch={mae[1]:.2f}, roll={mae[2]:.2f}")

if __name__ == "__main__":
    main()
