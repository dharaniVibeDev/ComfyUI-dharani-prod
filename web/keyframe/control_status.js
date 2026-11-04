import { app } from "/scripts/app.js";
import { ComfyWidgets } from "/scripts/widgets.js";

const NODE_TYPE = "DharaniProdControlPanel";
const WIDGET_NAME = "active_route";

function isControlPanel(node) {
    return node?.comfyClass === NODE_TYPE || node?.type === NODE_TYPE;
}

function statusWidget(node) {
    return node.widgets?.find((widget) => widget.name === WIDGET_NAME);
}

function updateStatus(node, value, stale = false) {
    const widget = statusWidget(node);
    if (!widget) return;
    widget.value = `${stale ? "STALE - settings changed; run the workflow to refresh.\n\n" : ""}${value || "No backend status was returned."}`;
    node.setDirtyCanvas?.(true, true);
}

function draftStatus(node) {
    const value = (name) => node.widgets?.find((w) => w.name === name)?.value;
    const active = ["pose", "depth", "canny", "lineart"].filter((name) => value(`${name}_on`));
    const selection = value("generation_control");
    let route = selection === "auto (one enabled)" ? (active.length === 1 ? active[0] : "none") : selection;
    let detail = "";
    if (selection === "auto (one enabled)" && active.length > 1) {
        route = "BLOCKED";
        detail = "Choose generation_control explicitly. Multiple adapters are not combined.";
    } else if (route !== "none" && !active.includes(route)) {
        route = "BLOCKED";
        detail = "Turn ON the map chosen for generation.";
    } else if (active.length > 1) {
        detail = "Other enabled maps are previews only; guidance is not combined.";
    }
    return `Preview maps: ${active.join(", ") || "none"}\nGeneration adapter: ${route}\n${detail}`;
}

app.registerExtension({
    name: "dharani.prod.control-status",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = onExecuted?.apply(this, arguments);
            if (!isControlPanel(this)) return result;
            const text = message?.text;
            const value = Array.isArray(text) ? text.join("\n") : text;
            updateStatus(this, typeof value === "string" ? value : "No backend status was returned.");
            return result;
        };
    },
    nodeCreated(node) {
        if (!isControlPanel(node)) return;
        const widget = statusWidget(node) || ComfyWidgets.STRING(
            node, WIDGET_NAME,
            ["STRING", { multiline: true, default: "Run the workflow to show the actual generation route." }], app
        ).widget;
        if (widget) {
            widget.options = { ...(widget.options || {}), multiline: true, readonly: true, serialize: false };
            widget.serialize = false;
            widget.serializeValue = () => undefined;
            if (widget.inputEl) widget.inputEl.readOnly = true;
        }
        for (const candidate of node.widgets || []) {
            if (candidate === widget) continue;
            const callback = candidate.callback;
            candidate.callback = function (...args) {
                const result = callback?.apply(this, args);
                updateStatus(node, draftStatus(node), true);
                return result;
            };
        }
    },
});
