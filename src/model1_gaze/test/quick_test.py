# Quick test script to verify training works with smaller dataset
from __future__ import annotations

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm

from src.model1_gaze.dataset import MPIIGaze4Class, GazeDataConfig
from src.model1_gaze.model import build_model


def quick_test():
    """Test training on just 100 samples to verify everything works"""
    cfg = GazeDataConfig()
    
    # Load full dataset
    train_ds = MPIIGaze4Class(cfg.train_csv, img_size=cfg.img_size, train=True)
    
    # Only use first 100 samples for quick test
    subset_indices = list(range(min(100, len(train_ds))))
    train_subset = Subset(train_ds, subset_indices)
    
    # Small batch size for testing
    train_loader = DataLoader(
        train_subset, 
        batch_size=8, 
        shuffle=False,
        num_workers=0
    )
    
    device = "cpu"
    model = build_model(num_classes=4, pretrained=False).to(device)
    
    # Simple loss and optimizer
    loss_fn = nn.CrossEntropyLoss()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    print(f"Testing with {len(train_subset)} samples...")
    print(f"Number of batches: {len(train_loader)}")
    print(f"Device: {device}")
    print("-" * 50)
    
    model.train()
    losses = []
    
    pbar = tqdm(train_loader, desc="Quick Test")
    for batch_idx, (x, y) in enumerate(pbar):
        x = x.to(device)
        y = y.to(device)
        
        opt.zero_grad()
        logits = model(x)
        loss = loss_fn(logits, y)
        loss.backward()
        opt.step()
        
        current_loss = float(loss.item())
        losses.append(current_loss)
        
        pbar.set_postfix({
            "batch": f"{batch_idx+1}/{len(train_loader)}", 
            "loss": f"{current_loss:.4f}"
        })
    
    avg_loss = sum(losses) / len(losses)
    print("-" * 50)
    print(f"✓ Quick test completed successfully!")
    print(f"✓ Average loss: {avg_loss:.4f}")
    print(f"✓ All {len(train_loader)} batches processed without errors")
    print("\nYour training setup is working correctly.")
    print("You can now run the full training with: python -m src.model1_gaze.train")


if __name__ == "__main__":
    quick_test()
