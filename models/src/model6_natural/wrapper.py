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


def platt_apply_logits(z: np.ndarray, a: float, b: float) -> np.ndarray:
    """Platt scaling on logits: sigmoid(a*z + b)."""
    z = np.clip(np.asarray(z, dtype=np.float64), -13.8, 13.8)
    return 1.0 / (1.0 + np.exp(-(a * z + b)))


class PlattCalibratedProba:
    """Wrap a sklearn-like classifier with 1-D Platt calibration (picklable)."""

    def __init__(self, base, a: float, b: float):
        self.base = base
        self.a = float(a)
        self.b = float(b)

    def __setstate__(self, state):
        # Older pickles may omit fields; fill defaults then overlay.
        self.base = None
        self.a = 1.0
        self.b = 0.0
        if isinstance(state, dict):
            self.__dict__.update(state)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        base = getattr(self, "base", None)
        if base is None:
            raise RuntimeError("PlattCalibratedProba missing base estimator")
        a = float(getattr(self, "a", 1.0))
        b = float(getattr(self, "b", 0.0))
        p = np.clip(np.asarray(base.predict_proba(X))[:, 1], 1e-6, 1 - 1e-6)
        p1 = platt_apply_logits(np.log(p / (1.0 - p)), a, b)
        return np.stack([1.0 - p1, p1], axis=1)


class Model6SklearnWrapper:
    """predict_proba interface for ml_service."""

    def __init__(self, pack: dict):
        self.features: List[str] = list(pack["features"])
        self.threshold = float(pack["threshold"])
        self.scaler_mean = np.array(pack["scaler_mean"], dtype=np.float32)
        self.scaler_scale = np.array(pack["scaler_scale"], dtype=np.float32)
        self.hidden = int(pack.get("hidden", 64))
        self._state = pack["state_dict"]
        cal = pack.get("calibration") or None
        self._cal = (float(cal["a"]), float(cal["b"])) if cal else None
        self._model: Optional[FusionMLP] = None
        self._device = torch.device("cpu")

    def __setstate__(self, state):
        """Unpickle-safe defaults for attributes added after older packs."""
        self.features = []
        self.threshold = 0.5
        self.scaler_mean = np.zeros(1, dtype=np.float32)
        self.scaler_scale = np.ones(1, dtype=np.float32)
        self.hidden = 64
        self._state = {}
        self._cal = None
        self._model = None
        self._device = torch.device("cpu")
        if isinstance(state, dict):
            self.__dict__.update(state)
        # Ensure post-pickle attributes always exist (joblib skips __init__).
        if not hasattr(self, "_cal"):
            self._cal = None
        if not hasattr(self, "_model"):
            self._model = None
        if not hasattr(self, "_device"):
            self._device = torch.device("cpu")
        if not hasattr(self, "hidden"):
            self.hidden = 64

    def _ensure(self):
        if getattr(self, "_model", None) is not None:
            return
        if not hasattr(self, "_device") or self._device is None:
            self._device = torch.device("cpu")
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        hidden = int(getattr(self, "hidden", 64) or 64)
        self._model = FusionMLP(n_in=len(self.features), hidden=hidden).to(self._device)
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
            cal = getattr(self, "_cal", None)
            if cal is not None:
                z = logits.float().cpu().numpy().astype(np.float64).reshape(-1)
                p1 = platt_apply_logits(z, *cal).astype(np.float32)
            else:
                p1 = torch.sigmoid(logits.float()).cpu().numpy().reshape(-1)
        p0 = 1.0 - p1
        return np.stack([p0, p1], axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)[:, 1]
        return (proba >= self.threshold).astype(int)
