"""Inspect suite registration and optional runtimes without modifying them."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen


KEYFRAME_CLASSES = (
    "DWPreprocessor", "DepthAnythingV2Preprocessor", "CannyEdgePreprocessor", "LineArtPreprocessor",
    "Krea2OstrisEditModelPatch", "TextEncodeKrea2OstrisEdit", "Krea2ControlLoRALoader",
    "Krea2ControlApply", "Krea2ControlImageEncode", "NK2EInContextEditNode",
    "FluxKontextImageScale", "FluxKontextMultiReferenceLatentMethod", "Lora Loader Stack (rgthree)",
)


def inspect(url, keyframes=False):
    with urlopen(url.rstrip("/") + "/dharani-prod/suite", timeout=10) as response:
        status = json.load(response)
    with urlopen(url.rstrip("/") + "/object_info", timeout=10) as response:
        schema = json.load(response)
    missing = sorted(set(status["nodes"]) - schema.keys())
    if keyframes:
        missing.extend(name for name in KEYFRAME_CLASSES if name not in schema)
    failed = [name for name, state in status["components"].items() if not state["loaded"]]
    return {"version": status["version"], "node_count": len(status["nodes"]),
            "failed_components": failed, "missing_nodes": missing,
            "healthy": not failed and not missing}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--keyframes", action="store_true", help="Also require the external classes used by the unified example.")
    args = parser.parse_args()
    result = inspect(args.url, args.keyframes)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["healthy"] else 1)
