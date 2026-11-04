# Agent installation and setup prompt

Copy the following prompt into your local coding agent and fill in the settings. The agent needs access to the machine where ComfyUI runs.

```text
Install and configure https://github.com/dharaniVibeDev/ComfyUI-dharani-prod in my existing ComfyUI.

SETTINGS
COMFY_ROOT = <absolute path to the ComfyUI folder containing main.py>
COMFY_URL = http://127.0.0.1:8188
FEATURES = system, shot_revision, archive, h3_tags, keyframes
ALLOW_CONTROL_MODEL_DOWNLOADS = false
ALLOW_LARGE_BASE_MODEL_DOWNLOADS = false
ENABLE_VOICE_RUNTIMES = false

Read this repository's README, requirements.txt, model_manifest.json and scripts before acting.

1. Locate the actual ComfyUI interpreter and version. Use its environment for dependencies.
   Do not replace PyTorch/CUDA or create a second ComfyUI installation.
2. Inspect the running queue and preserve any unsaved work before stopping/restarting ComfyUI.
   Clone this repository into COMFY_ROOT/custom_nodes/ComfyUI-dharani-prod.
   If it already exists, inspect its remote and local edits before updating; do not reset edits.
3. Check whether legacy suite folders exist. Run scripts/migrate_legacy.py without --apply first.
   Explain the planned moves; authorization to consolidate means you may apply the reversible
   backup migration when ComfyUI is stopped. Retain the printed rollback manifest.
   Do not delete old nodes, user images, voices, archives, models, or workflows.
4. Install requirements.txt with the verified ComfyUI Python, while ComfyUI is stopped.
   Check currently installed versions first. Do not blindly upgrade unrelated packages.
5. For keyframes, inventory the existing base model, vision-capable text encoder, VAE,
   adapter weights and node classes. Use scripts/setup_keyframes.py to review the plan.
   Install missing pinned node packs using --install-nodes. Existing forks stay untouched.
   Read each dependency's requirements and install only missing compatible libraries.
   If ALLOW_CONTROL_MODEL_DOWNLOADS=true, download the manifest's optional weights using
   --download-models. That flag is authorization for those listed downloads.
   Otherwise list the missing weights and continue checking the core suite.
   Do not download a base model unless ALLOW_LARGE_BASE_MODEL_DOWNLOADS=true and its exact
   source, license, disk requirement and hardware fit have been established.
6. Speech-model runtimes are optional and isolated from ComfyUI. If ENABLE_VOICE_RUNTIMES
   is false, do not install or download them. Explain that Voice FX still works on CPU and
   that speech generation requires separate runtime setup.
7. Start ComfyUI with the suite loaded, refresh its browser, and run scripts/doctor.py.
   Confirm 22 registered suite node IDs and no failed components. Keep legacy node IDs
   intact; visible names should start with dharani.prod. Do not invent Comfy Registry IDs.
8. Check Hardware and Timer in the actual UI. Verify idle-only VRAM cleanup remains guarded.
   Check Shot Editor with a disposable demo image and Prompt Archive with disposable output.
   Test Reference Browser search -> movie -> frame selection -> input import -> node load.
   Do not publish or upload my media, prompts, voices, archives or screenshots.
9. Validate the unified keyframe example against live /object_info and choose installed
   model filenames. Test only configured modes; do not claim unconfigured modes work.
   Multiple preview maps do not imply simultaneous guidance. Verify that ambiguous auto
   selection is blocked and the actual selected generation adapter is shown.
10. Report the install path, active URL, dependency/model/runtime status, completed checks,
    any unresolved errors, and the migration rollback path. Include evidence, not claims
    that something was installed or tested when it was not.
```

`ALLOW_CONTROL_MODEL_DOWNLOADS` covers adapter and preprocessor weights only. Base diffusion models, text encoders, VAEs, speech models, paid services and accounts are separate decisions. Local model files are never uploaded by these setup tools.
