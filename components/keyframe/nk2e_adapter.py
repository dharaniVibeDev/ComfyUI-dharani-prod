"""Strict interoperability adapter for the pinned external NK2E implementation."""
import inspect

import comfy.patcher_extension


def apply_reference(model, reference, nk2e_class):
    module = inspect.getmodule(nk2e_class)
    forward = getattr(module, "_nk2e_incontext_forward", None)
    if not callable(forward):
        raise RuntimeError("The installed NK2E version is incompatible; install the pinned integration from setup_keyframes.py.")
    latent = model.model.process_latent_in(reference["samples"])

    def strict_forward(executor, *args, **kwargs):
        diffusion_model = executor.class_obj
        if not hasattr(diffusion_model, "txtfusion"):
            raise RuntimeError("Canny guidance requires the native Krea 2 base model.")
        options = kwargs.get("transformer_options")
        if not isinstance(options, dict):
            options = next((item for item in args[3:] if isinstance(item, dict)), {})
        # Use the upstream implementation for the model mathematics. Exceptions
        # propagate instead of quietly replacing the requested control with txt2img.
        output = forward(diffusion_model, args[0], args[1], args[2], options, latent)
        if output is None:
            raise RuntimeError("NK2E returned no conditioned output; generation stopped.")
        return output

    patched = model.clone()
    patched.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL,
                                 "dharani_prod_canny_reference", strict_forward)
    return patched
