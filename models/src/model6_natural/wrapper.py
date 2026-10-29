"""Sklearn-like predict_proba wrapper around the model6 MLP (safe to joblib)."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import torch
import torch.nn as nn


class FusionMLP(nn.Module):
    def __init__(self, n_in: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class Model6SklearnWrapper:
    """predict_proba interface for ml_service."""

    def __init__(self, pack: dict):
        self.features: List[str] = list(pack["features"])
        self.threshold = float(pack["threshold"])
        self.scaler_mean = np.array(pack["scaler_mean"], dtype=np.float32)
        self.scaler_scale = np.array(pack["scaler_scale"], dtype=np.float32)
        self.hidden = int(pack.get("hidden", 64))
        self._state = pack["state_dict"]
        self._model: Optional[FusionMLP] = None
        self._device = torch.device("cpu")

    def _ensure(self):
        if self._model is not None:
            return
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = FusionMLP(n_in=len(self.features), hidden=self.hidden).to(self._device)
        # state_dict values may be tensors
        sd = {
            k: (v.cpu() if hasattr(v, "cpu") else torch.as_tensor(v))
            for k, v in self._state.items()
        }
        self._model.load_state_dict(sd)
        self._model.eval()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        self._ensure()
        X = np.asarray(X, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        Xs = (X - self.scaler_mean) / np.maximum(self.scaler_scale, 1e-8)
        with torch.no_grad():
            t = torch.from_numpy(Xs).to(self._device)
            logits = self._model(t)
            p1 = torch.sigmoid(logits.float()).cpu().numpy().reshape(-1)
        p0 = 1.0 - p1
        return np.stack([p0, p1], axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)[:, 1]
        return (proba >= self.threshold).astype(int)
