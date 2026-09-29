/* Pure data utilities: reusable in the browser and Node tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SCMCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const METRICS = {
    EA: { type: 'EA', label: '수량', unit: 'EA' },
    EQ_DRAM: { type: 'EQ', label: 'DRAM 환산', unit: 'EQ·DRAM' },
    EQ_FLASH: { type: 'EQ', label: 'FLASH 환산', unit: 'EQ·FLASH' },
    BOX: { type: 'BOX', label: '박스', unit: 'BOX' },
    USD: { type: 'USD', label: '출하 금액', unit: 'USD' }
  };
  const number = v => (v === null || v === undefined || typeof v === 'boolean' ||
    (typeof v === 'string' && !v.trim()) || !['number', 'string'].includes(typeof v))
    ? null : (Number.isFinite(Number(v)) ? Number(v) : null);
  function format(v, decimals = 0) {
    const n = number(v);
    return n === null ? '—' : n.toLocaleString('ko-KR', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
  }
  function kstParts(date = new Date()) {
    const f = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'});
    return Object.fromEntries(f.formatToParts(date).filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
  }
  function today(date = new Date()) { const p = kstParts(date); return p.year + p.month + p.day; }
  function validDate(v) {
    if (typeof v !== 'string') return false;
    const s = v.replace(/-/g, '');
    if (!/^\d{8}$/.test(s)) return false;
    const d = new Date(`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}T12:00:00Z`);
    return Number.isFinite(d.getTime()) && d.toISOString().slice(0,10).replace(/-/g, '') === s;
  }
  function isoDate(v) { return validDate(v) ? v.replace(/-/g,'').replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3') : ''; }
  function dateLabel(v) { return isoDate(v).replace(/-/g,'.') || '기준일 미제공'; }
  function pct(actual, target) {
    const a = number(actual), t = number(target);
    return a === null || t === null || t <= 0 ? null : a / t * 100;
  }
  function change(current, previous) {
    const a = number(current), b = number(previous);
    return a === null || b === null || b === 0 ? null : (a - b) / Math.abs(b) * 100;
  }
  function cumulative(values) {
    let sum = 0, gap = false;
    return values.map(v => { const n = number(v); if (n === null) gap = true; if (gap) return null; sum += n; return sum; });
  }
  function sum(values) {
    if (!values.length || values.some(v => number(v) === null)) return null;
    return values.reduce((s, v) => s + Number(v), 0);
  }
  function multiplier(endpoint, metric, units = {}) {
    const explicit = number(units.overrides?.[endpoint]?.[metric]);
    if (explicit !== null && explicit > 0) return explicit;
    return units.profile === 'readme-k' && ['EA', 'USD'].includes(metric) ? 1000 : 1;
  }
  function scale(v, endpoint, metric, units) {
    const n = number(v); return n === null ? null : n * multiplier(endpoint, metric, units);
  }
  function normalizeKPI(raw, metric, units) {
    const result = {};
    for (const key of ['production', 'shipment']) {
      const r = raw?.[key] || {};
      const actual = scale(r.actual_mtd, 'kpi', metric, units), target = scale(r.target, 'kpi', metric, units);
      const actualToday = scale(r.actual_today, 'kpi', metric, units), yesterday = scale(r.yesterday, 'kpi', metric, units);
      result[key] = {target, actual, today: actualToday, yesterday, achievement: pct(actual, target),
        reportedAchievement: number(r.achievement), change: change(actualToday, yesterday),
        reportedChange: number(r.yoy_change), count: number(r.count_mtd), todayCount: number(r.count_today),
        date: r.date || raw?.[key === 'production' ? 'latest_inbound_date' : 'latest_shipment_date'] || raw?.date || ''};
      if (metric === 'USD' && key === 'production') {
        for (const f of ['actual','target','today','yesterday','achievement','change']) result[key][f] = null;
      }
    }
    const inv = raw?.inventory || {};
    result.inventory = {current: scale(inv.current, 'kpi', metric, units), available: scale(inv.available, 'kpi', metric, units), count: number(inv.count)};
    result.metric = metric; result.date = raw?.date || ''; result.timestamp = raw?.timestamp || '';
    return result;
  }
  function dailySeries(raw, month, key, units, metric = 'EA') {
    if (!/^\d{6}$/.test(month) || Number(month.slice(4)) < 1 || Number(month.slice(4)) > 12) return [];
    const days = new Date(Number(month.slice(0,4)), Number(month.slice(4)), 0).getDate();
    const map = new Map((Array.isArray(raw?.daily) ? raw.daily : []).filter(r => validDate(r.date)).map(r => [r.date.replace(/-/g,''), r]));
    return Array.from({length: days}, (_, i) => {
      const date = month + String(i + 1).padStart(2, '0');
      return {date, value: map.has(date) ? scale(map.get(date)[key], 'daily-trend', metric, units) : null};
    });
  }
  function hourlyValues(raw, key, units, metric = raw?.metric || 'EA') {
    const map = new Map((raw?.hours || []).map((h, i) => [String(h).padStart(2, '0'), raw?.[key]?.[i]]));
    return Array.from({length:24}, (_, h) => scale(map.get(String(h).padStart(2,'0')), 'hourly', metric, units));
  }
  function eventKey(e) { return JSON.stringify([e.date || '', e.time || '', e.type || '', e.detail || '', e.warehouse || '']); }
  function newEventKeys(oldEvents, newEvents, initialized = true) {
    if (!initialized) return new Set();
    const before = new Set(oldEvents.map(eventKey));
    return new Set(newEvents.map(eventKey).filter(k => !before.has(k)));
  }
  function csv(rows) {
    const cell = value => {
      let text = value === null || value === undefined ? '' : String(value);
      if (typeof value !== 'number' && /^[\s\uFEFF]*[=+\-@\t\r]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    return '\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n');
  }
  function requestParams(endpoint, state, allowed) {
    const params = {metric: state.metric, ...state.filters, range: state.range, limit:50, month:state.month};
    return Object.fromEntries((allowed[endpoint] || []).filter(k => params[k] !== '' && params[k] !== 'ALL' && params[k] !== null && params[k] !== undefined).map(k => [k, params[k]]));
  }
  function escapeHTML(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])); }
  function validate(endpoint, raw, metric) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('객체 형태의 JSON 응답이 아닙니다');
    if (endpoint === 'kpi') {
      if (!raw.production || !raw.shipment || !raw.inventory) throw new Error('KPI 필수 영역이 없습니다');
      if (raw.metric && raw.metric !== metric) throw new Error(`지표 불일치: 요청 ${metric}, 응답 ${raw.metric}`);
    } else if (endpoint === 'hourly') {
      if (!Array.isArray(raw.hours) || !Array.isArray(raw.production) || !Array.isArray(raw.shipment)) throw new Error('시간대별 배열이 없습니다');
    } else {
      const key = {'daily-trend':'daily','inbound-progress':'progress',customers:'customers',items:'items',events:'events',alerts:'alerts'}[endpoint];
      if (key && !Array.isArray(raw[key])) throw new Error(`${key} 배열이 없습니다`);
    }
    return raw;
  }
  return {METRICS, number, format, kstParts, today, validDate, isoDate, dateLabel, pct, change, cumulative, sum, multiplier, scale, normalizeKPI, dailySeries, hourlyValues, eventKey, newEventKeys, csv, requestParams, escapeHTML, validate};
});
