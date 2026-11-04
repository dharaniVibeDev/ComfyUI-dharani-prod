"""Copy the public geometric demo asset into a standard ComfyUI input folder."""
import argparse
from pathlib import Path
import shutil

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", required=True)
    args = parser.parse_args()
    root = Path(args.comfy_root).resolve()
    if not (root / "main.py").is_file():
        raise ValueError("Choose the ComfyUI folder containing main.py.")
    source = Path(__file__).resolve().parents[1] / "examples/assets/demo-reference.png"
    destination = root / "input" / "dharani-prod-demo.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        raise FileExistsError("A different file already uses the demo filename; upload a reference manually instead.")
    if not destination.exists():
        shutil.copy2(source, destination)
    print(destination)
