class ChartDrawingController {
    constructor(options) {
        this.overlay = options.overlay;
        this.toolbar = options.toolbar;
        this.toggle = options.toggle;
        this.colorInput = options.colorInput;
        this.widthInput = options.widthInput;
        this.styleInput = options.styleInput;
        this.chart = null;
        this.series = null;
        this.contextKey = null;
        this.drawings = [];
        this.history = [];
        this.selectedId = null;
        this.tool = 'select';
        this.pendingPoint = null;
        this.drag = null;
        this.risk = null;
        this.priceLines = [];
        this._bindControls();
    }

    attach(chart, series) {
        this.chart = chart;
        this.series = series;
        chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.redraw());
        window.addEventListener('resize', () => this.redraw());
        this.redraw();
    }

    setContext({ year, symbol, timeframe }) {
        const key = `manual-chart-drawings:v1:${year}:${symbol}:${timeframe}`;
        if (key === this.contextKey) return;
        this._save();
        this.contextKey = key;
        this.selectedId = null;
        this.pendingPoint = null;
        this.history = [];
        try {
            const stored = JSON.parse(this._storage()?.getItem(key) || '[]');
            this.drawings = Array.isArray(stored) ? stored : [];
        } catch (error) {
            this.drawings = [];
        }
        this.redraw();
    }

    setRisk(risk) {
        this.risk = risk || null;
        this._syncPriceLines();
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
        this.redraw();
    }

    redraw() {
        if (!this.chart || !this.series) return;
        const width = this.overlay.clientWidth;
        const height = this.overlay.clientHeight;
        if (!width || !height) return;
        this.overlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
        this.overlay.replaceChildren();
        this._renderRisk(width);
        this.drawings.forEach(drawing => this._renderDrawing(drawing, width, height));
        if (this.pendingPoint) this._renderPendingPoint(this.pendingPoint);
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
            if (event.key === 'Delete' || event.key === 'Backspace') this._deleteSelected();
        });
        this._selectTool('select');
    }

    _selectTool(tool) {
        this.tool = tool;
        this.pendingPoint = null;
        this.toolbar.querySelectorAll('[data-draw-tool]').forEach(button => {
            button.classList.toggle('active', button.dataset.drawTool === tool);
        });
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
            this._startDrag(event, drawingId, null);
            return;
        }
        const point = this._eventPoint(event);
        if (!point) return;
        if (this.tool === 'select') {
            this.selectedId = null;
            this.redraw();
            return;
        }
        if (['horizontal', 'ray', 'vertical'].includes(this.tool)) {
            this._pushHistory();
            this.drawings.push(this._newDrawing(this.tool, [point]));
            this._save();
            this.redraw();
            return;
        }
        if (!this.pendingPoint) {
            this.pendingPoint = point;
            this.redraw();
            return;
        }
        this._pushHistory();
        this.drawings.push(this._newDrawing(this.tool, [this.pendingPoint, point]));
        this.pendingPoint = null;
        this._save();
        this.redraw();
    }

    _startDrag(event, drawingId, endpoint) {
        const drawing = this.drawings.find(item => item.id === drawingId);
        if (!drawing) return;
        event.preventDefault();
        this._pushHistory();
        this.selectedId = drawingId;
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
        const x = this.chart.timeScale().timeToCoordinate(point.time);
        const y = this.series.priceToCoordinate(point.price);
        if (x == null || y == null) return null;
        const time = this.chart.timeScale().coordinateToTime(x + dx);
        const price = this.series.coordinateToPrice(y + dy);
        if (time == null || price == null || typeof time !== 'number') return null;
        return { time, price };
    }

    _coordinates(point) {
        const x = this.chart.timeScale().timeToCoordinate(point.time);
        const y = this.series.priceToCoordinate(point.price);
        return x == null || y == null ? null : { x, y };
    }

    _renderDrawing(drawing, width, height) {
        const points = drawing.points.map(point => this._coordinates(point));
        if (points.some(point => point == null)) return;
        const selected = drawing.id === this.selectedId;
        const common = {
            stroke: drawing.color,
            'stroke-width': selected ? Number(drawing.width) + 1 : drawing.width,
            'stroke-dasharray': this._dashArray(drawing.style),
            fill: 'none',
            'data-drawing-id': drawing.id,
            style: 'pointer-events:stroke;cursor:move',
        };
        if (drawing.type === 'trend') {
            this._svg('line', { ...common, x1: points[0].x, y1: points[0].y, x2: points[1].x, y2: points[1].y });
        } else if (drawing.type === 'horizontal') {
            this._svg('line', { ...common, x1: 0, y1: points[0].y, x2: width, y2: points[0].y });
        } else if (drawing.type === 'ray') {
            this._svg('line', { ...common, x1: points[0].x, y1: points[0].y, x2: width, y2: points[0].y });
        } else if (drawing.type === 'vertical') {
            this._svg('line', { ...common, x1: points[0].x, y1: 0, x2: points[0].x, y2: height });
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

    _renderRisk(width) {
        if (!this.risk) return;
        const startX = this.chart.timeScale().timeToCoordinate(this.risk.entry_time);
        const rawEndX = this.chart.timeScale().timeToCoordinate(this.risk.end_time);
        const entryY = this.series.priceToCoordinate(this.risk.fill_price);
        const targetY = this.series.priceToCoordinate(this.risk.target_price);
        const stopY = this.series.priceToCoordinate(this.risk.stop_price);
        if ([startX, rawEndX, entryY, targetY, stopY].some(value => value == null)) return;
        const endX = Math.min(width, Math.max(startX + 12, rawEndX + 8));
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

    _syncPriceLines() {
        if (!this.series) return;
        this.priceLines.forEach(line => this.series.removePriceLine(line));
        this.priceLines = [];
        if (!this.risk) return;
        const side = this.risk.side === 'BUY' ? '开多' : '开空';
        this.priceLines = [
            this.series.createPriceLine({ price: this.risk.fill_price, color: '#4b9cff', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `${side} x${this.risk.leverage}` }),
            this.series.createPriceLine({ price: this.risk.target_price, color: '#21c58b', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '止盈' }),
            this.series.createPriceLine({ price: this.risk.stop_price, color: '#ff5f91', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '止损' }),
        ];
    }

    _svg(name, attributes) {
        const node = document.createElementNS('http://www.w3.org/2000/svg', name);
        Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
        this.overlay.appendChild(node);
        return node;
    }

    _dashArray(style) {
        if (style === 'dash') return '8 5';
        if (style === 'dot') return '2 5';
        return '';
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
        this._save();
        this.redraw();
    }

    _deleteSelected() {
        if (!this.selectedId) return;
        this._pushHistory();
        this.drawings = this.drawings.filter(item => item.id !== this.selectedId);
        this.selectedId = null;
        this._save();
        this.redraw();
    }

    _clear() {
        if (!this.drawings.length) return;
        this._pushHistory();
        this.drawings = [];
        this.selectedId = null;
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
