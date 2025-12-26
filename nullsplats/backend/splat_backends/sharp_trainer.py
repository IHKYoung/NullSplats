"""SHARP backend for the unified trainer interface."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import torch
import torch.nn.functional as F

from nullsplats.backend.colmap_io import ColmapImage
from nullsplats.backend.splat_backends.types import TrainerCapabilities, TrainingInput, TrainingOutput
from nullsplats.util.tooling_paths import app_root


class SharpTrainer:
    name = "sharp"
    capabilities = TrainerCapabilities(
        live_preview=False,
        supports_unconstrained=True,
        supports_constrained=False,
        requires_colmap=False,
    )

    def prepare(self, inputs: TrainingInput, config: dict[str, Any]) -> None:
        _ = inputs
        _validate_config(config)
        _ensure_sharp_available()

    def train(self, inputs: TrainingInput, config: dict[str, Any], **_: Any) -> TrainingOutput:
        cfg = _normalize_config(config)
        _validate_config(cfg)
        _ensure_sharp_available()

        device = _resolve_device(cfg.get("device", "default"))
        _cleanup_torch(device)

        image_path = _select_image(inputs, cfg)
        image, f_px = _load_image_and_focal(inputs, image_path, cfg)
        height, width = image.shape[:2]

        predictor = _load_predictor(cfg, device)
        gaussians = _predict_image(predictor, image, f_px, device)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%SZ")
        output_name = f"splat_{SharpTrainer.name}_{timestamp}.ply"
        output_path = inputs.scene_paths.splats_dir / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        _save_ply(gaussians, f_px, (height, width), output_path)
        _cleanup_torch(device)

        return TrainingOutput(
            primary_path=output_path,
            method=self.name,
            timestamp=timestamp,
            export_format="ply",
            metrics={},
            extra_files=[],
        )


def _ensure_sharp_available() -> None:
    try:
        import sharp  # noqa: F401
        return
    except Exception:
        pass
    sharp_src = app_root() / "tools" / "sharp" / "src"
    if sharp_src.exists():
        sys.path.insert(0, str(sharp_src))
    try:
        import sharp  # noqa: F401
    except Exception as exc:
        raise ImportError(
            "SHARP is not available. Clone https://github.com/apple/ml-sharp into tools/sharp "
            "and install its requirements, or install the sharp package in the active environment."
        ) from exc


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise TypeError(f"SHARP config must be a dict, got {type(config)}")
    normalized = dict(config)
    normalized.setdefault("device", "default")
    normalized.setdefault("intrinsics_source", "colmap")
    normalized.setdefault("image_index", 0)
    return normalized


def _validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise TypeError(f"SHARP config must be a dict, got {type(config)}")
    source = str(config.get("intrinsics_source", "colmap")).strip().lower()
    if source not in {"colmap", "exif", "manual"}:
        raise ValueError("SHARP intrinsics_source must be one of: colmap, exif, manual")
    if "image_index" in config and config["image_index"] is not None:
        if int(config["image_index"]) < 0:
            raise ValueError("SHARP image_index must be >= 0")


def _resolve_device(device: str) -> torch.device:
    raw = str(device or "default").strip().lower()
    if raw in {"default", ""}:
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch, "mps") and torch.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if raw.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested for SHARP but CUDA is not available.")
        try:
            torch.cuda.set_device(raw)
        except Exception:
            pass
    if raw == "mps":
        if not hasattr(torch, "mps") or not torch.mps.is_available():
            raise RuntimeError("MPS requested for SHARP but MPS is not available.")
    return torch.device(raw)


def _cleanup_torch(device: torch.device) -> None:
    try:
        torch.set_grad_enabled(False)
    except Exception:
        pass
    if device.type == "cuda" and torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception:
            pass


def _select_image(inputs: TrainingInput, config: dict[str, Any]) -> Path:
    name = str(config.get("image_name") or "").strip()
    if name:
        for path in inputs.images:
            if path.name == name or str(path) == name:
                return path
        raise FileNotFoundError(f"SHARP image_name {name} not found in selected frames.")
    idx = int(config.get("image_index", 0) or 0)
    if idx >= len(inputs.images):
        raise IndexError(f"SHARP image_index {idx} out of range for {len(inputs.images)} frames.")
    return inputs.images[idx]


def _load_image_and_focal(
    inputs: TrainingInput,
    image_path: Path,
    config: dict[str, Any],
) -> tuple[Any, float]:
    from sharp.utils import io as sharp_io

    image, _icc, f_px_exif = sharp_io.load_rgb(image_path)
    source = str(config.get("intrinsics_source", "colmap")).strip().lower()
    if source == "exif":
        return image, float(f_px_exif)
    if source == "manual":
        f_px = _resolve_manual_focal(image.shape, config)
        return image, f_px
    if inputs.colmap is None:
        raise ValueError("SHARP intrinsics_source=colmap requires COLMAP outputs. Use EXIF or manual instead.")
    f_px = _resolve_colmap_focal(inputs, image_path, config)
    return image, f_px


def _resolve_manual_focal(image_shape: tuple[int, int, int], config: dict[str, Any]) -> float:
    height, width = image_shape[0], image_shape[1]
    focal_px = config.get("focal_px_override")
    fx_fy_override = config.get("fx_fy_override")
    if fx_fy_override:
        try:
            fx, fy = fx_fy_override
            focal_px = (float(fx) + float(fy)) * 0.5
        except Exception:
            focal_px = float(fx_fy_override)
    if focal_px:
        return float(focal_px)
    fov_deg = float(config.get("fov_override_deg") or 0.0)
    if fov_deg > 0.0:
        return 0.5 * width / math.tan(0.5 * math.radians(fov_deg))
    raise ValueError("SHARP manual intrinsics require focal_px_override, fx_fy_override, or fov_override_deg")


def _resolve_colmap_focal(inputs: TrainingInput, image_path: Path, config: dict[str, Any]) -> float:
    focal_px = config.get("focal_px_override")
    if focal_px:
        return float(focal_px)
    entry = _match_colmap_entry(inputs, image_path)
    camera = inputs.colmap.cameras[entry.camera_id]
    fx, fy, _cx, _cy = camera.params
    return float((fx + fy) * 0.5)


def _match_colmap_entry(inputs: TrainingInput, image_path: Path) -> ColmapImage:
    images_by_name = {entry.name: entry for entry in inputs.colmap.images.values()}
    images_by_basename = {Path(entry.name).name: entry for entry in inputs.colmap.images.values()}
    entry = images_by_name.get(image_path.name) or images_by_basename.get(image_path.name)
    if entry is None:
        raise FileNotFoundError(f"COLMAP image entry not found for {image_path.name}")
    return entry


def _load_predictor(config: dict[str, Any], device: torch.device) -> Any:
    from sharp.models import PredictorParams, create_predictor

    state_dict = _load_state_dict(config)
    predictor = create_predictor(PredictorParams())
    predictor.load_state_dict(state_dict)
    predictor.eval()
    predictor.to(device)
    return predictor


def _load_state_dict(config: dict[str, Any]) -> dict[str, Any]:
    checkpoint_path = config.get("checkpoint_path") or config.get("weights_path")
    if checkpoint_path:
        path = Path(checkpoint_path)
        if not path.exists():
            raise FileNotFoundError(f"SHARP checkpoint not found: {path}")
        try:
            return torch.load(path, weights_only=True, map_location="cpu")
        except TypeError:
            return torch.load(path, map_location="cpu")
    default_url = "https://ml-site.cdn-apple.com/models/sharp/sharp_2572gikvuh.pt"
    cache_path = _default_sharp_checkpoint_path()
    if cache_path.exists():
        return torch.load(cache_path, map_location="cpu")
    try:
        return torch.hub.load_state_dict_from_url(default_url, progress=True)
    except Exception:
        _download_with_powershell(default_url, cache_path)
        return torch.load(cache_path, map_location="cpu")


def _default_sharp_checkpoint_path() -> Path:
    return app_root() / "cache" / "models" / "sharp" / "sharp_2572gikvuh.pt"


def _download_with_powershell(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = f"Invoke-WebRequest -Uri \"{url}\" -OutFile \"{dest}\""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to start PowerShell to download SHARP checkpoint: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"PowerShell download failed for SHARP checkpoint: {stderr or 'unknown error'}")


@torch.no_grad()
def _predict_image(predictor: Any, image: Any, f_px: float, device: torch.device) -> Any:
    from sharp.utils.gaussians import unproject_gaussians

    internal_shape = (1536, 1536)
    image_pt = torch.from_numpy(image.copy()).float().to(device).permute(2, 0, 1) / 255.0
    _, height, width = image_pt.shape
    disparity_factor = torch.tensor([f_px / width], dtype=torch.float32, device=device)

    image_resized_pt = F.interpolate(
        image_pt[None],
        size=(internal_shape[1], internal_shape[0]),
        mode="bilinear",
        align_corners=True,
    )

    gaussians_ndc = predictor(image_resized_pt, disparity_factor)

    intrinsics = torch.tensor(
        [
            [f_px, 0.0, width / 2.0, 0.0],
            [0.0, f_px, height / 2.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        device=device,
        dtype=torch.float32,
    )
    intrinsics_resized = intrinsics.clone()
    intrinsics_resized[0] *= internal_shape[0] / width
    intrinsics_resized[1] *= internal_shape[1] / height

    gaussians = unproject_gaussians(
        gaussians_ndc, torch.eye(4, device=device), intrinsics_resized, internal_shape
    )
    return gaussians


def _save_ply(gaussians: Any, f_px: float, image_shape: tuple[int, int], output_path: Path) -> None:
    from sharp.utils.gaussians import save_ply

    save_ply(gaussians, f_px, image_shape, output_path)
