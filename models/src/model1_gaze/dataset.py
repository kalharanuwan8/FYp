# model1_gaze Dataset class
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms as T


# 4-class mapping (Choice A)
LABEL4: Dict[str, int] = {
    "center": 0,
    "left": 1,
    "right": 2,
    "down": 3,
}


class GrayToRGB:
    """Convert a 1-channel tensor to 3-channel by repeating.
    Picklable replacement for T.Lambda(lambda x: x.repeat(3,1,1) ...).
    """
    def __call__(self, x: torch.Tensor) -> torch.Tensor:
        return x.repeat(3, 1, 1) if x.shape[0] == 1 else x

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


@dataclass(frozen=True)
class GazeDataConfig:
    train_csv: Path = Path("data/processed/model1_gaze/train.csv")
    val_csv: Path = Path("data/processed/model1_gaze/val.csv")
    test_csv: Path = Path("data/processed/model1_gaze/test.csv")
    num_classes: int = 4
    # Native patches are 60x36. 224px made the GPU step ~1.7 s/batch
    # (~25 min/epoch); the deployed checkpoint (epoch 15 retrain) uses
    # 96px and is stored with img_size=96. Backend reads img_size from
    # the checkpoint; this default must match the deployed checkpoint.
    img_size: int = 96


def build_transforms(img_size: int, train: bool) -> T.Compose:
    # images are grayscale; we'll convert to RGB so we can use ImageNet-pretrained models cleanly
    if train:
        # Augment at native 60x36 first: rotation/jitter on the upscaled
        # 224x224 image costs ~27x more CPU and was the loader bottleneck.
        return T.Compose([
            T.RandomRotation(degrees=5),
            T.ColorJitter(brightness=0.2, contrast=0.2),
            T.Resize((img_size, img_size)),
            T.ToTensor(),
            GrayToRGB(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    else:
        return T.Compose([
            T.Resize((img_size, img_size)),
            T.ToTensor(),
            GrayToRGB(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])


class MPIIGaze4Class(Dataset):
    """
    Reads train/val/test.csv produced by prepare.py.
    Uses only label_name in {center,left,right,down}.
    """
    def __init__(self, csv_path: Path, img_size: int = 224, train: bool = True):
        self.csv_path = Path(csv_path)
        assert self.csv_path.exists(), f"Missing CSV: {self.csv_path}"

        df = pd.read_csv(self.csv_path)

        # Keep only 4 classes (defensive filtering)
        df = df[df["label_name"].isin(LABEL4.keys())].reset_index(drop=True)
        if len(df) == 0:
            raise RuntimeError(f"No usable rows after filtering labels in {self.csv_path}")

        self.df = df
        self.tf = build_transforms(img_size, train)

        # Optional packed image cache (see scripts/build_gaze_image_cache.py).
        # <csv_stem>_images.npy next to the CSV, row-aligned with the CSV.
        cache = self.csv_path.with_name(f"{self.csv_path.stem}_images.npy")
        self.images = None
        if cache.exists():
            import numpy as np
            self.images = np.load(cache, mmap_mode="r")
            assert len(self.images) == len(self.df), f"Cache/CSV size mismatch: {cache}"

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        row = self.df.iloc[idx]
        label_name = row["label_name"]

        y = torch.tensor(LABEL4[label_name], dtype=torch.long)

        if self.images is not None:
            img = Image.fromarray(self.images[idx], mode="L")
        else:
            img = Image.open(row["img_path"]).convert("L")  # grayscale
        x = self.tf(img)

        return x, y
