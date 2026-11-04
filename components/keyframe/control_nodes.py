"""ComfyUI adapters around the tested spatial-control implementations."""
import os
import nodes
from .control_policy import AUTO, MODES, choose_route


def results(value):
    if isinstance(value, dict):
        return value["result"]
    return value.result if hasattr(value, "result") else value


def registered(name):
    cls = nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:
        raise RuntimeError(f"Required node {name} is not loaded. Restart ComfyUI with the installed adapter pack.")
    return cls


class DharaniProdControlPanel:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "pose_on": ("BOOLEAN", {"default": False}),
            "depth_on": ("BOOLEAN", {"default": True}),
            "canny_on": ("BOOLEAN", {"default": False}),
            "lineart_on": ("BOOLEAN", {"default": False}),
            "generation_control": ([AUTO, *MODES],),
            "resolution": ("INT", {"default": 512, "min": 256, "max": 2048, "step": 64}),
            "control_strength": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 2.0, "step": 0.05}),
            "canny_low": ("INT", {"default": 100, "min": 0, "max": 255}),
            "canny_high": ("INT", {"default": 200, "min": 0, "max": 255}),
        }}

    RETURN_TYPES = ("DHARANI_CONTROL_PLAN", "IMAGE", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("control_plan", "pose_map", "depth_map", "canny_map", "lineart_map")
    FUNCTION = "plan"
    CATEGORY = "dharani.prod/keyframe"
    DESCRIPTION = "Independent extraction switches. Auto routes one enabled map. With multiple previews choose the generation adapter explicitly."

    def plan(self, image, pose_on=False, depth_on=True, canny_on=False, lineart_on=False,
             generation_control=AUTO, resolution=512, control_strength=1.0,
             canny_low=100, canny_high=200):
        from .nodes import DharaniProdReferenceControls
        enabled = dict(zip(MODES, (pose_on, depth_on, canny_on, lineart_on)))
        policy = choose_route(enabled, generation_control)
        maps = dict.fromkeys(MODES)
        extractor = DharaniProdReferenceControls()
        for mode in policy["active"]:
            maps[mode] = extractor.extract(
                image, use_pose=mode == "pose", use_depth=mode == "depth",
                use_canny=mode == "canny", use_lineart=mode == "lineart",
                resolution=resolution, depth_model="depth_anything_v2_vits.pth",
                lineart_coarse="enable", canny_low=canny_low, canny_high=canny_high,
            )[0]
        plan = {**policy, "maps": maps, "source": image, "strength": control_strength}
        return {"ui": {"text": [policy["status"]]},
                "result": (plan, *(maps[mode] for mode in MODES))}


class DharaniProdSpatialAdapter:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "control_plan": ("DHARANI_CONTROL_PLAN",),
            "model": ("MODEL",), "clip": ("CLIP",), "vae": ("VAE",),
            "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True}),
        }}

    RETURN_TYPES = ("DHARANI_RENDER_RECIPE",)
    RETURN_NAMES = ("render_recipe",)
    FUNCTION = "prepare"
    CATEGORY = "dharani.prod/keyframe"
    DESCRIPTION = "Routes to the matching installed adapter without stacking incompatible model forward patches."

    def __init__(self):
        self._route = None
        self._instances = {}

    def call(self, name, **kwargs):
        cls = registered(name)
        if name not in self._instances:
            self._instances[name] = cls()
        instance = self._instances[name]
        function = getattr(cls, "FUNCTION", "execute")
        return results(getattr(instance, function)(**kwargs))

    def prepare(self, control_plan, model, clip, vae, prompt):
        if control_plan["error"]:
            raise ValueError(control_plan["error"])
        # ModelPatcher clones share the physical module. Restore resident clones
        # before an adapter inspects/captures first/forward/extra_conds.
        import comfy.model_management
        comfy.model_management.unload_model_and_clones(model)
        route = control_plan["route"]
        if self._route != route:
            self._instances.clear()
            self._route = route
        control = control_plan["maps"].get(route)
        if control is None:
            control = self.call("FluxKontextImageScale", image=control_plan["source"])[0]
        height, width = control.shape[1:3]
        latent = nodes.EmptyLatentImage().generate(width, height, 1)[0]
        strength = control_plan["strength"]
        if route in ("pose", "lineart"):
            filename = "krea2_turbo_openpose_controlnet.safetensors" if route == "pose" else "krea2_lineart_coarse_edit_v1.safetensors"
            model = self.call("LoraLoaderModelOnly", model=model, lora_name=os.path.join("Krea2", filename), strength_model=strength)[0]
            model = self.call("Krea2OstrisEditModelPatch", model=model, kv_cache=True)[0]
            positive = self.call("TextEncodeKrea2OstrisEdit", clip=clip, prompt=prompt, vae=vae, image1=control)[0]
            positive = self.call("FluxKontextMultiReferenceLatentMethod", conditioning=positive, reference_latents_method="index_timestep_zero")[0]
        else:
            positive = nodes.CLIPTextEncode().encode(clip, prompt)[0]
            if route == "depth":
                model = self.call("Krea2ControlLoRALoader", model=model, lora_name=os.path.join("Krea2", "depth-control-lora.safetensors"), strength=strength)[0]
                encoded = self.call("Krea2ControlImageEncode", control_image=control, vae=vae,
                                    resize="match_latent_size", upscale_method="lanczos", crop="center",
                                    channel_mode="grayscale", normalize="per_image_minmax", invert=False,
                                    batch_mode="independent_images", latent=latent)[0]
                model = self.call("Krea2ControlApply", model=model, control_latent=encoded)[0]
            elif route == "canny":
                model = self.call("LoraLoaderModelOnly", model=model, lora_name=os.path.join("Krea2", "NK2E-canny-v0.1.safetensors"), strength_model=strength)[0]
                encoded = nodes.VAEEncode().encode(vae, control)[0]
                from .nk2e_adapter import apply_reference
                model = apply_reference(model, encoded, registered("NK2EInContextEditNode"))
        negative = nodes.ConditioningZeroOut().zero_out(positive)[0]
        recipe = {"model": model, "positive": positive, "negative": negative, "latent": latent,
                  "route": route, "steps": 10 if route == "pose" else 8,
                  "sampler": "euler_ancestral" if route == "lineart" else "euler"}
        return (recipe,)


class DharaniProdRoutedSampler:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "render_recipe": ("DHARANI_RENDER_RECIPE",),
            "seed": ("INT", {"default": 42, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True}),
            "steps_override": ("INT", {"default": 0, "min": 0, "max": 60, "tooltip": "0 uses tested defaults: pose 10, other modes 8."}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "sample"
    CATEGORY = "dharani.prod/keyframe"
    DESCRIPTION = "Uses the tested sampler/scheduler/CFG defaults for the selected adapter. No hidden prompt rewriting."

    def sample(self, render_recipe, seed=42, steps_override=0):
        r = render_recipe
        return nodes.common_ksampler(r["model"], seed, steps_override or r["steps"], 1.0,
                                    r["sampler"], "simple", r["positive"], r["negative"],
                                    r["latent"], denoise=1.0)


NODE_CLASS_MAPPINGS = {
    "DharaniProdControlPanel": DharaniProdControlPanel,
    "DharaniProdSpatialAdapter": DharaniProdSpatialAdapter,
    "DharaniProdRoutedSampler": DharaniProdRoutedSampler,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DharaniProdControlPanel": "dharani.prod Control Panel",
    "DharaniProdSpatialAdapter": "dharani.prod Scene Prompt and Adapter",
    "DharaniProdRoutedSampler": "dharani.prod Routed Sampler",
}
