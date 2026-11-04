import { app } from '/scripts/app.js';
import { api } from '/scripts/api.js';
import { createMonitor } from './monitor.js';

app.registerExtension({
    name: 'dharani.prod.hardware',
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== 'VallpaperHardware') return;
        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = originalCreated?.apply(this, args);
            this.color = '#153b48';
            this.bgcolor = '#1b252b';
            const monitor = createMonitor((path, options) => api.fetchApi(path, options));
            const widget = this.addDOMWidget('hardware', 'vallpaper-hardware', monitor.element, {
                serialize: false,
            });
            widget.computeSize = () => [320, 330];
            this.setSize([350, 370]);
            const originalRemoved = this.onRemoved;
            this.onRemoved = function (...removedArgs) {
                monitor.dispose();
                return originalRemoved?.apply(this, removedArgs);
            };
            return result;
        };
    },
});
