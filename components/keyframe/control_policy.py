"""Pure routing policy: map previews and generation adapters are distinct choices."""
MODES = ("pose", "depth", "canny", "lineart")
AUTO = "auto (one enabled)"


def choose_route(enabled, selection=AUTO):
    active = tuple(mode for mode in MODES if enabled.get(mode, False))
    error = None
    if selection == AUTO:
        route = active[0] if len(active) == 1 else "none"
        if len(active) > 1:
            error = ("Several preview maps are ON. Choose generation_control explicitly. "
                     "Simultaneous adapter combinations are not validated; no adapter will be silently chosen.")
    elif selection not in MODES:
        route, error = "none", "Unknown generation control."
    elif selection not in active:
        route, error = "none", f"Turn ON {selection} before selecting it for generation."
    else:
        route = selection
    message = "Preview maps: " + (", ".join(active) or "none")
    message += "\nGeneration adapter: " + ("BLOCKED" if error else route)
    if error:
        message += "\n" + error
    elif len(active) > 1:
        message += "\nOther enabled maps are previews only; guidance is not combined."
    elif route == "none":
        message += "\nAll maps OFF: prompt-only generation."
    return {"active": active, "route": route, "error": error, "status": message}
