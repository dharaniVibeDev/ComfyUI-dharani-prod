import { app } from '/scripts/app.js';
import { api } from '/scripts/api.js';
import { imagePoint, fitView, zoomView } from './shot-editor-geometry.mjs';

const EXT = 'vallpaper.shot-editor';
const stylesheet = document.createElement('link');
stylesheet.rel = 'stylesheet';
stylesheet.href = new URL('./shot-editor.css?v=2', import.meta.url).href;
document.head.append(stylesheet);

function element(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

function readState(widget, source) {
  try {
    const state = JSON.parse(widget.value || '{}');
    return state.source === source ? state : {};
  } catch { return {}; }
}

function assetUrl(value) {
  const match = /^(.*?)(?:\s+\[(input|output|temp)\])?$/.exec(String(value).replaceAll('\\', '/'));
  const path = match[1], slash = path.lastIndexOf('/');
  return api.apiURL('/view?' + new URLSearchParams({
    filename: path.slice(slash + 1), subfolder: slash < 0 ? '' : path.slice(0, slash),
    type: match[2] || 'input', channel: 'rgb',
  }));
}

async function loadImage(value) {
  const image = new Image();
  image.src = assetUrl(value);
  await image.decode();
  return image;
}

async function upload(blob, name) {
  const form = new FormData();
  form.append('image', blob, name);
  form.append('type', 'input');
  form.append('subfolder', 'shot-revision');
  form.append('overwrite', 'false');
  const response = await api.fetchApi('/upload/image', { method: 'POST', body: form });
  if (!response.ok) throw new Error('Could not save image (' + response.status + '). Try again.');
  const file = await response.json();
  return (file.subfolder ? file.subfolder + '/' : '') + file.name + ' [' + (file.type || 'input') + ']';
}

function canvas(width, height) {
  const result = document.createElement('canvas');
  result.width = width; result.height = height;
  return result;
}

function button(text, label, callback, cls = '') {
  const result = element('button', cls, text);
  result.type = 'button'; result.title = label; result.setAttribute('aria-label', label);
  result.addEventListener('click', callback);
  return result;
}

function icon(paths) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) svg.setAttribute(key, value);
  for (const d of paths) {
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', d); svg.append(path);
  }
  return svg;
}

const TOOLS = [
  ['pen', 'Pen', 'P', ['M3 21l4-11L17 3l4 4-7 10-11 4Z', 'M3 21l8-8', 'M9 12l3 3']],
  ['brush', 'Brush', 'B', ['M14 4l6 6-9 9-6-6 9-9Z', 'M5 13c-4 2-1 5-3 8 5 0 8-1 9-2']],
  ['eraser', 'Eraser', 'E', ['M14 3l7 7-10 11H7l-5-5L14 3Z', 'M8 10l7 7', 'M11 21h11']],
  ['rect', 'Rectangle', 'M', ['M4 4h16v16H4V4Z']],
  ['pan', 'Hand', 'H', ['M7 12V6a2 2 0 014 0v5-7a2 2 0 014 0v7-5a2 2 0 014 0v8c0 5-3 8-7 8-3 0-5-2-7-5l-3-4a2 2 0 013-2l2 2Z']],
];

