import hashlib
import json
import math

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

import folder_paths
from nodes import LoadImage


def _image(value, name):
    if not isinstance(value, torch.Tensor) or value.ndim != 4 or value.shape[0] != 1 or value.shape[-1] not in (3, 4):
        raise ValueError(f"{name} must be a single RGB or RGBA IMAGE [1,H,W,C]")
    if value.shape[1] < 1 or value.shape[2] < 1 or not torch.isfinite(value).all():
        raise ValueError(f"{name} must have non-empty spatial dimensions and finite values")
    return value


def _mask(value, name, height, width):
    if not isinstance(value, torch.Tensor) or value.ndim != 3 or value.shape[0] != 1 or tuple(value.shape[1:]) != (height, width):
        raise ValueError(f"{name} must be MASK [1,H,W] matching the image")
    if not torch.isfinite(value).all() or torch.any(value < 0) or torch.any(value > 1):
        raise ValueError(f"{name} values must be finite and in [0,1]")
    return value


def _digest(image):
    return hashlib.sha256(image.detach().contiguous().cpu().numpy().tobytes()).hexdigest()


class VallpaperPrepareRevision:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",), "edit_mask": ("MASK",),
            "context_padding": ("INT", {"default": 96, "min": 0, "max": 2048}),
            "feather": ("INT", {"default": 12, "min": 0, "max": 128}),
        }, "optional": {
            "protect_mask": ("MASK",),
            "max_megapixels": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 8.0, "step": 0.25}),
            "mask_grow": ("INT", {"default": 12, "min": 0, "max": 256}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK", "SHOT_REVISION_CONTEXT", "INT", "INT")
    RETURN_NAMES = ("crop_image", "crop_mask", "revision_context", "width", "height")
    FUNCTION = "prepare"
    CATEGORY = "dharani.prod/Shot Revision"

    def prepare(self, image, edit_mask, context_padding=96, feather=12, protect_mask=None, max_megapixels=1.0, mask_grow=12):
        image = _image(image, "image")
        h, w = image.shape[1:3]
        edit = _mask(edit_mask, "edit_mask", h, w).to(device=image.device, dtype=image.dtype)
        protect = torch.zeros_like(edit) if protect_mask is None else _mask(protect_mask, "protect_mask", h, w).to(device=image.device, dtype=image.dtype)
        grow = int(mask_grow)
        if grow:
            edit = F.max_pool2d(edit.unsqueeze(1), (1, 2 * grow + 1), stride=1, padding=(0, grow))
            edit = F.max_pool2d(edit, (2 * grow + 1, 1), stride=1, padding=(grow, 0)).squeeze(1)
        allowed = edit * (1 - protect)
        ys, xs = torch.where(edit[0] > 0)
        if xs.numel() == 0:
            raise ValueError("edit_mask has no painted pixels")
        pad = int(context_padding)
        left, top = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
        right, bottom = min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad)
        ch, cw = bottom - top, right - left
        budget = float(max_megapixels) * 1_000_000
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("max_megapixels must be a finite positive number")
        scale = min(1.0, math.sqrt(budget / (ch * cw)))
        out_h, out_w = max(64, int(ch * scale) // 16 * 16), max(64, int(cw * scale) // 16 * 16)
        crop = image[:, top:bottom, left:right, :3].permute(0, 3, 1, 2)
        crop = F.interpolate(crop, size=(out_h, out_w), mode="bilinear", align_corners=False, antialias=True).permute(0, 2, 3, 1)
        mask_crop = F.interpolate(allowed[:, top:bottom, left:right].unsqueeze(1), size=(out_h, out_w), mode="bilinear", align_corners=False).squeeze(1)
        context = {
            "allowed": allowed.clone(), "protect": protect.clone(),
            "rect": (left, top, right, bottom), "padded_size": (out_h, out_w),
            "resized_crop": True,
            "feather": int(feather), "sha256": _digest(image), "geometry": tuple(image.shape),
        }
        return (crop, mask_crop, context, out_w, out_h)


class VallpaperApplyRevision:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"original": ("IMAGE",), "revised_crop": ("IMAGE",), "revision_context": ("SHOT_REVISION_CONTEXT",)}}

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("revised_image", "applied_mask")
    FUNCTION = "apply"
    CATEGORY = "dharani.prod/Shot Revision"

    def apply(self, original, revised_crop, revision_context):
        original = _image(original, "original")
        if tuple(original.shape) != revision_context["geometry"] or _digest(original) != revision_context["sha256"]:
            raise ValueError("original image geometry or bytes changed after revision preparation")
        revised_crop = _image(revised_crop, "revised_crop")
        out_h, out_w = revision_context["padded_size"]
        if tuple(revised_crop.shape[1:3]) != (out_h, out_w):
            raise ValueError(f"revised_crop must match prepared padded dimensions {(out_h, out_w)}")
        left, top, right, bottom = revision_context["rect"]
        h, w = bottom - top, right - left
        device, dtype = original.device, original.dtype
        revised = revised_crop.to(device=device, dtype=dtype)
        if revision_context.get("resized_crop"):
            revised = F.interpolate(revised[..., :3].permute(0, 3, 1, 2), size=(h, w), mode="bilinear", align_corners=False, antialias=True).permute(0, 2, 3, 1)
        else:
            revised = revised[:, :h, :w, :3]
        alpha = revision_context["allowed"]
        feather = revision_context["feather"]
        if feather:
            smooth = F.avg_pool2d(alpha.unsqueeze(1), (1, 2 * feather + 1), stride=1, padding=(0, feather), count_include_pad=False)
            smooth = F.avg_pool2d(smooth, (2 * feather + 1, 1), stride=1, padding=(feather, 0), count_include_pad=False).squeeze(1)
            alpha = torch.minimum(alpha, smooth)
            alpha = alpha * (revision_context["protect"] < 1).to(dtype=alpha.dtype)
        alpha = alpha[:, top:bottom, left:right].to(device=device, dtype=dtype)
        source = original[:, top:bottom, left:right, :3]
        blended = source + (revised - source) * alpha.unsqueeze(-1)
        result = original.clone()
        region = result[:, top:bottom, left:right, :3]
        region.copy_(torch.where(alpha.unsqueeze(-1) > 0, blended, source))
        applied = torch.zeros((1, original.shape[1], original.shape[2]), device=device, dtype=dtype)
        applied[:, top:bottom, left:right] = alpha
        return (result, applied)


