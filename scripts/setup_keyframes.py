"""Review/install pinned external node packs and optional control weights."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def setup(comfy_root, install_nodes=False, download_models=False):
    root = Path(comfy_root).resolve()
    if not (root / "main.py").is_file():
        raise ValueError("Choose the ComfyUI root containing main.py.")
    manifest = json.loads((REPO / "model_manifest.json").read_text(encoding="utf8"))
    for item in manifest["node_packs"]:
        dest = root / "custom_nodes" / item["folder"]
        if dest.exists():
            print(f"EXISTS (untouched): {dest}")
        elif install_nodes:
            dest.mkdir(parents=True)
            subprocess.run(["git", "init", str(dest)], check=True)
            subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", item["url"]], check=True)
            subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", item["revision"]], check=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "--detach", "FETCH_HEAD"], check=True)
        else:
            print(f"MISSING NODE PACK: {item['folder']} ({item['url']})")
    for item in manifest["models"]:
        dest = root / item["destination"]
        if dest.is_file() and dest.stat().st_size == item["bytes"]:
            if sha256(dest) == item["sha256"]:
                print(f"VERIFIED: {dest.name}")
                continue
            raise ValueError(f"Existing file has an unexpected checksum; it was not overwritten: {dest}")
        if dest.exists():
            raise ValueError(f"Existing file has an unexpected size; inspect it before replacing: {dest}")
        print(f"MODEL: {item['repo']} / {item['filename']} ({item['bytes']:,} bytes; {item['license']})")
        if not download_models:
            continue
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError("Install huggingface_hub in this interpreter to use --download-models.") from exc
        dest.parent.mkdir(parents=True, exist_ok=True)
        download = Path(hf_hub_download(item["repo"], filename=item["filename"],
                                       revision=item["revision"], local_dir=dest.parent))
        if download.stat().st_size != item["bytes"] or sha256(download) != item["sha256"]:
            raise ValueError(f"Downloaded checkpoint verification failed: {item['filename']}")
        if download.resolve() != dest.resolve():
            download.replace(dest)
        print(f"DOWNLOADED AND VERIFIED: {dest}")
    print("Base diffusion model, text encoder, VAE and speech runtimes are not downloaded by this script.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", required=True)
    parser.add_argument("--install-nodes", action="store_true")
    parser.add_argument("--download-models", action="store_true")
    args = parser.parse_args()
    setup(args.comfy_root, args.install_nodes, args.download_models)
