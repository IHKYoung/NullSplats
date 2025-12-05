"""Utility modules adapted from gsplat examples (non-viewer helpers).

Copied into the repo to avoid importing from tools/gsplat_examples at runtime.
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from torch import Tensor


class CameraOptModule(torch.nn.Module):
    """Camera pose optimization module using 6D rotations."""

    def __init__(self, n: int):
        super().__init__()
        self.embeds = torch.nn.Embedding(n, 9)
        self.register_buffer("identity", torch.tensor([1.0, 0.0, 0.0, 0.0, 1.0, 0.0]))

    def zero_init(self) -> None:
        torch.nn.init.zeros_(self.embeds.weight)

    def random_init(self, std: float) -> None:
        torch.nn.init.normal_(self.embeds.weight, std=std)

    def forward(self, camtoworlds: Tensor, embed_ids: Tensor) -> Tensor:
        assert camtoworlds.shape[:-2] == embed_ids.shape
        batch_dims = camtoworlds.shape[:-2]
        pose_deltas = self.embeds(embed_ids)
        dx, drot = pose_deltas[..., :3], pose_deltas[..., 3:]
        rot = rotation_6d_to_matrix(drot + self.identity.expand(*batch_dims, -1))
        transform = torch.eye(4, device=pose_deltas.device).repeat((*batch_dims, 1, 1))
        transform[..., :3, :3] = rot
        transform[..., :3, 3] = dx
        return torch.matmul(camtoworlds, transform)


class AppearanceOptModule(torch.nn.Module):
    """View-dependent appearance adjustment."""

    def __init__(
        self,
        n: int,
        feature_dim: int,
        embed_dim: int = 16,
        sh_degree: int = 3,
        mlp_width: int = 64,
        mlp_depth: int = 2,
    ):
        super().__init__()
        self.embed_dim = embed_dim
        self.sh_degree = sh_degree
        self.embeds = torch.nn.Embedding(n, embed_dim)
        layers = [
            torch.nn.Linear(embed_dim + feature_dim + (sh_degree + 1) ** 2, mlp_width),
            torch.nn.ReLU(inplace=True),
        ]
        for _ in range(mlp_depth - 1):
            layers.append(torch.nn.Linear(mlp_width, mlp_width))
            layers.append(torch.nn.ReLU(inplace=True))
        layers.append(torch.nn.Linear(mlp_width, 3))
        self.color_head = torch.nn.Sequential(*layers)

    def forward(self, features: Tensor, embed_ids: Tensor, dirs: Tensor, sh_degree: int) -> Tensor:
        from gsplat.cuda._torch_impl import _eval_sh_bases_fast

        C, N = dirs.shape[:2]
        if embed_ids is None:
            embeds = torch.zeros(C, self.embed_dim, device=features.device)
        else:
            embeds = self.embeds(embed_ids)
        embeds = embeds[:, None, :].expand(-1, N, -1)
        features = features[None, :, :].expand(C, -1, -1)
        dirs = F.normalize(dirs, dim=-1)
        num_bases_to_use = (sh_degree + 1) ** 2
        num_bases = (self.sh_degree + 1) ** 2
        sh_bases = torch.zeros(C, N, num_bases, device=features.device)
        sh_bases[:, :, :num_bases_to_use] = _eval_sh_bases_fast(num_bases_to_use, dirs)
        h = torch.cat([embeds, features, sh_bases], dim=-1) if self.embed_dim > 0 else torch.cat([features, sh_bases], dim=-1)
        return self.color_head(h)


def rotation_6d_to_matrix(d6: Tensor) -> Tensor:
    a1, a2 = d6[..., :3], d6[..., 3:]
    b1 = F.normalize(a1, dim=-1)
    b2 = a2 - (b1 * a2).sum(-1, keepdim=True) * b1
    b2 = F.normalize(b2, dim=-1)
    b3 = torch.cross(b1, b2, dim=-1)
    return torch.stack((b1, b2, b3), dim=-2)


def rgb_to_sh(rgb: Tensor) -> Tensor:
    C0 = 0.28209479177387814
    return (rgb - 0.5) / C0


def set_random_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


__all__ = ["CameraOptModule", "AppearanceOptModule", "rotation_6d_to_matrix", "rgb_to_sh", "set_random_seed"]
