/* Accessible, responsive SVG charts. No CDN, build step, or third-party runtime. */
(function () {
  'use strict';
  const C = window.SCMCore, esc = C.escapeHTML;
  const $ = (s, base = document) => base.querySelector(s);
  class SCMChart {
    constructor(id) {
      this.id = id; this.el = document.getElementById(id); this.data = null;
      this.cumulative = false; this.zoom = false; this.start = 0; this.active = 0;
      this.hidden = new Set(); this.signature = ''; this._g = null;
      this.el.addEventListener('pointermove', e => {
        if (!this._g) return;
        const x = e.clientX - this.el.getBoundingClientRect().left;
        const g = this._g; this.showPoint(Math.max(0, Math.min(g.n - 1, Math.floor((x - g.left) / g.step))));
      });
      this.el.addEventListener('pointerleave', () => this.hidePoint());
      this.el.addEventListener('blur', () => this.hidePoint());
      this.el.addEventListener('keydown', e => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(e.key)) return;
        e.preventDefault(); e.stopPropagation();
        if (e.key === 'Escape') return this.hidePoint();
        const n = this._g?.n || 0;
        const next = e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : this.active + (e.key === 'ArrowRight' ? 1 : -1);
        this.showPoint(Math.max(0, Math.min(n - 1, next)), true);
      });
      this.observer = new ResizeObserver(() => { cancelAnimationFrame(this.frame); this.frame = requestAnimationFrame(() => this.draw()); });
      this.observer.observe(this.el);
      $(`[data-cumulative="${id}"]`).addEventListener('click', () => { this.cumulative = !this.cumulative; this.draw(); });
      $(`[data-zoom="${id}"]`).addEventListener('click', () => { this.zoom = !this.zoom; this.start = 0; this.draw(); });
      $(`[data-pan="${id}"] input`).addEventListener('input', e => { this.start = Number(e.target.value); this.draw(); });
    }
    set(data) {
      const context = `${data.period}|${data.unit}|${data.labels.join(',')}`;
      if (this.context !== context) { this.start = 0; this.active = 0; this.context = context; }
      this.data = data; this.draw();
    }
    visibleData() {
      if (!this.data) return {labels: [], series: []};
      const n = this.data.labels.length;
      const count = this.zoom ? Math.max(4, Math.ceil(n / 2)) : n;
      this.start = Math.max(0, Math.min(this.start, Math.max(0, n - count)));
      return {labels: this.data.labels.slice(this.start, this.start + count), series: this.data.series.filter(s => !this.hidden.has(s.key)).map(s => ({...s, values: (this.cumulative ? C.cumulative(s.values) : s.values).slice(this.start, this.start + count)}))};
    }
    draw() {
      if (!this.data || this.el.clientWidth < 20 || !this.el.getClientRects().length) return;
      const W = this.el.clientWidth, H = this.el.clientHeight, d = this.visibleData();
      const theme = document.documentElement.dataset.theme;
      const signature = JSON.stringify([W,H,this.data,d,this.cumulative,this.zoom,theme]);
      if (this.signature === signature) return;
      this.signature = signature;
      const numberValues = d.series.flatMap(s => s.values).filter(v => C.number(v) !== null);
      const allZero = numberValues.length > 0 && numberValues.every(v => v === 0);
      let high = Math.max(0, ...numberValues), low = Math.min(0, ...numberValues);
      if (high === low) high = low + (this.data.divisor || 1);
      const desired = (high - low) / 4;
      const power = Math.pow(10, Math.floor(Math.log10(desired || 1)));
      const rawStep = desired / power;
      const step = ([1,2,2.5,5,10].find(x => x >= rawStep) || 10) * power;
      high = Math.ceil(high / step) * step; low = Math.floor(low / step) * step;
      const tickCount = Math.round((high - low) / step);
      const axis = v => {
        const value = v / this.data.divisor;
        const resolution = step / this.data.divisor;
        const decimals = Math.min(5, Math.max(0, -Math.floor(Math.log10(resolution || 1)) + (resolution / Math.pow(10, Math.floor(Math.log10(resolution || 1))) === 2.5 ? 1 : 0)));
        return C.format(value, decimals);
      };
      const widest = Math.max(...Array.from({length: tickCount + 1}, (_, i) => axis(low + i * step).length));
      const left = Math.max(42, Math.min(W * .28, widest * 5.4 + 12)), right = 15, top = 16, bottom = 28;
      const w = Math.max(5, W - left - right), h = H - top - bottom, n = d.labels.length;
      const xstep = w / Math.max(1, n), x = i => left + (i + .5) * xstep;
      const y = value => top + h * (high - value) / (high - low);
      this._g = {W,H,left,right,top,bottom,w,h,n,step:xstep,x,y,d};
      const svg = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(this.data.title)} · ${esc(this.data.unit)}"><title>${esc(this.data.title)} · ${esc(this.data.unit)}. 표 버튼으로 모든 수치를 볼 수 있습니다.</title>`];
      for (let i=0;i<=tickCount;i++) {
        const v = low+i*step, yy=y(v);
        svg.push(`<line x1="${left}" x2="${W-right}" y1="${yy}" y2="${yy}" class="chart-gridline"/><text x="${left-9}" y="${yy+3}" text-anchor="end">${esc(axis(v))}</text>`);
      }
      svg.push(`<line x1="${left}" x2="${W-right}" y1="${y(0)}" y2="${y(0)}" class="chart-baseline"/>`);
      const labelEvery = Math.max(1, Math.ceil(n / Math.max(3, Math.floor(w / 48))));
      d.labels.forEach((label, i) => {
        if (i % labelEvery === 0 || (i === n-1 && (n-1)%labelEvery >= labelEvery/2)) svg.push(`<text x="${x(i)}" y="${H-9}" text-anchor="middle">${esc(this.data.shortLabel(label))}</text>`);
      });
      const asLine = this.cumulative || this.data.kind === 'line';
      d.series.forEach((s, j) => {
        const color = getComputedStyle(document.documentElement).getPropertyValue(s.color).trim();
        if (asLine) {
          let path = '', open = false;
          s.values.forEach((v,i) => { if (v === null) {open=false;return;} path += `${open?' L':' M'}${x(i).toFixed(2)},${y(v).toFixed(2)}`;open=true; });
          svg.push(`<path d="${path}" stroke="${color}" stroke-width="2" fill="none" class="chart-series"/>`);
          s.values.forEach((v,i) => { if(v !== null) svg.push(`<circle cx="${x(i)}" cy="${y(v)}" r="${n>22?1.8:2.5}" fill="${color}"/>`); });
        } else {
          const totalWidth = xstep * .66, bw = Math.max(1, totalWidth / Math.max(1,d.series.length) - 1);
          s.values.forEach((v,i) => {
            if (v === null) return;
            const xx = x(i) - totalWidth/2 + j * totalWidth/d.series.length;
            const yy=Math.min(y(v),y(0)), bh=Math.abs(y(0)-y(v));
            svg.push(`<rect x="${xx}" y="${yy}" width="${bw}" height="${Math.max(v===0?0:1,bh)}" rx="1" fill="${color}" class="chart-series"/>`);
          });
        }
      });
      if (Number.isInteger(this.data.currentIndex)) {
        const i=this.data.currentIndex-this.start;
        if(i>=0 && i<n) svg.push(`<line x1="${x(i)}" x2="${x(i)}" y1="${top}" y2="${H-bottom}" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3"/><text x="${Math.min(W-right-17,x(i))}" y="${top-5}" text-anchor="middle">진행 중</text>`);
      }
      if(!numberValues.length) svg.push(`<text x="${left+w/2}" y="${top+h/2}" text-anchor="middle">${d.series.length ? '표시할 수신값이 없습니다.' : '범례에서 계열을 선택하세요.'}</text>`);
      else if(allZero) svg.push(`<text x="${left+w/2}" y="${top+h/2}" text-anchor="middle">수신값 전체 0</text>`);
      svg.push(`<line class="crosshair" x1="0" x2="0" y1="${top}" y2="${H-bottom}" visibility="hidden"/><rect class="chart-interaction" x="${left}" y="${top}" width="${w}" height="${h}"/></svg>`);
      this.el.innerHTML=svg.join('');
      this.tooltip=document.createElement('div'); this.tooltip.className='chart-tooltip';this.tooltip.hidden=true;this.el.appendChild(this.tooltip);
      const legend=$(`[data-legend="${this.id}"]`);
      legend.innerHTML=this.data.series.map(s=>`<button type="button" class="legend-button" data-series="${esc(s.key)}" style="--series:var(${s.color})" aria-pressed="${!this.hidden.has(s.key)}"><span></span>${esc(s.name)}</button>`).join('');
      legend.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=> {this.hidden.has(b.dataset.series)?this.hidden.delete(b.dataset.series):this.hidden.add(b.dataset.series);this.draw();}));
      $(`[data-cumulative="${this.id}"]`).setAttribute('aria-pressed',String(this.cumulative));
      $(`[data-cumulative="${this.id}"]`).title=this.cumulative?'누락 구간 이후 누적값은 표시하지 않습니다.':'일별 또는 시간대별 수신값 누적';
      $(`[data-zoom="${this.id}"]`).setAttribute('aria-pressed',String(this.zoom));
      $(`[data-zoom="${this.id}"]`).textContent=this.zoom?'복원':'확대';
      const pan=$(`[data-pan="${this.id}"]`);pan.hidden=!this.zoom;const range=$('input',pan);range.max=String(Math.max(0,this.data.labels.length-n));range.value=String(this.start);
    }
    showPoint(index, announce=false) {
      const g=this._g;if(!g || !g.n || index<0) return;
      this.active=index;
      const data=g.d;
      this.tooltip.innerHTML=`<strong>${esc(data.labels[index])}${this.cumulative?' · 누적':''}</strong>` + data.series.map(s=>`<div><span>${esc(s.name)}</span><b>${esc(this.data.format(s.values[index]))}</b></div>`).join('') + (this.cumulative?'<small>누락이 있으면 그 이후 누적은 미표시</small>':'');
      this.tooltip.hidden=false;
      const left=Math.min(g.W-this.tooltip.offsetWidth-4,Math.max(4,g.x(index)+12));
      this.tooltip.style.left=left+'px';this.tooltip.style.top='13px';
      const cross=$('.crosshair',this.el);if(cross){cross.setAttribute('x1',String(g.x(index)));cross.setAttribute('x2',String(g.x(index)));cross.setAttribute('visibility','visible');}
      if(announce)document.getElementById('screenReaderStatus').textContent=this.tooltip.textContent;
    }
    hidePoint(){ if(this.tooltip)this.tooltip.hidden=true; const cross=$('.crosshair',this.el);if(cross)cross.setAttribute('visibility','hidden'); }
    exportRows() {
      const d=this.visibleData();
      return [['기준',...d.series.map(s=>`${s.name} (${this.data?.rawUnit || ''}${this.cumulative?' · 누적':''})`)],...d.labels.map((label,i)=>[label,...d.series.map(s=>s.values[i])])];
    }
    destroy(){this.observer.disconnect();cancelAnimationFrame(this.frame);}
  }
  window.SCMChart=SCMChart;
})();
