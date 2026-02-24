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
    img_size: int = 224


def build_transforms(img_size: int, train: bool) -> T.Compose:
    # images are grayscale; we'll convert to RGB so we can use ImageNet-pretrained models cleanly
    if train:
        return T.Compose([
            T.Resize((img_size, img_size)),
            T.RandomHorizontalFlip(p=0.5),
            T.RandomRotation(degrees=5),
            T.ColorJitter(brightness=0.2, contrast=0.2),
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

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        row = self.df.iloc[idx]
        img_path = row["img_path"]
        label_name = row["label_name"]

        y = torch.tensor(LABEL4[label_name], dtype=torch.long)

        img = Image.open(img_path).convert("L")  # grayscale
        x = self.tf(img)

        return x, y
