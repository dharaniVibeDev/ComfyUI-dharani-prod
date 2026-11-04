"""dharani.prod: a single, backwards-compatible ComfyUI node suite."""
import importlib
import logging

from aiohttp import web
from server import PromptServer

__version__ = "0.1.0"
WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
MODULE_STATUS = {}

DISPLAY_NAMES = {
    "VallpaperHardware": "Hardware", "VallpaperTimer": "Timer",
    "VallpaperShotEditor": "Shot Editor", "VallpaperPrepareRevision": "Prepare Shot Revision",
    "VallpaperApplyRevision": "Apply Shot Revision", "VallpaperRevisionDifference": "Revision Difference",
    "H3ReferenceTags": "H3 Reference Tags", "PromptArchiveDOCX": "Prompt Archive",
    "VallpaperVoice": "Voice", "VallpaperVoiceLine": "Voice Line",
    "VallpaperVoiceDirector": "Voice Director", "VallpaperVoiceSelect": "Voice Select",
    "VallpaperVoiceSession": "Voice Session", "VallpaperVoiceFX": "Voice FX",
    "VallpaperKittenClone": "Kitten TTS Clone",
    "DharaniProdReferenceFrame": "Reference Browser",
    "DharaniProdReferenceControls": "Reference Controls (legacy)",
    "DharaniProdControlPreview": "Map Preview",
    "DharaniProdPoseLoraGate": "Pose Control LoRA (legacy)",
    "DharaniProdControlPanel": "Control Panel",
    "DharaniProdSpatialAdapter": "Scene Prompt and Adapter",
    "DharaniProdRoutedSampler": "Routed Sampler",
}

for component in ("system", "shot_revision", "h3_tags", "archive", "voice", "kitten_tts", "keyframe"):
    try:
        module = importlib.import_module(f".components.{component}", __name__)
        classes = module.NODE_CLASS_MAPPINGS
        duplicates = NODE_CLASS_MAPPINGS.keys() & classes.keys()
        if duplicates:
            raise RuntimeError(f"Duplicate node IDs: {sorted(duplicates)}")
        NODE_CLASS_MAPPINGS.update(classes)
        for node_id, cls in classes.items():
            cls.CATEGORY = f"dharani.prod/{component.replace('_', ' ')}"
            NODE_DISPLAY_NAME_MAPPINGS[node_id] = "dharani.prod " + DISPLAY_NAMES[node_id]
        MODULE_STATUS[component] = {"loaded": True, "nodes": len(classes)}
    except Exception as exc:
        MODULE_STATUS[component] = {"loaded": False, "error": str(exc)}
        logging.exception("[dharani.prod] Could not load component %s", component)


@PromptServer.instance.routes.get("/dharani-prod/suite")
async def suite_status(request):
    return web.json_response({"version": __version__, "components": MODULE_STATUS,
                              "nodes": NODE_DISPLAY_NAME_MAPPINGS})


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