class SelectionEditor {
  constructor(node) {
    this.node = node;
    this.imageWidget = node.widgets.find(w => w.name === 'image');
    this.stateWidget = node.widgets.find(w => w.name === 'editor_state');
    this.source = String(this.imageWidget.value);
    this.saved = readState(this.stateWidget, this.source);
    this.paths = structuredClone(this.saved.paths || []);
    this.activePath = this.paths.find(p => !p.closed) || null;
    this.tool = 'pen'; this.space = false; this.busy = false;
    this.opacity = .35; this.brushSize = Number(this.saved.brush_size) || 48;
    this.viewport = { scale: 1, x: 0, y: 0 };
    this.history = []; this.future = []; this.rasterDirty = true; this.maskDirty = true;
    this.dispose = [];
  }
  async open() {
    this.image = await loadImage(this.source);
    this.width = this.image.naturalWidth; this.height = this.image.naturalHeight;
    this.brush = canvas(this.width, this.height);
    this.brushContext = this.brush.getContext('2d', { willReadFrequently: true });
    this.selection = canvas(this.width, this.height);
    this.overlay = canvas(this.width, this.height);
    const brushFile = this.saved.brush_file || this.saved.mask_file;
    if (brushFile) {
      const mask = await loadImage(brushFile);
      if (mask.naturalWidth !== this.width || mask.naturalHeight !== this.height) throw new Error('Saved selection size differs from the image. Choose the matching source image.');
      this.brushContext.drawImage(mask, 0, 0);
      const data = this.brushContext.getImageData(0, 0, this.width, this.height);
      for (let i = 0; i < data.data.length; i += 4) {
        const value = data.data[i];
        data.data[i] = data.data[i + 1] = data.data[i + 2] = 255;
        data.data[i + 3] = value;
      }
      this.brushContext.putImageData(data, 0, 0);
      if (!this.saved.brush_file) this.paths = [];
    }
    this.build(); this.dialog.showModal(); this.stage.focus();
    this.resize(true);
    const observer = new ResizeObserver(() => this.resize());
    observer.observe(this.stage); this.dispose.push(() => observer.disconnect());
    this.checkpoint(); this.setTool('pen');
  }
  build() {
    this.dialog = element('dialog', 'vse-dialog');
    this.dialog.setAttribute('aria-label', 'dharani.prod Shot Editor');
    this.dialog.addEventListener('cancel', event => { event.preventDefault(); this.close(); });
    const header = element('header', 'vse-header');
    const heading = element('div', 'vse-heading');
    heading.append(element('strong', '', 'dharani.prod Shot Editor'), element('span', '', this.width + ' x ' + this.height + ' px'));
    this.cancelButton = button('Cancel', 'Discard selection changes', () => this.close());
    this.saveButton = button('Save selection', 'Save selection and return to the workflow', () => this.save(), 'vse-primary');
    header.append(heading, this.cancelButton, this.saveButton);
    const rail = element('nav', 'vse-rail'); rail.setAttribute('aria-label', 'Selection tools');
    this.toolButtons = new Map();
    for (const [key, name, shortcut, paths] of TOOLS) {
      const tool = button('', name + ' tool (' + shortcut + ')', () => this.setTool(key), 'vse-tool');
      tool.append(icon(paths), element('span', '', name));
      this.toolButtons.set(key, tool); rail.append(tool);
    }
    this.stage = element('div', 'vse-stage'); this.stage.tabIndex = 0;
    this.stage.setAttribute('aria-label', 'Image canvas. Space and drag to pan. Mouse wheel to zoom.');
    this.view = canvas(1, 1); this.view.className = 'vse-view'; this.stage.append(this.view);
    this.context = this.view.getContext('2d');
    const inspector = element('aside', 'vse-inspector');
    this.toolTitle = element('h2', '', 'Pen selection'); this.help = element('p', 'vse-help');
    this.sizeInput = element('input'); this.sizeInput.type = 'range';
    this.sizeInput.min = '1'; this.sizeInput.max = '400'; this.sizeInput.value = this.brushSize;
    this.sizeInput.setAttribute('aria-label', 'Brush size in image pixels');
    this.sizeValue = element('output', '', this.brushSize + ' px');
    const sizeLabel = element('label', 'vse-field');
    sizeLabel.append(element('span', '', 'Brush size'), this.sizeInput, this.sizeValue);
    this.sizeInput.addEventListener('input', () => { this.brushSize = Number(this.sizeInput.value); this.sizeValue.value = this.brushSize + ' px'; this.draw(); });
    const overlayLabel = element('label', 'vse-field');
    const opacity = element('input'); opacity.type = 'range'; opacity.min = '0'; opacity.max = '80'; opacity.value = '35';
    opacity.setAttribute('aria-label', 'Selection overlay opacity');
    opacity.addEventListener('input', () => { this.opacity = Number(opacity.value) / 100; this.draw(); });
    overlayLabel.append(element('span', '', 'Selection visibility'), opacity);
    this.undoButton = button('Undo', 'Undo selection change (Ctrl+Z)', () => this.undo());
    this.redoButton = button('Redo', 'Redo selection change (Ctrl+Shift+Z)', () => this.redo());
    const history = element('div', 'vse-pair'); history.append(this.undoButton, this.redoButton);
    const clear = button('Clear selection', 'Clear the entire selection', () => {
      this.brushContext.clearRect(0, 0, this.width, this.height);
      this.paths = []; this.activePath = null; this.changed(true); this.checkpoint(); this.draw();
    });
    const guide = element('div', 'vse-guide');
    guide.append(element('strong', '', 'Select here. Generate in the workflow.'), element('p', '', 'Cover the area you want to replace, including room for the new shape. Save the selection, then edit the prompt and press Run in ComfyUI.'));
    inspector.append(this.toolTitle, this.help, sizeLabel, overlayLabel, history, clear, guide);
    const footer = element('footer', 'vse-footer');
    this.status = element('span', 'vse-status', 'Ready'); this.status.setAttribute('role', 'status');
    this.zoomLabel = element('output', 'vse-zoom', '100%');
    footer.append(this.status, button('-', 'Zoom out', () => this.zoom(this.viewport.scale / 1.25)),
      this.zoomLabel, button('+', 'Zoom in', () => this.zoom(this.viewport.scale * 1.25)),
      button('Fit', 'Fit the whole image', () => this.fit()),
      button('100%', 'View image at actual size', () => this.zoom(1)));
    this.dialog.append(header, rail, this.stage, inspector, footer); document.body.append(this.dialog);
    for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'pointerleave']) this.view.addEventListener(type, event => this.pointer(type, event));
    this.view.addEventListener('wheel', event => {
      event.preventDefault(); event.stopPropagation();
      this.zoom(this.viewport.scale * Math.exp(-Math.max(-200, Math.min(200, event.deltaY)) * .0025), this.screen(event));
    }, { passive: false });
    this.view.addEventListener('contextmenu', event => event.preventDefault());
    this.view.addEventListener('dblclick', () => { if (this.tool === 'pen') this.closePath(); });
    const keydown = event => this.key(event);
    const keyup = event => { if (event.code === 'Space') { this.space = false; this.draw(); } };
    window.addEventListener('keydown', keydown, true); window.addEventListener('keyup', keyup, true);
    this.dispose.push(() => window.removeEventListener('keydown', keydown, true), () => window.removeEventListener('keyup', keyup, true));
  }
  resize(initial = false) {
    const rect = this.stage.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    const oldWidth = this.screenWidth || rect.width, oldHeight = this.screenHeight || rect.height;
    this.screenWidth = rect.width; this.screenHeight = rect.height; this.dpr = window.devicePixelRatio || 1;
    this.view.width = Math.round(rect.width * this.dpr); this.view.height = Math.round(rect.height * this.dpr);
    if (initial) this.fit();
    else { this.viewport.x += (rect.width - oldWidth) / 2; this.viewport.y += (rect.height - oldHeight) / 2; this.draw(); }
  }
  fit() { this.viewport = fitView(this.screenWidth, this.screenHeight, this.width, this.height); this.draw(); }
  zoom(scale, point = { x: this.screenWidth / 2, y: this.screenHeight / 2 }) {
    this.viewport = zoomView(this.viewport, Math.max(.005, Math.min(32, scale)), point.x, point.y); this.draw();
  }
  screen(event) { const r = this.view.getBoundingClientRect(); return { x: event.clientX - r.left, y: event.clientY - r.top }; }
  native(point) { return imagePoint(this.viewport, point.x, point.y); }
  inside(p) { return p.x >= 0 && p.y >= 0 && p.x <= this.width && p.y <= this.height; }
  setTool(tool) {
    this.tool = tool;
    for (const [key, b] of this.toolButtons) b.setAttribute('aria-pressed', String(key === tool));
    this.toolTitle.textContent = {pen:'Pen selection',brush:'Brush selection',eraser:'Erase selection',rect:'Rectangle selection',pan:'Hand tool'}[tool];
    this.help.textContent = {pen:'Click to add a point. Drag to curve it. Click the first point or press Enter to close. Drag anchors or handles to refine.',brush:'Paint to add to the selection. Use [ and ] to resize the brush.',eraser:'Paint to remove from the selection. Erasing a pen shape converts it to a painted selection; Undo restores the path.',rect:'Drag to add a rectangle. Hold Alt to subtract.',pan:'Drag to move the image. Space + drag works from every tool. Scroll to zoom at the cursor.'}[tool];
    this.draw();
  }
  key(event) {
    if (!this.dialog.open) return;
    if (event.key === 'Tab') return;
    if (event.target instanceof HTMLInputElement) { event.stopPropagation(); return; }
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); this.close(); return; }
    if (this.busy) return;
    const k = event.key.toLowerCase();
    const tool = TOOLS.find(t => t[2].toLowerCase() === k);
    if (!tool && ![' ', 'Enter', '[', ']', 'z', 'y'].includes(event.key) && !['z','y'].includes(k)) return;
    event.stopImmediatePropagation();
    if ((event.ctrlKey || event.metaKey) && k === 'z') { event.preventDefault(); event.shiftKey ? this.redo() : this.undo(); return; }
    if ((event.ctrlKey || event.metaKey) && k === 'y') { event.preventDefault(); this.redo(); return; }
    if (event.code === 'Space') { event.preventDefault(); this.space = true; this.draw(); return; }
    if (event.key === 'Enter') { event.preventDefault(); this.closePath(); return; }
    if (k === '[' || k === ']') {
      this.brushSize = Math.max(1, Math.min(400, this.brushSize + (k === '[' ? -8 : 8)));
      this.sizeInput.value = this.brushSize; this.sizeValue.value = this.brushSize + ' px'; this.draw(); return;
    }
    if (tool) { event.preventDefault(); this.setTool(tool[0]); }
  }
  pointer(type, event) {
    event.stopPropagation();
    const screen = this.screen(event), p = this.native(screen); this.cursor = this.inside(p) ? p : null;
    if (type === 'pointerleave' && !this.drag) { this.cursor = null; this.draw(); return; }
    if (type === 'pointerdown') {
      if (this.busy) return;
      this.stage.focus(); event.preventDefault(); this.view.setPointerCapture(event.pointerId);
      if (event.button === 1 || this.space || this.tool === 'pan') {
        this.drag = { kind: 'pan', start: screen, viewport: { ...this.viewport } }; this.draw(); return;
      }
      if (event.button !== 0 || !this.inside(p)) return;
      if (this.tool === 'pen') this.penDown(p, event);
      else if (this.tool === 'rect') {
        if (event.altKey) this.flattenPaths();
        this.drag = { kind: 'rect', start: p, end: p, subtract: event.altKey };
      } else {
        if (this.tool === 'eraser') this.flattenPaths();
        this.drag = { kind: 'brush', last: p, subtract: this.tool === 'eraser' }; this.stroke(p, p, this.drag.subtract);
      }
    } else if (type === 'pointermove' && this.drag) {
      const d = this.drag;
      if (d.kind === 'pan') this.viewport = { ...d.viewport, x: d.viewport.x + screen.x - d.start.x, y: d.viewport.y + screen.y - d.start.y };
      else if (d.kind === 'brush') { this.stroke(d.last, p, d.subtract); d.last = p; }
      else if (d.kind === 'rect') d.end = p;
      else if (d.kind === 'new') { d.point.out = { ...p }; d.point.in = { x: 2*d.point.x-p.x, y: 2*d.point.y-p.y }; this.changed(); }
      else if (d.kind === 'anchor') {
        const dx = p.x-d.point.x, dy = p.y-d.point.y; d.point.x = p.x; d.point.y = p.y;
        for (const h of ['in','out']) { d.point[h].x += dx; d.point[h].y += dy; } this.changed();
      } else if (d.kind === 'handle') {
        d.point[d.handle] = { ...p };
        if (!event.altKey) d.point[d.handle === 'in' ? 'out' : 'in'] = { x: 2*d.point.x-p.x, y: 2*d.point.y-p.y };
        this.changed();
      }
    } else if ((type === 'pointerup' || type === 'pointercancel') && this.drag) {
      const d = this.drag;
      if (d.kind === 'rect') {
        const c = this.brushContext;
        c.save(); c.globalCompositeOperation = d.subtract ? 'destination-out' : 'source-over'; c.fillStyle = '#fff';
        c.fillRect(Math.min(d.start.x,d.end.x), Math.min(d.start.y,d.end.y), Math.abs(d.end.x-d.start.x), Math.abs(d.end.y-d.start.y));
        c.restore(); this.changed(true);
      }
      this.drag = null; if (d.kind !== 'pan') this.checkpoint();
      if (this.view.hasPointerCapture(event.pointerId)) this.view.releasePointerCapture(event.pointerId);
    }
    this.draw();
  }
  penDown(p, event) {
    const near = q => Math.hypot(q.x-p.x,q.y-p.y) < 8/this.viewport.scale;
    if (this.activePath && !this.activePath.closed && this.activePath.points.length >= 3 && near(this.activePath.points[0])) { this.closePath(); return; }
    for (const path of [...this.paths].reverse()) for (const point of path.points) {
      for (const handle of ['in','out']) {
        if (Math.hypot(point[handle].x-point.x,point[handle].y-point.y) > 2/this.viewport.scale && near(point[handle])) {
          this.activePath=path; this.drag={kind:'handle',point,handle}; return;
        }
      }
      if (near(point)) { this.activePath=path; this.drag={kind:'anchor',point}; return; }
    }
    if (event.detail > 1) { this.closePath(); return; }
    if (!this.activePath || this.activePath.closed) { this.activePath={points:[],closed:false}; this.paths.push(this.activePath); }
    const point={x:p.x,y:p.y,in:{...p},out:{...p}};
    this.activePath.points.push(point); this.drag={kind:'new',point}; this.changed();
  }
  closePath() {
    if (!this.activePath || this.activePath.closed) return;
    if (this.activePath.points.length < 3) { this.setStatus('Add at least three points to close the selection.'); return; }
    this.activePath.closed=true; this.activePath=null; this.changed(); this.checkpoint(); this.draw();
  }
  trace(context, path) {
    const points=path.points; if (!points.length) return;
    context.beginPath(); context.moveTo(points[0].x,points[0].y);
    for (let i=1;i<points.length;i++) { const a=points[i-1], b=points[i]; context.bezierCurveTo(a.out.x,a.out.y,b.in.x,b.in.y,b.x,b.y); }
    if (path.closed) { const a=points.at(-1), b=points[0]; context.bezierCurveTo(a.out.x,a.out.y,b.in.x,b.in.y,b.x,b.y); context.closePath(); }
  }
  changed(raster = false) { this.maskDirty=true; if (raster) this.rasterDirty=true; this.setStatus('Selection changed'); }
  stroke(a,b,subtract) {
    const c=this.brushContext; c.save(); c.globalCompositeOperation=subtract?'destination-out':'source-over'; c.strokeStyle='#fff'; c.fillStyle='#fff';
    c.lineWidth=this.brushSize; c.lineCap='round'; c.lineJoin='round';
    c.beginPath(); c.moveTo(a.x,a.y); c.lineTo(b.x,b.y); c.stroke();
    c.beginPath(); c.arc(b.x,b.y,this.brushSize/2,0,2*Math.PI); c.fill(); c.restore(); this.changed(true);
  }
  updateMask() {
    if (!this.maskDirty) return;
    const c=this.selection.getContext('2d'); c.clearRect(0,0,this.width,this.height); c.fillStyle='#fff';
    for (const path of this.paths) if (path.closed) { this.trace(c,path); c.fill(); }
    c.drawImage(this.brush,0,0);
    const o=this.overlay.getContext('2d'); o.clearRect(0,0,this.width,this.height); o.drawImage(this.selection,0,0);
    o.globalCompositeOperation='source-in'; o.fillStyle='#f04d65'; o.fillRect(0,0,this.width,this.height); o.globalCompositeOperation='source-over';
    this.maskDirty=false;
  }
  flattenPaths() {
    if (!this.paths.length) return;
    this.updateMask(); this.brushContext.clearRect(0,0,this.width,this.height); this.brushContext.drawImage(this.selection,0,0);
    this.paths=[]; this.activePath=null; this.changed(true);
  }
  checkpoint() {
    if (this.rasterDirty || !this.rasterSnapshot) this.rasterSnapshot=this.brushContext.getImageData(0,0,this.width,this.height);
    this.rasterDirty=false; this.history.push({paths:structuredClone(this.paths),raster:this.rasterSnapshot});
    while (this.history.length>20 || (this.history.length>2 && [...new Set(this.history.map(h=>h.raster))].reduce((n,r)=>n+r.data.byteLength,0)>128*1024*1024)) this.history.shift();
    this.future=[]; this.historyButtons();
  }
  restore(snapshot) {
    this.paths=structuredClone(snapshot.paths); this.activePath=this.paths.find(p=>!p.closed)||null;
    this.brushContext.putImageData(snapshot.raster,0,0); this.rasterSnapshot=snapshot.raster; this.rasterDirty=false; this.maskDirty=true;
    this.historyButtons(); this.draw();
  }
  undo() { if(this.history.length<2)return; this.future.push(this.history.pop()); this.restore(this.history.at(-1)); }
  redo() { const next=this.future.pop();if(next){this.history.push(next);this.restore(next);} }
  historyButtons() { this.undoButton.disabled=this.history.length<2; this.redoButton.disabled=!this.future.length; }
  draw() {
    if (this.frame || !this.dialog?.open) return;
    this.frame=requestAnimationFrame(()=>{this.frame=null;this.render();});
  }
  render() {
    this.updateMask(); const c=this.context, v=this.viewport, d=this.dpr;
    c.setTransform(d,0,0,d,0,0); c.clearRect(0,0,this.screenWidth,this.screenHeight);
    c.save(); c.translate(v.x,v.y); c.scale(v.scale,v.scale);
    c.imageSmoothingEnabled=true; c.imageSmoothingQuality='high'; c.drawImage(this.image,0,0,this.width,this.height);
    c.save(); c.globalAlpha=this.opacity; c.drawImage(this.overlay,0,0); c.restore();
    c.lineWidth=1/v.scale; c.strokeStyle='#d5f6a2';
    if (this.tool==='pen') for (const path of this.paths) {
      this.trace(c,path); c.stroke();
      for (const p of path.points) {
        if (path===this.activePath) for (const h of ['in','out']) {
          c.beginPath(); c.moveTo(p.x,p.y); c.lineTo(p[h].x,p[h].y); c.stroke();
          c.beginPath(); c.arc(p[h].x,p[h].y,3/v.scale,0,Math.PI*2); c.fillStyle='#d5f6a2'; c.fill();
        }
        c.fillStyle='#151a1c'; c.fillRect(p.x-4/v.scale,p.y-4/v.scale,8/v.scale,8/v.scale); c.strokeRect(p.x-4/v.scale,p.y-4/v.scale,8/v.scale,8/v.scale);
      }
    }
    if (this.drag?.kind==='rect') {
      const {start:a,end:b}=this.drag; c.fillStyle='rgba(240,77,101,.25)'; c.fillRect(a.x,a.y,b.x-a.x,b.y-a.y); c.strokeRect(a.x,a.y,b.x-a.x,b.y-a.y);
    }
    if (this.cursor && !this.space && ['brush','eraser'].includes(this.tool)) {
      c.beginPath();c.arc(this.cursor.x,this.cursor.y,this.brushSize/2,0,Math.PI*2);c.strokeStyle='#fff';c.lineWidth=1/v.scale;c.stroke();
    }
    c.restore();
    this.stage.style.cursor=this.drag?.kind==='pan'?'grabbing':(this.space||this.tool==='pan')?'grab':['brush','eraser'].includes(this.tool)?'none':'crosshair';
    this.zoomLabel.value=Number((v.scale*100).toFixed(1))+'%';
  }
  async png(source) {
    const flattened=canvas(this.width,this.height), context=flattened.getContext('2d');
    context.fillStyle='#000'; context.fillRect(0,0,this.width,this.height); context.drawImage(source,0,0);
    const blob=await new Promise(resolve=>flattened.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Could not encode the selection. Try again.');
    return blob;
  }
  async save() {
    if(this.busy)return;
    if(this.paths.some(p=>!p.closed)){this.setStatus('Close the pen path with Enter, or Undo it before saving.');return;}
    this.busy=true;this.dialog.querySelectorAll('button,input').forEach(el=>el.disabled=true);this.setStatus('Saving selection...');
    try {
      this.updateMask();
      const mask=await upload(await this.png(this.selection),'selection.png');
      const brush=await upload(await this.png(this.brush),'brush.png');
      this.stateWidget.value=JSON.stringify({...this.saved,version:2,source:this.source,mask_file:mask,brush_file:brush,paths:this.paths,brush_size:this.brushSize,expand:{left:0,right:0,top:0,bottom:0}});
      app.graph.setDirtyCanvas(true,true);this.close(true);
    } catch(error) {
      this.busy=false;this.dialog.querySelectorAll('button,input').forEach(el=>el.disabled=false);this.historyButtons();this.setStatus(error.message);
    }
  }
  setStatus(text) { if(this.status)this.status.textContent=text; }
  close(force=false) {
    if(this.busy&&!force)return;
    if(this.frame)cancelAnimationFrame(this.frame);
    this.dispose.splice(0).forEach(fn=>fn());this.dialog?.close();this.dialog?.remove();
    if(this.node[EXT]?.editor===this)this.node[EXT].editor=null;
  }
}

