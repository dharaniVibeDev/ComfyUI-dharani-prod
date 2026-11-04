import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

async function request(path, options) {
    const response = await api.fetchApi(`/dharani-prod/reference/${path}`, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
}

function el(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
}

function openBrowser(node) {
    const dialog = el("dialog", "", "dharani-reference-browser");
    dialog.innerHTML = `<style>
      .dharani-reference-browser {width:min(1050px,92vw);max-height:90vh;box-sizing:border-box;background:var(--comfy-menu-bg,#202020);color:var(--input-text,#eee);border:1px solid #666;border-radius:10px;padding:20px;font:14px system-ui}
      .dharani-reference-browser::backdrop {background:#000a}
      .dharani-reference-browser header,.dharani-reference-browser form,.dharani-reference-browser footer {display:flex;gap:12px;align-items:center;margin-bottom:14px}
      .dharani-reference-browser h2 {margin:0;flex:1;font-size:19px}
      .dharani-reference-browser button,.dharani-reference-browser input {font:inherit;color:inherit;background:var(--comfy-input-bg,#303030);border:1px solid #777;border-radius:5px;padding:9px 12px}
      .dharani-reference-browser button {cursor:pointer}
      .dharani-reference-browser button:focus-visible,.dharani-reference-browser input:focus-visible {outline:2px solid #91c8fa;outline-offset:2px}
      .dharani-reference-browser button:disabled {opacity:.5;cursor:default}
      .dharani-reference-browser input {flex:1;min-width:0}
      .dharani-reference-browser .results {display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;overflow:auto;max-height:57vh;padding:3px}
      .dharani-reference-browser .frame {padding:4px;text-align:left;display:flex;flex-direction:column;gap:6px}
      .dharani-reference-browser .frame img {width:100%;aspect-ratio:16/10;object-fit:contain;background:#080808}
      .dharani-reference-browser .selected {outline:3px solid #91c8fa}
      .dharani-reference-browser .status {min-height:1.5em;margin:8px 0 14px;white-space:pre-wrap}
      .dharani-reference-browser footer {margin:16px 0 0;flex-wrap:wrap}
      .dharani-reference-browser a {color:#91c8fa}
    </style>`;
    const header = el("header");
    header.append(el("h2", "dharani.prod Reference Browser"));
    const close = el("button", "Close"); close.onclick = () => dialog.close(); header.append(close);
    const form = el("form");
    const input = el("input"); input.placeholder = "Search a movie, e.g. Blade Runner"; input.setAttribute("aria-label", "Movie title"); input.required = true; input.minLength = 2;
    const search = el("button", "Search FilmGrab"); search.type = "submit"; form.append(input, search);
    const status = el("div", "Search FilmGrab, choose a movie, then select a frame.", "status"); status.setAttribute("role", "status");
    const grid = el("div", "", "results");
    const footer = el("footer");
    const back = el("button", "Back to movies"); back.hidden = true;
    const next = el("button", "More movies"); next.hidden = true;
    const use = el("button", "Use selected frame"); use.disabled = true;
    const source = el("a", "Source: FilmGrab"); source.href = "https://film-grab.com"; source.target = "_blank"; source.rel = "noopener noreferrer";
    footer.append(back, next, use, source);
    dialog.append(header, form, status, grid, footer); document.body.append(dialog);
    let movies = [], movie = null, selected = null, page = 1, busy = false;
    const error = (e) => { status.textContent = e.message; };
    function movieList() {
        movie = null; selected = null; use.disabled = true; back.hidden = true;
        grid.replaceChildren(); next.hidden = movies.length < 12;
        for (const entry of movies) {
            const button = el("button", entry.title); button.onclick = () => loadFrames(entry.id); grid.append(button);
        }
        status.textContent = movies.length ? "Choose a movie to browse its frames." : "No matching movies on FilmGrab. Try another title.";
    }
    async function find(reset = true) {
        if (busy) return;
        busy = true; search.disabled = true; next.disabled = true; use.disabled = true;
        if (reset) page = 1;
        status.textContent = "Searching FilmGrab…";
        try { movies = await request(`search?q=${encodeURIComponent(input.value.trim())}&page=${page}`); movieList(); }
        catch (e) { error(e); }
        finally { busy = false; search.disabled = false; next.disabled = false; }
    }
    async function loadFrames(id) {
        if (busy) return;
        busy = true; status.textContent = "Loading frame gallery…"; use.disabled = true;
        try {
            movie = await request(`frames/${id}`); selected = null;
            grid.replaceChildren(); back.hidden = false; next.hidden = true;
            source.href = movie.source; source.textContent = `${movie.title} · FilmGrab`;
            movie.frames.forEach((frame, index) => {
                const button = el("button", "", "frame"); button.setAttribute("aria-label", `Select frame ${index + 1}`); button.setAttribute("aria-pressed", "false");
                const img = el("img"); img.src = frame.thumbnail; img.alt = `${movie.title}, frame ${index + 1}`; img.loading = "lazy"; img.referrerPolicy = "no-referrer";
                button.append(img, el("span", `Frame ${index + 1}`));
                button.onclick = () => {
                    grid.querySelectorAll(".selected").forEach((b) => { b.classList.remove("selected"); b.setAttribute("aria-pressed", "false"); });
                    selected = index; button.classList.add("selected"); button.setAttribute("aria-pressed", "true"); use.disabled = false;
                    status.textContent = `${movie.title} · Frame ${index + 1} selected`;
                }; grid.append(button);
            });
            status.textContent = `${movie.title} · ${movie.frames.length} frames. Select one to import.`;
        } catch (e) { error(e); }
        finally { busy = false; }
    }
    use.onclick = async () => {
        if (selected === null || busy) return;
        busy = true; use.disabled = true; status.textContent = "Importing the selected frame…";
        try {
            const result = await request("import", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({post_id:movie.id,index:selected})});
            const widget = node.widgets?.find((w) => w.name === "image");
            if (!widget) throw new Error("The reference-image widget is unavailable.");
            if (Array.isArray(widget.options?.values) && !widget.options.values.includes(result.image)) widget.options.values.push(result.image);
            widget.value = result.image;
            widget.callback?.(result.image);
            const img = new Image();
            img.onload = () => { node.imgs = [img]; node.setDirtyCanvas(true, true); };
            const slash = result.image.lastIndexOf("/");
            img.src = api.apiURL(`/view?filename=${encodeURIComponent(result.image.slice(slash + 1))}&subfolder=${encodeURIComponent(result.image.slice(0, slash))}&type=input`);
            node.properties.dharani_reference_source = result.source;
            app.graph.setDirtyCanvas(true, true); dialog.close();
        } catch (e) { error(e); use.disabled = false; }
        finally { busy = false; }
    };
    form.onsubmit = (e) => { e.preventDefault(); find(); };
    back.onclick = movieList; next.onclick = () => { page++; find(false); };
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => dialog.remove());
    dialog.showModal(); input.focus();
}

app.registerExtension({
    name: "dharani.prod.reference-browser",
    nodeCreated(node) {
        if (node.comfyClass !== "DharaniProdReferenceFrame" && node.type !== "DharaniProdReferenceFrame") return;
        node.addWidget("button", "Browse Movie Frames", null, () => openBrowser(node), {serialize:false});
    },
});