class VallpaperShotEditor:
    @classmethod
    def INPUT_TYPES(cls):
        inputs = LoadImage.INPUT_TYPES()
        inputs["required"]["image"] = (inputs["required"]["image"][0], {})
        inputs["required"]["editor_state"] = ("STRING", {"default": "{}", "multiline": True})
        inputs["optional"] = {
            side: ("INT", {"default": 0, "min": 0, "max": 8192, "step": 16})
            for side in ("left", "right", "top", "bottom")
        }
        return inputs

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "edit_mask", "instruction")
    FUNCTION = "load"
    CATEGORY = "dharani.prod/Shot Revision"

    def load(self, image, editor_state="{}", left=0, right=0, top=0, bottom=0):
        state = json.loads(editor_state or "{}")
        if not isinstance(state, dict):
            raise ValueError("Editor state is invalid. Open Shot Editor and save the selection again.")
        loaded, source_mask = LoadImage().load_image(image)
        loaded = _image(loaded, "editor source image")
        h, w = loaded.shape[1:3]
        mask_file = state.get("mask_file")
        if mask_file and state.get("source") != image:
            raise ValueError("The selection belongs to another image. Open Shot Editor to create a new selection.")
        if mask_file:
            path = folder_paths.get_annotated_filepath(mask_file)
            with Image.open(path) as mask_image:
                pixels = np.array(ImageOps.exif_transpose(mask_image).convert("L"), dtype=np.float32) / 255.0
            mask = torch.from_numpy(pixels).unsqueeze(0).to(device=loaded.device, dtype=loaded.dtype)
            mask = _mask(mask, "editor selection", h, w)
        elif tuple(source_mask.shape) == (1, h, w):
            mask = source_mask.to(device=loaded.device, dtype=loaded.dtype)
        else:
            mask = torch.zeros((1, h, w), device=loaded.device, dtype=loaded.dtype)
        expand = dict(left=left, right=right, top=top, bottom=bottom)
        if state.get("version", 1) < 2 and not any(expand.values()):
            expand = state.get("expand", {})
        amounts = []
        for side in ("left", "right", "top", "bottom"):
            amount = expand.get(side, 0)
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise ValueError("Canvas expansion must use non-negative whole pixel values.")
            amounts.append(amount)
        if any(amounts):
            loaded = F.pad(loaded.permute(0, 3, 1, 2), tuple(amounts), mode="replicate").permute(0, 2, 3, 1)
            mask = F.pad(mask, tuple(amounts), mode="constant", value=1)
        instruction = state.get("prompt", "")
        if not isinstance(instruction, str):
            raise ValueError("The saved legacy prompt must be text.")
        if any(amounts):
            instruction += " Extend the scene naturally into the new canvas borders. Continue the existing perspective, lighting and background; keep the original composition intact."
        return loaded, mask, instruction

    @classmethod
    def VALIDATE_INPUTS(cls, image, **kwargs):
        return True if folder_paths.exists_annotated_filepath(image) else "Source image not found. Upload it in Shot Editor."

    @classmethod
    def IS_CHANGED(cls, image, editor_state="{}", **kwargs):
        state = json.loads(editor_state or "{}")
        digest = hashlib.sha256(editor_state.encode())
        for name in (image, state.get("mask_file")):
            if name:
                with open(folder_paths.get_annotated_filepath(name), "rb") as asset:
                    digest.update(asset.read())
        return digest.hexdigest()


