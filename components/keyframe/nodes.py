import os
from pathlib import Path

import folder_paths
import nodes


class DharaniProdReferenceFrame:
    @classmethod
    def INPUT_TYPES(cls):
        inputs = nodes.LoadImage.INPUT_TYPES()
        spec = inputs["required"]["image"]
        root = Path(folder_paths.get_input_directory())
        imports = root / "MovieReferences"
        choices = list(spec[0])
        if imports.is_dir():
            choices.extend(p.relative_to(root).as_posix()
                           for p in sorted(imports.glob("*.png")) if p.is_file())
        inputs["required"]["image"] = (list(dict.fromkeys(choices)), *spec[1:])
        return inputs

    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"
    CATEGORY = "dharani.prod/keyframe"

    def load_image(self, image):
        path = folder_paths.get_annotated_filepath(image, folder_paths.get_input_directory())
        if not os.path.isfile(path) or not folder_paths.is_within_directory(folder_paths.get_input_directory(), path):
            raise ValueError(f"Invalid reference image selection: {image!r}")
        return nodes.LoadImage().load_image(image)


class DharaniProdReferenceControls:
    """Extract only the selected spatial maps and order up to three for Krea refs."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "use_pose": ("BOOLEAN", {"default": True}),
                "use_depth": ("BOOLEAN", {"default": False}),
                "use_lineart": ("BOOLEAN", {"default": False}),
                "use_canny": ("BOOLEAN", {"default": False}),
                "resolution": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 64}),
                "depth_model": (["depth_anything_v2_vits.pth", "depth_anything_v2_vitb.pth", "depth_anything_v2_vitl.pth"],),
                "lineart_coarse": (["disable", "enable"],),
                "detect_hands": ("BOOLEAN", {"default": True}),
                "detect_face": ("BOOLEAN", {"default": True}),
                "canny_low": ("INT", {"default": 100, "min": 0, "max": 255}),
                "canny_high": ("INT", {"default": 200, "min": 0, "max": 255}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "STRING", "BOOLEAN")
    RETURN_NAMES = ("control_1", "control_2", "control_3", "active_controls", "pose_active")
    FUNCTION = "extract"
    CATEGORY = "dharani.prod/keyframe"

    @staticmethod
    def _require_cached(repo, filename):
        import custom_controlnet_aux.util as aux_util

        model_path = Path(aux_util.annotator_ckpts_path) / repo / filename
        if not model_path.is_file():
            raise RuntimeError(
                f"Reference control model is not installed: {model_path}. "
                "This node will not download models automatically."
            )

    def extract(self, image, use_pose=True, use_depth=False, use_lineart=False,
                use_canny=False, resolution=512, depth_model="depth_anything_v2_vits.pth",
                lineart_coarse="disable", detect_hands=True, detect_face=True,
                canny_low=100, canny_high=200):
        selected = [
            ("pose", use_pose), ("depth", use_depth),
            ("lineart", use_lineart), ("canny", use_canny),
        ]
        active = [name for name, enabled in selected if enabled]
        if len(active) > 3:
            raise ValueError("Krea 2 accepts up to three reference images. Disable one control map.")

        maps = []
        mapping = nodes.NODE_CLASS_MAPPINGS
        for name in active:
            if name == "pose":
                self._require_cached("hr16/yolox-onnx", "yolox_l.torchscript.pt")
                self._require_cached(
                    "hr16/DWPose-TorchScript-BatchSize5",
                    "dw-ll_ucoco_384_bs5.torchscript.pt",
                )
                cls = mapping.get("DWPreprocessor")
                if cls is None:
                    raise RuntimeError("DWPreprocessor is not registered. Load comfyui-controlnet-aux.")
                result = cls().estimate_pose(
                    image, detect_hand="enable" if detect_hands else "disable",
                    detect_body="enable", detect_face="enable" if detect_face else "disable",
                    resolution=resolution, bbox_detector="yolox_l.torchscript.pt",
                    pose_estimator="dw-ll_ucoco_384_bs5.torchscript.pt",
                    scale_stick_for_xinsr_cn="disable",
                )
                maps.append(result["result"][0])
            elif name == "depth":
                depth_repos = {
                    "depth_anything_v2_vitl.pth": "depth-anything/Depth-Anything-V2-Large",
                    "depth_anything_v2_vitb.pth": "depth-anything/Depth-Anything-V2-Base",
                    "depth_anything_v2_vits.pth": "depth-anything/Depth-Anything-V2-Small",
                }
                self._require_cached(depth_repos[depth_model], depth_model)
                cls = mapping.get("DepthAnythingV2Preprocessor")
                if cls is None:
                    raise RuntimeError("DepthAnythingV2Preprocessor is not registered. Load comfyui-controlnet-aux.")
                maps.append(cls().execute(image, ckpt_name=depth_model, resolution=resolution)[0])
            elif name == "lineart":
                self._require_cached("lllyasviel/Annotators", "sk_model.pth")
                self._require_cached("lllyasviel/Annotators", "sk_model2.pth")
                cls = mapping.get("LineArtPreprocessor")
                if cls is None:
                    raise RuntimeError("LineArtPreprocessor is not registered. Load comfyui-controlnet-aux.")
                maps.append(cls().execute(image, resolution=resolution, coarse=lineart_coarse)[0])
            else:
                cls = mapping.get("CannyEdgePreprocessor")
                if cls is None:
                    raise RuntimeError("CannyEdgePreprocessor is not registered. Load comfyui-controlnet-aux.")
                maps.append(cls().execute(
                    image, low_threshold=canny_low, high_threshold=canny_high,
                    resolution=resolution,
                )[0])

        # Match the published pose workflow's Kontext reference sizing.
        if maps:
            import comfy.utils
            from comfy_extras.nodes_flux import PREFERRED_KONTEXT_RESOLUTIONS
            ratio = image.shape[2] / image.shape[1]
            _, width, height = min((abs(ratio - w / h), w, h)
                                   for w, h in PREFERRED_KONTEXT_RESOLUTIONS)
            maps = [comfy.utils.common_upscale(m.movedim(-1, 1), width, height,
                                               "lanczos", "center").movedim(1, -1)
                    for m in maps]
        labels = ", ".join(active) if active else "none"
        return (maps[0] if len(maps) > 0 else None,
                maps[1] if len(maps) > 1 else None,
                maps[2] if len(maps) > 2 else None,
                labels, bool(use_pose))


class DharaniProdControlPreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"slot": ("INT", {"default": 1, "min": 1, "max": 3})},
                "optional": {"image": ("IMAGE",), "active_controls": ("STRING",)}}

    RETURN_TYPES = ()
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "dharani.prod/keyframe"

    def preview(self, slot=1, image=None, active_controls="none"):
        if image is None:
            return {"ui": {"images": []}, "result": ()}
        labels = active_controls.split(", ")
        label = labels[slot - 1] if slot <= len(labels) else "control"
        return nodes.PreviewImage().save_images(image, filename_prefix=f"dharani_{label}")


class DharaniProdPoseLoraGate:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",), "pose_active": ("BOOLEAN", {"default": True}),
            "lora_name": (folder_paths.get_filename_list("loras"),),
            "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
        }}

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "apply"
    CATEGORY = "dharani.prod/keyframe"

    def apply(self, model, pose_active, lora_name, strength=1.0):
        if not pose_active or strength == 0:
            return (model,)
        return nodes.LoraLoaderModelOnly().load_lora_model_only(model, lora_name, strength)


NODE_CLASS_MAPPINGS = {
    "DharaniProdReferenceFrame": DharaniProdReferenceFrame,
    "DharaniProdReferenceControls": DharaniProdReferenceControls,
    "DharaniProdControlPreview": DharaniProdControlPreview,
    "DharaniProdPoseLoraGate": DharaniProdPoseLoraGate,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DharaniProdReferenceFrame": "dharani.prod Reference Browser",
    "DharaniProdReferenceControls": "dharani.prod Reference Controls",
    "DharaniProdControlPreview": "dharani.prod Map Preview",
    "DharaniProdPoseLoraGate": "dharani.prod Pose Control LoRA",
}