function hideState(node) {
  const widget=node.widgets?.find(w=>w.name==='editor_state');if(!widget)return;
  widget.type='hidden';widget.computeSize=()=>[0,-4];
  const dom=widget.element||widget.inputEl;if(dom)dom.style.display='none';
}
async function open(node) {
  if(node[EXT]?.editor){node[EXT].editor.stage?.focus();return;}
  const editor=new SelectionEditor(node);node[EXT].editor=editor;
  try { await editor.open(); }
  catch(error){editor.close(true);app.extensionManager.toast.add({severity:'error',title:'Selection editor',message:error.message});}
}
app.registerExtension({
  name:EXT,
  beforeRegisterNodeDef(type,data) {
    if(data.name!=='VallpaperShotEditor')return;
    const created=type.prototype.onNodeCreated,configured=type.prototype.onConfigure,removed=type.prototype.onRemoved;
    type.prototype.onNodeCreated=function(...args){
      created?.apply(this,args);this[EXT]={editor:null};hideState(this);
      const file=element('input');file.type='file';file.accept='image/*';
      file.addEventListener('change',async()=>{
        const chosen=file.files?.[0];if(!chosen)return;
        try{
          const value=await upload(chosen,chosen.name),imageWidget=this.widgets.find(w=>w.name==='image');
          const choices=imageWidget.options?.values;if(Array.isArray(choices)&&!choices.includes(value))choices.push(value);
          imageWidget.value=value;this.widgets.find(w=>w.name==='editor_state').value=JSON.stringify({version:2,source:value,paths:[]});app.graph.setDirtyCanvas(true,true);
        }catch(error){app.extensionManager.toast.add({severity:'error',title:'Source upload',message:error.message});}
        file.value='';
      });
      const uploader=this.addWidget('button','Upload source image',null,()=>file.click(),{});uploader.serialize=false;
      const editor=this.addWidget('button','Open selection editor',null,()=>open(this),{});editor.serialize=false;
    };
    type.prototype.onConfigure=function(...args){configured?.apply(this,args);hideState(this);};
    type.prototype.onRemoved=function(...args){this[EXT]?.editor?.close(true);removed?.apply(this,args);};
  },
});
