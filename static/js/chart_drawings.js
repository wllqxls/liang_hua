class ChartDrawingController {
    constructor(options) {
        this.overlay = options.overlay;
        this.toolbar = options.toolbar;
        this.styleToolbar = options.styleToolbar;
        this.styleDragHandle = options.styleDragHandle;
        this.chartWrap = options.chartWrap;
        this.chartContainer = options.chartContainer;
        this.toggle = options.toggle;
        this.colorInput = options.colorInput;
        this.widthInput = options.widthInput;
        this.styleInput = options.styleInput;
        this.chart = null;
        this.series = null;
        this.contextKey = null;
        this.contextTimeframe = '5m';
        this.drawings = [];
        this.history = [];
        this.selectedId = null;
        this.tool = 'select';
        this.pendingPoint = null;
        this.drag = null;
        this.styleDrag = null;
        this.risk = null;
        this.renderRoot = null;
        this.redrawFrame = null;
        this.chartInteractionActive = false;
        this.clipId = `drawing-clip-${Math.random().toString(16).slice(2)}`;
        this._bindControls();
    }

    attach(chart, series) {
        this.chart = chart;
        this.series = series;
        chart.timeScale().subscribeVisibleLogicalRangeChange(() => this._scheduleRedraw());
        this.chartContainer.addEventListener('pointerdown', () => { this.chartInteractionActive = true; }, { passive: true });
        this.chartContainer.addEventListener('pointermove', () => {
            if (this.chartInteractionActive) this._scheduleRedraw();
        }, { passive: true });
        ['wheel', 'dblclick', 'touchmove'].forEach(eventName => {
            this.chartContainer.addEventListener(eventName, () => this._scheduleRedraw(), { passive: true });
        });
        this.chartWrap.addEventListener('wheel', event => this._handlePriceWheel(event), {
            capture: true,
            passive: false,
        });
        window.addEventListener('pointerup', () => {
            if (this.chartInteractionActive) this._scheduleRedraw();
            this.chartInteractionActive = false;
        }, { passive: true });
        window.addEventListener('resize', () => this._scheduleRedraw());
        this.redraw();
    }

    setContext({ year, symbol, timeframe }) {
        this.contextTimeframe = timeframe;
        const key = `manual-chart-drawings:v2:${year}:${symbol}`;
        if (key === this.contextKey) {
            this.redraw();
            return;
        }
        this._save();
        this.contextKey = key;
        this.selectedId = null;
        this.pendingPoint = null;
        this.history = [];
        try {
            const storage = this._storage();
            const shared = JSON.parse(storage?.getItem(key) || 'null');
            const stored = Array.isArray(shared)
                ? shared
                : this._migrateTimeframeDrawings(storage, year, symbol);
            this.drawings = stored.map(drawing => this._normalizeStoredDrawing(drawing));
            if (!Array.isArray(shared) && this.drawings.length) this._save();
        } catch (error) {
            this.drawings = [];
        }
        this.redraw();
    }

    setRisk(risk) {
        this.risk = risk || null;
        this.redraw();
    }

    setOpen(open) {
        this.toolbar.classList.toggle('hidden', !open);
        this.overlay.classList.toggle('drawing-active', open);
        this.toggle.classList.toggle('active', open);
        this.toggle.setAttribute('aria-expanded', String(open));
        if (!open) {
            this.pendingPoint = null;
            this.drag = null;
        }
        this._syncStyleToolbarVisibility();
        this.redraw();
    }

    redraw() {
        if (!this.chart || !this.series) return;
        const width = this.overlay.clientWidth;
        const height = this.overlay.clientHeight;
        if (!width || !height) return;
        this.overlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
        this.overlay.replaceChildren();
        this.renderRoot = null;
        const bounds = this._plotBounds(width, height);
        const definitions = this._svg('defs', {}, this.overlay);
        const clipPath = this._svg('clipPath', { id: this.clipId }, definitions);
        this._svg('rect', bounds, clipPath);
        if (!this.toolbar.classList.contains('hidden') && this.tool !== 'select') {
            this._svg('rect', {
                ...bounds,
                fill: 'transparent',
                style: 'pointer-events:all',
                'data-drawing-capture': 'true',
            }, this.overlay);
        }
        this.renderRoot = this._svg('g', { 'clip-path': `url(#${this.clipId})` }, this.overlay);
        this._renderRisk(bounds);
        this.drawings.forEach(drawing => this._renderDrawing(drawing, bounds));
        if (this.pendingPoint) this._renderPendingPoint(this.pendingPoint);
        this.renderRoot = null;
    }

    _bindControls() {
        this.toggle.addEventListener('click', () => {
            this.setOpen(this.toolbar.classList.contains('hidden'));
        });
        this.toolbar.querySelectorAll('[data-draw-tool]').forEach(button => {
            button.addEventListener('click', () => this._selectTool(button.dataset.drawTool));
        });
        this.toolbar.querySelector('#draw-undo').addEventListener('click', () => this._undo());
        this.toolbar.querySelector('#draw-delete').addEventListener('click', () => this._deleteSelected());
        this.toolbar.querySelector('#draw-clear').addEventListener('click', () => this._clear());
        this.colorInput.addEventListener('change', () => this._applySelectedStyle());
        this.widthInput.addEventListener('change', () => this._applySelectedStyle());
        this.styleInput.addEventListener('change', () => this._applySelectedStyle());
        this.styleDragHandle.addEventListener('pointerdown', event => this._startStyleDrag(event));
        window.addEventListener('pointermove', event => this._moveStyleToolbar(event));
        window.addEventListener('pointerup', () => { this.styleDrag = null; });
        this.overlay.addEventListener('pointerdown', event => this._pointerDown(event));
        this.overlay.addEventListener('pointermove', event => this._pointerMove(event));
        this.overlay.addEventListener('pointerup', event => this._pointerUp(event));
        this.overlay.addEventListener('pointercancel', event => this._pointerUp(event));
        window.addEventListener('keydown', event => {
            if (this.toolbar.classList.contains('hidden')) return;
            if (event.key === 'Escape') {
                this.pendingPoint = null;
                this.drag = null;
                this.redraw();
            }
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
                event.preventDefault();
                this._undo();
            }
            if (event.key === 'Delete' || event.key === 'Backspace') this._deleteSelected();
        });
        this._selectTool('select');
    }

    _selectTool(tool) {
        this.tool = tool;
        this.pendingPoint = null;
        if (tool !== 'select') this.selectedId = null;
        this.toolbar.querySelectorAll('[data-draw-tool]').forEach(button => {
            button.classList.toggle('active', button.dataset.drawTool === tool);
        });
        this._syncStyleToolbarVisibility();
        this.redraw();
    }

    _pointerDown(event) {
        if (this.toolbar.classList.contains('hidden')) return;
        const endpoint = event.target.dataset.endpoint;
        const drawingId = event.target.dataset.drawingId;
        if (endpoint && drawingId) {
            this._startDrag(event, drawingId, Number(endpoint));
            return;
        }
        if (drawingId) {
            this.selectedId = drawingId;
            this._loadSelectedStyle();
            this._startDrag(event, drawingId, null);
            return;
        }
        const point = this._eventPoint(event);
        if (!point) return;
        if (this.tool === 'select') {
            this.selectedId = null;
            this._syncStyleToolbarVisibility();
            this.redraw();
            return;
        }
        if (['horizontal', 'horizontalRay', 'vertical'].includes(this.tool)) {
            this._pushHistory();
            const drawing = this._newDrawing(this.tool, [point]);
            this.drawings.push(drawing);
            this.selectedId = drawing.id;
            this._save();
            this._selectTool('select');
            return;
        }
        if (!this.pendingPoint) {
            this.pendingPoint = point;
            this.redraw();
            return;
        }
        this._pushHistory();
        const drawing = this._newDrawing(this.tool, [this.pendingPoint, point]);
        this.drawings.push(drawing);
        this.selectedId = drawing.id;
        this._save();
        this._selectTool('select');
    }

    _startDrag(event, drawingId, endpoint) {
        const drawing = this.drawings.find(item => item.id === drawingId);
        if (!drawing) return;
        event.preventDefault();
        this._pushHistory();
        this.selectedId = drawingId;
        this._loadSelectedStyle();
        this.drag = {
            drawingId,
            endpoint,
            startX: event.clientX,
            startY: event.clientY,
            points: drawing.points.map(point => ({ ...point })),
        };
        this.overlay.setPointerCapture(event.pointerId);
        this.redraw();
    }

    _pointerMove(event) {
        if (!this.drag) return;
        const drawing = this.drawings.find(item => item.id === this.drag.drawingId);
        if (!drawing) return;
        if (this.drag.endpoint !== null) {
            const point = this._eventPoint(event);
            if (point) drawing.points[this.drag.endpoint] = point;
        } else {
            const dx = event.clientX - this.drag.startX;
            const dy = event.clientY - this.drag.startY;
            drawing.points = this.drag.points.map(point => this._shiftPoint(point, dx, dy) || point);
        }
        this.redraw();
    }

    _pointerUp(event) {
        if (!this.drag) return;
        if (this.overlay.hasPointerCapture(event.pointerId)) this.overlay.releasePointerCapture(event.pointerId);
        this.drag = null;
        this._save();
        this.redraw();
    }

    _newDrawing(type, points) {
        return {
            id: `drawing-${Date.now()}-${Math.random().toString(16).slice(2)}`,
            type,
            points,
            color: this.colorInput.value,
            width: Number(this.widthInput.value),
            style: this.styleInput.value,
        };
    }

    _eventPoint(event) {
        const bounds = this.overlay.getBoundingClientRect();
        const x = event.clientX - bounds.left;
        const y = event.clientY - bounds.top;
        const time = this.chart.timeScale().coordinateToTime(x);
        const price = this.series.coordinateToPrice(y);
        if (time == null || price == null || typeof time !== 'number') return null;
        return { time, price };
    }

    _shiftPoint(point, dx, dy) {
        const x = this._timeToCoordinate(point.time);
        const y = this.series.priceToCoordinate(point.price);
        if (x == null || y == null) return null;
        const time = this.chart.timeScale().coordinateToTime(x + dx);
        const price = this.series.coordinateToPrice(y + dy);
        if (time == null || price == null || typeof time !== 'number') return null;
        return { time, price };
    }

    _coordinates(point) {
        const x = this._timeToCoordinate(point.time);
        const y = this.series.priceToCoordinate(point.price);
        return x == null || y == null ? null : { x, y };
    }

    _renderDrawing(drawing, bounds) {
        const points = drawing.points.map(point => this._coordinates(point));
        if (points.some(point => point == null)) return;
        const right = bounds.x + bounds.width;
        const bottom = bounds.y + bounds.height;
        const selected = drawing.id === this.selectedId;
        const common = {
            stroke: drawing.color,
            'stroke-width': selected ? Number(drawing.width) + 1 : drawing.width,
            'stroke-dasharray': this._dashArray(drawing.style),
            fill: 'none',
            'data-drawing-id': drawing.id,
            style: 'pointer-events:stroke;cursor:move',
        };
        if (drawing.type === 'ray') {
            const end = this._rayEnd(points[0], points[1], bounds);
            this._svg('line', { ...common, x1: points[0].x, y1: points[0].y, x2: end.x, y2: end.y });
        } else if (drawing.type === 'horizontal') {
            this._svg('line', { ...common, x1: bounds.x, y1: points[0].y, x2: right, y2: points[0].y });
        } else if (drawing.type === 'horizontalRay') {
            this._svg('line', { ...common, x1: points[0].x, y1: points[0].y, x2: right, y2: points[0].y });
        } else if (drawing.type === 'vertical') {
            this._svg('line', { ...common, x1: points[0].x, y1: bounds.y, x2: points[0].x, y2: bottom });
        } else if (drawing.type === 'rectangle') {
            this._svg('rect', {
                ...common,
                x: Math.min(points[0].x, points[1].x), y: Math.min(points[0].y, points[1].y),
                width: Math.abs(points[1].x - points[0].x), height: Math.abs(points[1].y - points[0].y),
                fill: `${drawing.color}1f`, style: 'pointer-events:all;cursor:move',
            });
        }
        if (selected) points.forEach((point, index) => this._svg('circle', {
            cx: point.x, cy: point.y, r: 5, fill: '#ffffff', stroke: drawing.color, 'stroke-width': 2,
            'data-drawing-id': drawing.id, 'data-endpoint': index, style: 'pointer-events:all;cursor:grab',
        }));
    }

    _renderPendingPoint(point) {
        const coordinate = this._coordinates(point);
        if (!coordinate) return;
        this._svg('circle', { cx: coordinate.x, cy: coordinate.y, r: 5, fill: this.colorInput.value });
    }

    _renderRisk(bounds) {
        if (!this.risk) return;
        const startX = this.chart.timeScale().timeToCoordinate(this.risk.entry_time);
        const rawEndX = this.chart.timeScale().timeToCoordinate(this.risk.end_time);
        const entryY = this.series.priceToCoordinate(this.risk.fill_price);
        const targetY = this.series.priceToCoordinate(this.risk.target_price);
        const stopY = this.series.priceToCoordinate(this.risk.stop_price);
        if ([startX, rawEndX, entryY, targetY, stopY].some(value => value == null)) return;
        const endX = Math.min(bounds.x + bounds.width, Math.max(startX + 12, rawEndX + 8));
        const boxWidth = Math.max(12, endX - startX);
        this._riskRect(startX, Math.min(entryY, targetY), boxWidth, Math.abs(targetY - entryY), '#21c58b', 'rgba(33,197,139,.20)');
        this._riskRect(startX, Math.min(entryY, stopY), boxWidth, Math.abs(stopY - entryY), '#ff5f91', 'rgba(255,95,145,.22)');
        this._svg('line', { x1: startX, y1: entryY, x2: endX, y2: entryY, stroke: '#4b9cff', 'stroke-width': 1.5, 'stroke-dasharray': '5 4', style: 'pointer-events:none' });
        const profitPct = Math.abs((this.risk.target_price / this.risk.fill_price - 1) * 100).toFixed(2);
        const stopPct = Math.abs((this.risk.stop_price / this.risk.fill_price - 1) * 100).toFixed(2);
        this._riskLabel(startX + 6, (entryY + targetY) / 2, `止盈 ${profitPct}%`, '#b9ffe4');
        this._riskLabel(startX + 6, (entryY + stopY) / 2, `止损 ${stopPct}%`, '#ffd0df');
    }

    _riskRect(x, y, width, height, stroke, fill) {
        this._svg('rect', { x, y, width, height: Math.max(1, height), fill, stroke, 'stroke-width': 1, style: 'pointer-events:none' });
    }

    _riskLabel(x, y, text, fill) {
        const node = this._svg('text', { x, y, fill, 'font-size': 11, 'font-weight': 700, style: 'pointer-events:none' });
        node.textContent = text;
    }

    _svg(name, attributes, parent = this.renderRoot || this.overlay) {
        const node = document.createElementNS('http://www.w3.org/2000/svg', name);
        Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
        parent.appendChild(node);
        return node;
    }

    _dashArray(style) {
        if (style === 'dash') return '8 5';
        if (style === 'dot') return '2 5';
        return '';
    }

    _rayEnd(start, direction, bounds) {
        const dx = direction.x - start.x;
        const dy = direction.y - start.y;
        const right = bounds.x + bounds.width;
        const bottom = bounds.y + bounds.height;
        const candidates = [];
        if (dx > 0) candidates.push((right - start.x) / dx);
        if (dx < 0) candidates.push((bounds.x - start.x) / dx);
        if (dy > 0) candidates.push((bottom - start.y) / dy);
        if (dy < 0) candidates.push((bounds.y - start.y) / dy);
        const scale = Math.min(...candidates.filter(value => value >= 1));
        if (!Number.isFinite(scale)) return direction;
        return { x: start.x + dx * scale, y: start.y + dy * scale };
    }

    _plotBounds(fallbackWidth, fallbackHeight) {
        const firstRow = this.chartContainer.querySelector('table')?.rows?.[0];
        const paneCell = firstRow?.cells?.[1];
        if (!paneCell) return { x: 0, y: 0, width: fallbackWidth, height: fallbackHeight };
        const overlayBounds = this.overlay.getBoundingClientRect();
        const paneBounds = paneCell.getBoundingClientRect();
        return {
            x: paneBounds.left - overlayBounds.left,
            y: paneBounds.top - overlayBounds.top,
            width: paneBounds.width,
            height: paneBounds.height,
        };
    }

    _handlePriceWheel(event) {
        if (!this.chart || !this.series || event.deltaY === 0) return;
        const firstRow = this.chartContainer.querySelector('table')?.rows?.[0];
        const paneCell = firstRow?.cells?.[1];
        if (!firstRow || !paneCell) return;
        const priceRowBounds = firstRow.getBoundingClientRect();
        const chartBounds = this.chartContainer.getBoundingClientRect();
        const insidePriceRow = event.clientX >= chartBounds.left
            && event.clientX <= chartBounds.right
            && event.clientY >= priceRowBounds.top
            && event.clientY <= priceRowBounds.bottom;
        if (!insidePriceRow) return;

        event.preventDefault();
        event.stopPropagation();
        const priceScale = this.chart.priceScale('right');
        const range = priceScale.getVisibleRange();
        if (!range || !Number.isFinite(range.from) || !Number.isFinite(range.to) || range.to <= range.from) return;
        const paneBounds = paneCell.getBoundingClientRect();
        const cursorPrice = this.series.coordinateToPrice(event.clientY - paneBounds.top);
        const pivot = Number.isFinite(cursorPrice)
            ? Math.max(range.from, Math.min(range.to, cursorPrice))
            : (range.from + range.to) / 2;
        const deltaPixels = event.deltaMode === 1
            ? event.deltaY * 16
            : event.deltaMode === 2 ? event.deltaY * priceRowBounds.height : event.deltaY;
        const factor = Math.exp(Math.max(-240, Math.min(240, deltaPixels)) * 0.0015);
        const nextRange = {
            from: pivot - (pivot - range.from) * factor,
            to: pivot + (range.to - pivot) * factor,
        };
        if (!Number.isFinite(nextRange.from) || !Number.isFinite(nextRange.to) || nextRange.to <= nextRange.from) return;
        priceScale.setVisibleRange(nextRange);
        this._scheduleRedraw();
    }

    _scheduleRedraw() {
        if (this.redrawFrame !== null) cancelAnimationFrame(this.redrawFrame);
        this.redrawFrame = requestAnimationFrame(() => {
            this.redrawFrame = null;
            this.redraw();
        });
    }

    _timeToCoordinate(time) {
        const seconds = { '5m': 300, '15m': 900, '1h': 3600 }[this.contextTimeframe] || 300;
        return this.chart.timeScale().timeToCoordinate(Math.floor(time / seconds) * seconds);
    }

    _normalizeStoredDrawing(drawing) {
        if (drawing.type === 'trend') return { ...drawing, type: 'ray' };
        if (drawing.type === 'ray' && drawing.points?.length === 1) return { ...drawing, type: 'horizontalRay' };
        return drawing;
    }

    _migrateTimeframeDrawings(storage, year, symbol) {
        if (!storage) return [];
        const merged = [];
        const seen = new Set();
        ['5m', '15m', '1h'].forEach(timeframe => {
            const legacyKey = `manual-chart-drawings:v1:${year}:${symbol}:${timeframe}`;
            const legacy = JSON.parse(storage.getItem(legacyKey) || '[]');
            if (!Array.isArray(legacy)) return;
            legacy.forEach(drawing => {
                const identity = drawing.id || JSON.stringify(drawing);
                if (seen.has(identity)) return;
                seen.add(identity);
                merged.push(drawing);
            });
        });
        return merged;
    }

    _syncStyleToolbarVisibility() {
        const open = !this.toolbar.classList.contains('hidden');
        const shouldShow = open && (this.tool !== 'select' || this.selectedId !== null);
        this.styleToolbar.classList.toggle('hidden', !shouldShow);
    }

    _loadSelectedStyle() {
        const drawing = this.drawings.find(item => item.id === this.selectedId);
        if (drawing) {
            this.colorInput.value = drawing.color;
            this.widthInput.value = String(drawing.width);
            this.styleInput.value = drawing.style;
        }
        this._syncStyleToolbarVisibility();
    }

    _applySelectedStyle() {
        const drawing = this.drawings.find(item => item.id === this.selectedId);
        if (!drawing) return;
        this._pushHistory();
        drawing.color = this.colorInput.value;
        drawing.width = Number(this.widthInput.value);
        drawing.style = this.styleInput.value;
        this._save();
        this.redraw();
    }

    _startStyleDrag(event) {
        event.preventDefault();
        const toolbarBounds = this.styleToolbar.getBoundingClientRect();
        const wrapBounds = this.chartWrap.getBoundingClientRect();
        this.styleDrag = {
            startX: event.clientX,
            startY: event.clientY,
            left: toolbarBounds.left - wrapBounds.left,
            top: toolbarBounds.top - wrapBounds.top,
        };
        this.styleDragHandle.setPointerCapture(event.pointerId);
    }

    _moveStyleToolbar(event) {
        if (!this.styleDrag) return;
        const maxLeft = Math.max(0, this.chartWrap.clientWidth - this.styleToolbar.offsetWidth);
        const maxTop = Math.max(0, this.chartWrap.clientHeight - this.styleToolbar.offsetHeight);
        const left = Math.max(0, Math.min(maxLeft, this.styleDrag.left + event.clientX - this.styleDrag.startX));
        const top = Math.max(0, Math.min(maxTop, this.styleDrag.top + event.clientY - this.styleDrag.startY));
        this.styleToolbar.style.left = `${left}px`;
        this.styleToolbar.style.top = `${top}px`;
    }

    _pushHistory() {
        this.history.push(JSON.stringify(this.drawings));
        if (this.history.length > 50) this.history.shift();
    }

    _undo() {
        const previous = this.history.pop();
        if (previous == null) return;
        this.drawings = JSON.parse(previous);
        this.selectedId = null;
        this._syncStyleToolbarVisibility();
        this._save();
        this.redraw();
    }

    _deleteSelected() {
        if (!this.selectedId) return;
        this._pushHistory();
        this.drawings = this.drawings.filter(item => item.id !== this.selectedId);
        this.selectedId = null;
        this._syncStyleToolbarVisibility();
        this._save();
        this.redraw();
    }

    _clear() {
        if (!this.drawings.length) return;
        this._pushHistory();
        this.drawings = [];
        this.selectedId = null;
        this._syncStyleToolbarVisibility();
        this._save();
        this.redraw();
    }

    _save() {
        if (!this.contextKey) return;
        try {
            this._storage()?.setItem(this.contextKey, JSON.stringify(this.drawings));
        } catch (error) {
            // Drawing remains usable in memory when browser storage is unavailable.
        }
    }

    _storage() {
        try {
            return window.localStorage || null;
        } catch (error) {
            return null;
        }
    }
}

window.ChartDrawingController = ChartDrawingController;
