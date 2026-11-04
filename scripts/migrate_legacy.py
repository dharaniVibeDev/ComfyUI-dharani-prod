"""Move legacy packs outside custom_nodes without deleting user edits."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

LEGACY_PACKS = (
    "vallpaper-hardware-monitor", "vallpaper-shot-revision",
    "comfyui-h3-reference-tagging", "prompt-archive-docx", "vallpaper-voice",
    "vallpaper-kitten-tts", "dharani-prod-reference-frame",
)


def migrate(comfy_root, apply=False):
    root = Path(comfy_root).resolve()
    custom = (root / "custom_nodes").resolve()
    if not (root / "main.py").is_file() or not custom.is_dir():
        raise ValueError("Choose the ComfyUI root containing main.py and custom_nodes.")
    planned = []
    backup = root / "user" / "dharani-prod-migration" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for name in LEGACY_PACKS:
        source = custom / name
        if not source.exists():
            continue
        # Do not move junction/symlink targets outside the named custom-node root.
        if source.resolve().parent != custom:
            raise ValueError(f"Legacy pack is a link or outside custom_nodes: {name}; migrate it manually.")
        target = backup / name
        planned.append({"source": str(source), "backup": str(target)})
    if not apply:
        return {"applied": False, "moves": planned}
    backup.mkdir(parents=True, exist_ok=False)
    manifest = backup / "manifest.json"
    completed = []
    try:
        for move in planned:
            if Path(move["backup"]).exists():
                raise FileExistsError(move["backup"])
            shutil.move(move["source"], move["backup"])
            completed.append(move)
    except Exception:
        for move in reversed(completed):
            shutil.move(move["backup"], move["source"])
        raise
    result = {"applied": True, "comfy_root": str(root), "moves": completed}
    manifest.write_text(json.dumps(result, indent=2), encoding="utf8")
    return {**result, "manifest": str(manifest)}


def restore(manifest_path, apply=False):
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf8"))
    root = Path(data["comfy_root"]).resolve()
    custom = (root / "custom_nodes").resolve()
    moves = list(reversed(data["moves"]))
    for move in moves:
        destination = Path(move["source"]).resolve()
        backup = Path(move["backup"]).resolve()
        if destination.parent != custom or backup.parent != path.parent:
            raise ValueError("Manifest paths are outside the recorded migration directories.")
        if destination.exists() or not backup.is_dir():
            raise ValueError(f"Restore would overwrite a pack or its backup is missing: {destination.name}")
    if apply:
        for move in moves:
            shutil.move(move["backup"], move["source"])
    return {"restored": apply, "moves": moves}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--comfy-root")
    group.add_argument("--restore", help="Migration manifest to restore; disable the suite before the next restart.")
    parser.add_argument("--apply", action="store_true", help="Without this flag, only print the plan.")
    args = parser.parse_args()
    print(json.dumps(restore(args.restore, args.apply) if args.restore else migrate(args.comfy_root, args.apply), indent=2))