class VallpaperRevisionDifference:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"original": ("IMAGE",), "revised": ("IMAGE",), "allowed_mask": ("MASK",)}}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("difference_heatmap", "summary")
    FUNCTION = "difference"
    CATEGORY = "dharani.prod/Shot Revision"

    def difference(self, original, revised, allowed_mask):
        original = _image(original, "original")
        revised = _image(revised, "revised")
        if tuple(original.shape) != tuple(revised.shape):
            raise ValueError("original and revised must have matching single-image dimensions and channels")
        h, w = original.shape[1:3]
        allowed = _mask(allowed_mask, "allowed_mask", h, w).to(device=original.device)
        delta = (original - revised.to(device=original.device, dtype=original.dtype)).abs().amax(dim=-1)
        outside = allowed[0] <= 0
        outside_delta = delta[0][outside]
        count = int(torch.count_nonzero((delta[0] > 0) & outside).item())
        maximum = float(outside_delta.max().item()) if outside_delta.numel() else 0.0
        scale = delta.amax().clamp_min(1e-12)
        intensity = (delta / scale).clamp(0, 1)
        heat = torch.stack((intensity, intensity * (1 - intensity), 1 - intensity), dim=-1)
        summary = f"Changed pixels outside allowed support: {count}; maximum outside difference: {maximum:.8g}"
        return (heat, summary)


NODE_CLASS_MAPPINGS = {
    "VallpaperShotEditor": VallpaperShotEditor,
    "VallpaperPrepareRevision": VallpaperPrepareRevision,
    "VallpaperApplyRevision": VallpaperApplyRevision,
    "VallpaperRevisionDifference": VallpaperRevisionDifference,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VallpaperShotEditor": "Source + Selection",
    "VallpaperPrepareRevision": "Prepare Shot Revision",
    "VallpaperApplyRevision": "Apply Shot Revision",
    "VallpaperRevisionDifference": "Revision Difference",
}

WEB_DIRECTORY = "./web"
