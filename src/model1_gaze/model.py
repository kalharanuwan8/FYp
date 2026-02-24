# model1_gaze Architecture
from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import mobilenet_v2, MobileNet_V2_Weights


def build_model(num_classes: int = 4, pretrained: bool = True) -> nn.Module:
    if pretrained:
        m = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT)
    else:
        m = mobilenet_v2(weights=None)

    # Replace classifier
    in_features = m.classifier[1].in_features
    m.classifier[1] = nn.Linear(in_features, num_classes)
    return m


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor) -> torch.Tensor:
    model.eval()
    logits = model(x)
    return torch.softmax(logits, dim=1)
