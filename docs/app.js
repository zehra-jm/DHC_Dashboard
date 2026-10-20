/* Karachi Rate Board. Reads data/summary.json and data/hotels/<id>.json written by
   collector/build.py. A preview build can inline both as window.RATE_DATA instead. */
(function () {
  const app = document.getElementById('app');
  const PERIODS = { d1: 'yesterday', d7: 'last week', d30: 'last month' };
  const state = { stars: 'all', q: '', period: 'd1', sort: 'stars', dir: -1 };
  let S = null;
  const hotelCache = {};

  try {
    const saved = JSON.parse(localStorage.getItem('krb') || '{}');
    if (saved.stars) state.stars = saved.stars;
    if (saved.period) state.period = saved.period;
  } catch (e) { /* storage unavailable */ }
  function remember() {
    try { localStorage.setItem('krb', JSON.stringify({ stars: state.stars, period: state.period })); } catch (e) {}
  }

  // ---------- data ----------
  async function getSummary() {
    if (window.RATE_DATA) return window.RATE_DATA.summary;
    const r = await fetch('data/summary.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error('summary.json ' + r.status);
    return r.json();
  }
  async function getHotel(id) {
    if (hotelCache[id]) return hotelCache[id];
    if (window.RATE_DATA) return (hotelCache[id] = window.RATE_DATA.hotels[id]);
    const r = await fetch('data/hotels/' + encodeURIComponent(id) + '.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error('hotel ' + r.status);
    return (hotelCache[id] = await r.json());
  }

  // ---------- formatting ----------
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = v => v == null ? '—' : Math.round(v).toLocaleString('en-US');
  const pkr = v => v == null ? '<span class="soldout">no rooms</span>' : '<span class="price num"><small>PKR</small>' + n(v) + '</span>';
  const stars = k => k ? '<span class="stars" aria-label="' + k + ' star">' + '★'.repeat(k) + '</span>' : '';
  const tz = { timeZone: 'Asia/Karachi' };
  const fmtTime = iso => new Date(iso).toLocaleTimeString('en-GB', { ...tz, hour: '2-digit', minute: '2-digit' });
  const fmtDay = iso => new Date(iso).toLocaleDateString('en-GB', { ...tz, weekday: 'short', day: 'numeric', month: 'short' });
  const dayKey = iso => new Date(iso).toLocaleDateString('en-CA', tz);

  function delta(c, label) {
    if (!c) return '<span class="na" title="No rate saved from ' + esc(label) + ' yet">—</span>';
    const cls = Math.abs(c.pct) < 0.5 ? 'flat' : c.pct > 0 ? 'up' : 'down';
    const arrow = cls === 'up' ? '▲ ' : cls === 'down' ? '▼ ' : '';
    const sign = c.diff > 0 ? '+' : c.diff < 0 ? '−' : '';
    return '<span class="d ' + cls + ' num" title="Was PKR ' + n(c.was) + ' ' + esc(label) + '"><b>' + arrow +
      (c.pct > 0 ? '+' : '') + c.pct.toFixed(1) + '%</b><small>' + sign + n(Math.abs(c.diff)) + '</small></span>';
  }

  function spark(vals, w, h) {
    w = w || 96; h = h || 26;
    const pts = vals.map((v, i) => [i, v]).filter(p => p[1] != null);
    if (pts.length < 2) return '<span class="na">—</span>';
    const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
    const X = i => 2 + i * (w - 6) / (vals.length - 1), Y = v => h - 3 - (v - lo) / span * (h - 6);
    let line = '', seg = false;
    vals.forEach((v, i) => { if (v == null) { seg = false; return; } line += (seg ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); seg = true; });
    const first = pts[0], last = pts[pts.length - 1];
    const area = 'M' + X(first[0]) + ' ' + h + pts.map(p => 'L' + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('') + 'L' + X(last[0]) + ' ' + h + 'Z';
    return '<svg class="spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="30-day trend from PKR ' + n(first[1]) + ' to ' + n(last[1]) + '">' +
      '<path class="area" d="' + area + '"/><path class="line" d="' + line + '"/><circle cx="' + X(last[0]).toFixed(1) + '" cy="' + Y(last[1]).toFixed(1) + '" r="2.5"/></svg>';
  }

  function matches(h) {
    if (state.stars !== 'all' && String(h.stars) !== state.stars) return false;
    const q = state.q.trim().toLowerCase();
    return !q || (h.name + ' ' + (h.area || '')).toLowerCase().includes(q);
  }

  // ---------- overview ----------
  function seg(id, label, opts, cur) {
    return '<div><span class="ctl-label" id="' + id + '-l">' + label + '</span><div class="seg" role="group" aria-labelledby="' + id + '-l">' +
      opts.map(([v, t]) => '<button type="button" data-' + id + '="' + v + '" aria-pressed="' + (v === cur) + '">' + t + '</button>').join('') + '</div></div>';
  }

  function stripHtml(list) {
    const p = state.period, label = PERIODS[p];
    const moved = list.filter(h => h[p]);
    const up = moved.filter(h => h[p].pct >= 0.5), down = moved.filter(h => h[p].pct <= -0.5);
    const avg = moved.length ? moved.reduce((a, h) => a + h[p].pct, 0) / moved.length : null;
    const top = up.slice().sort((a, b) => b[p].pct - a[p].pct)[0];
    const bot = down.slice().sort((a, b) => a[p].pct - b[p].pct)[0];
    const sold = list.filter(h => h.price == null).length;
    const pct = v => (v > 0 ? '+' : '') + v.toFixed(1) + '%';
    return '<dl class="strip num">' +
      '<div><dt>Hotels tracked</dt><dd>' + list.length + '<small>' + (sold ? sold + ' with no rooms for tomorrow' : 'all with rooms for tomorrow') + '</small></dd></div>' +
      '<div><dt>Since ' + label + '</dt><dd>' + up.length + ' up · ' + down.length + ' down<small>' + (moved.length - up.length - down.length) + ' unchanged</small></dd></div>' +
      '<div><dt>Average move</dt><dd>' + (avg == null ? '—' : pct(avg)) + '<small>lowest rate, vs ' + label + '</small></dd></div>' +
      '<div><dt>Biggest rise</dt><dd>' + (top ? pct(top[p].pct) + '<small>' + esc(top.name) + '</small>' : '—<small>none</small>') + '</dd></div>' +
      '<div><dt>Biggest drop</dt><dd>' + (bot ? pct(bot[p].pct) + '<small>' + esc(bot.name) + '</small>' : '—<small>none</small>') + '</dd></div>' +
      '</dl>';
  }

  function sortVal(h, k) {
    if (k === 'name') return h.name.toLowerCase();
    if (k === 'stars') return (h.stars || 0) * 1e7 + (h.price || 0) / 10;
    if (k === 'price') return h.price == null ? -1 : h.price;
    return h[k] ? h[k].pct : -1e9;
  }

  function tableHtml(list) {
    const cols = [['name', 'Hotel'], ['price', 'From / night'], ['d1', 'vs yesterday'], ['d7', 'vs last week'], ['d30', 'vs last month']];
    const rows = list.slice().sort((a, b) => {
      const x = sortVal(a, state.sort), y = sortVal(b, state.sort);
      return (x < y ? -1 : x > y ? 1 : 0) * state.dir || a.name.localeCompare(b.name);
    });
    return '<div class="scroll"><table><thead><tr>' +
      cols.map(([k, t]) => '<th' + (state.sort === k ? ' aria-sort="' + (state.dir > 0 ? 'ascending' : 'descending') + '"' : '') + '><button type="button" data-sort="' + k + '">' + t + '</button></th>').join('') +
      '<th>30 days</th></tr></thead><tbody>' +
      (rows.length ? rows.map(h => '<tr class="link" data-go="' + esc(h.id) + '">' +
        '<td class="hname"><a href="#h-' + esc(h.id) + '">' + esc(h.name) + '</a><span class="sub">' + stars(h.stars) + esc(h.area || '') + '</span></td>' +
        '<td>' + pkr(h.price) + '</td><td>' + delta(h.d1, 'yesterday') + '</td><td>' + delta(h.d7, 'last week') + '</td><td>' + delta(h.d30, 'last month') + '</td>' +
        '<td>' + spark(h.trend) + '</td></tr>').join('')
        : '<tr><td colspan="6" class="na">No hotels match these filters.</td></tr>') +
      '</tbody></table></div>';
  }

  function eventHtml(e) {
    let line, amt = '';
    const rooms = [e.rooms_up && e.rooms_up + ' room rate' + (e.rooms_up > 1 ? 's' : '') + ' up', e.rooms_down && e.rooms_down + ' down'].filter(Boolean).join(', ');
    if (e.kind === 'up' || e.kind === 'down') {
      line = 'Lowest rate ' + n(e.old) + ' → ' + n(e.new) + (rooms ? ' · ' + rooms : '');
      amt = delta({ pct: e.pct, diff: e.new - e.old, was: e.old }, 'before');
    } else if (e.kind === 'soldout') {
      line = 'No rooms left for tomorrow (was ' + n(e.old) + ')';
      amt = '<span class="tag">Sold out</span>';
    } else if (e.kind === 'back') {
      line = 'Rooms available again from ' + n(e.new);
      amt = '<span class="tag">Back</span>';
    } else {
      line = rooms + ' · lowest rate unchanged at ' + n(e.new);
    }
    return '<a class="ev" href="#h-' + esc(e.id) + '"><time class="num">' + fmtTime(e.t) + '</time><div class="what"><strong>' + esc(e.name) + '</strong><span class="num">' + line + '</span></div><div class="amt">' + amt + '</div></a>';
  }

  function feedHtml(events) {
    if (!events.length) return '<div class="feed"><p class="feed-empty">No price changes in the last 7 days for these hotels.</p></div>';
    let out = '', cur = '';
    events.forEach(e => {
      const k = dayKey(e.t);
      if (k !== cur) { cur = k; out += '<div class="day">' + fmtDay(e.t) + '</div>'; }
      out += eventHtml(e);
    });
    return '<div class="feed">' + out + '</div>';
  }

  function renderOverview() {
    const list = S.hotels.filter(matches);
    const events = S.changes.filter(matches);
    const priced = events.filter(e => e.kind === 'up' || e.kind === 'down').length;
    app.innerHTML =
      '<div class="controls">' +
        seg('stars', 'Stars', [['all', 'All'], ['5', '5★'], ['4', '4★'], ['3', '3★']], state.stars) +
        seg('period', 'Compare with', [['d1', 'Yesterday'], ['d7', 'Last week'], ['d30', 'Last month']], state.period) +
        '<div><label class="ctl-label" for="q">Find</label><input id="q" type="search" placeholder="Hotel or area" value="' + esc(state.q) + '"></div>' +
      '</div>' +
      stripHtml(list) +
      '<div class="board">' +
        '<section><h2>All hotels <span>Lowest Booking.com rate for tomorrow night · tap a hotel for its rooms</span></h2>' + tableHtml(list) + '</section>' +
        '<section class="feed-col"><h2>Price changes <span>' + priced + ' moves in 7 days</span></h2>' + feedHtml(events) + '</section>' +
      '</div>';
  }

  // ---------- hotel ----------
  function chartHtml(hist) {
    const W = 1100, H = 280, L = 52, R = 14, T = 12, B = 28;
    const pts = hist.map((d, i) => [i, d[1]]).filter(p => p[1] != null);
    if (pts.length < 2) return '<div class="chart"><p class="na" style="padding:12px">Not enough history yet. The chart fills in as rates are collected.</p></div>';
    const ys = pts.map(p => p[1]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pad = (hi - lo) * 0.15 || hi * 0.05; lo -= pad; hi += pad;
    const step = niceStep((hi - lo) / 4);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const X = i => L + i * (W - L - R) / (hist.length - 1), Y = v => T + (hi - v) / (hi - lo) * (H - T - B);
    let grid = '';
    for (let v = lo; v <= hi + 1e-6; v += step) grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/><text x="' + (L - 8) + '" y="' + (Y(v) + 4) + '" text-anchor="end">' + (v >= 1000 ? (v / 1000).toLocaleString('en-US', { maximumFractionDigits: 1 }) + 'k' : v) + '</text>';
    let xl = '';
    hist.forEach((d, i) => { if ((hist.length - 1 - i) % 7 === 0) xl += '<text x="' + X(i) + '" y="' + (H - 8) + '" text-anchor="' + (i === hist.length - 1 ? 'end' : i === 0 ? 'start' : 'middle') + '">' + new Date(d[0] + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + '</text>'; });
    let line = '', seg = false;
    hist.forEach((d, i) => { if (d[1] == null) { seg = false; return; } line += (seg ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(d[1]).toFixed(1); seg = true; });
    const f = pts[0], l = pts[pts.length - 1];
    const area = 'M' + X(f[0]) + ' ' + Y(lo) + pts.map(p => 'L' + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('') + 'L' + X(l[0]) + ' ' + Y(lo) + 'Z';
    return '<div class="chart"><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Lowest rate per day over 30 days"><g class="grid">' + grid + '</g>' + xl +
      '<path class="area" d="' + area + '"/><path class="line" d="' + line + '"/><circle class="dot" cx="' + X(l[0]) + '" cy="' + Y(l[1]) + '" r="4.5"/></svg></div>';
  }
  function niceStep(x) {
    const p = Math.pow(10, Math.floor(Math.log10(x))), m = x / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }

  async function renderHotel(id) {
    let h;
    try { h = await getHotel(id); } catch (e) { h = null; }
    if (!h) { app.innerHTML = '<a class="back" href="#">← All hotels</a><p>This hotel is not in the latest snapshot.</p>'; return; }
    const ev = S.changes.filter(e => e.id === id).slice(0, 25);
    app.innerHTML =
      '<a class="back" href="#">← All hotels</a>' +
      '<div class="hhead"><div><h2>' + esc(h.name) + '</h2><div class="meta">' + stars(h.stars) + esc(h.area || '') +
        (h.score ? ' · guest score ' + h.score : '') + ' · <a class="ext" href="' + esc(h.url) + '" target="_blank" rel="noopener">Open on Booking.com ↗</a></div></div>' +
        '<div class="now"><div class="lbl">Lowest rate, tomorrow night</div><div class="big num">' + (h.price == null ? 'No rooms' : 'PKR ' + n(h.price)) + '</div>' +
        '<div class="dl num"><span class="k">vs yesterday</span><span class="k">vs last week</span><span class="k">vs last month</span>' + delta(h.d1, 'yesterday') + delta(h.d7, 'last week') + delta(h.d30, 'last month') + '</div></div></div>' +
      '<div class="hgrid">' +
        '<section><h2>Lowest rate, last 30 days <span>closing rate each day</span></h2>' + chartHtml(h.history) + '</section>' +
        '<section><h2>Rooms <span>' + h.rooms.length + ' rates for 2 adults, 1 night, before tax</span></h2><div class="scroll"><table><thead><tr><th>Room</th><th>Tomorrow</th><th>vs yesterday</th><th>vs last week</th><th>vs last month</th><th>30 days</th></tr></thead><tbody>' +
          (h.rooms.length ? h.rooms.map(r => '<tr><td class="hname">' + esc(r.name) + '<span class="sub">' + '<span class="tag">' + esc(r.meal === 'breakfast' ? 'Breakfast included' : 'Room only') + '</span>' + (r.free_cancel ? '<span class="tag">Free cancellation</span>' : '') + '</span></td>' +
            '<td>' + pkr(r.price) + '</td><td>' + delta(r.d1, 'yesterday') + '</td><td>' + delta(r.d7, 'last week') + '</td><td>' + delta(r.d30, 'last month') + '</td><td>' + spark(r.trend.map(d => d[1])) + '</td></tr>').join('')
            : '<tr><td colspan="6" class="na">No rooms listed for tomorrow night.</td></tr>') +
        '</tbody></table></div></section>' +
        '<section><h2>Recent changes <span>last 7 days</span></h2>' + feedHtml(ev) + '</section>' +
      '</div>';
    window.scrollTo(0, 0);
  }

  // ---------- collector health ----------
  // status comes from data/status.json, written by collect.py on every run.
  function showAlert(s) {
    const st = s.status, el = document.getElementById('alert');
    const when = iso => iso ? fmtDay(iso) + ', ' + fmtTime(iso) + ' PKT' : 'never';
    const issues = s.repo ? ' <a href="https://github.com/' + esc(s.repo) + '/issues?q=is%3Aopen+label%3Acollector-broken" target="_blank" rel="noopener">See the issue</a>' : '';
    let title = '', text = '', warn = false;
    if (st && st.state === 'layout') {
      title = 'Booking.com changed its page layout.';
      text = 'New rates cannot be read until the collector is updated. Rates below are from ' + when(st.last_ok) + '. Problem seen since ' + when(st.since) + ': ' + esc(st.message) + issues;
    } else if (st && st.state === 'rooms') {
      title = 'Booking.com changed its hotel pages.';
      text = 'Hotel rates are current, but room rates stopped updating on ' + when(st.since) + ' until the collector is updated. ' + esc(st.message) + issues;
    } else if (st && st.state === 'blocked') {
      warn = !st.alert;
      title = 'Booking.com blocked the last collection run.';
      text = 'Rates below are from ' + when(st.last_ok) + '. ' + (st.alert
        ? 'This has lasted since ' + when(st.since) + ', so the collector needs a change.' + issues
        : 'This usually clears by the next run.');
    } else if (!s.sample && Date.now() - new Date(s.updated) > 3 * 3600e3) {
      warn = true;
      title = 'No new rates since ' + when(s.updated) + '.';
      text = 'The scheduled collection may be paused on GitHub. Re-enable it under Actions.';
    }
    el.hidden = !title;
    el.classList.toggle('warn', warn);
    document.getElementById('alert-title').textContent = title;
    document.getElementById('alert-text').innerHTML = text;
  }

  document.getElementById('demo-alert').addEventListener('click', () => {
    const now = S.updated;
    showAlert(Object.assign({}, S, { status: { state: 'layout', since: now, last_ok: S.updated, alert: true,
      message: 'The search page loaded but no hotel cards were found on it.' } }));
    window.scrollTo(0, 0);
  });

  // ---------- DHC rate letters vs Booking.com ----------
  // The rate sheet holds DHC's corporate rates. It is never published: it is loaded from a
  // file the viewer picks and kept only in this browser (localStorage).
  let C = null;
  async function getContracts() {
    if (C) return C;
    if (window.RATE_DATA) return (C = window.RATE_DATA.contracts || []);
    const r = await fetch('data/contracts.json', { cache: 'no-cache' });
    return (C = r.ok ? await r.json() : []);
  }
  function getRates() {
    if (window.RATE_DATA && window.RATE_DATA.rates) return window.RATE_DATA.rates;
    try { return JSON.parse(localStorage.getItem('krb-rates') || 'null'); } catch (e) { return null; }
  }

  function compare(rates, hid, rid) {
    const h = rates && rates.hotels[hid], v = h && h.rooms[rid];
    if (!v) return null;
    const dbl = v.double || v.single + (h.extra_person || 0);
    // Corporate rate before tax: letters that quote tax-inclusive prices have the tax taken out.
    const corp = h.tax_included ? dbl / (1 + rates.tax_rate) : dbl;
    return { basis: h.basis, corp, derived: !v.double && !!h.extra_person, taxIncluded: h.tax_included };
  }

  function verdict(vs) {
    if (vs == null) return null;
    if (vs < 0) return { cls: 'bad', text: 'Booking.com is ' + Math.abs(vs).toFixed(0) + '% below the corporate rate. Ask the hotel to review it.' };
    if (vs < 5) return { cls: 'watch', text: 'Booking.com is within 5% of the corporate rate. Watch this room.' };
    return { cls: 'good', text: 'Booking.com is ' + vs.toFixed(0) + '% above the corporate rate.' };
  }

  const pct = v => v == null ? '<span class="na">—</span>' : '<span class="gap ' + (v < 0 ? 'neg' : 'pos') + ' num">' + (v > 0 ? '+' : '') + v.toFixed(1) + '%</span>';

  function ratesPanel(rates) {
    if (window.RATE_DATA && window.RATE_DATA.rates) return '';
    return '<div class="ratefile">' + (rates
      ? '<span>Rate sheet loaded in this browser: ' + Object.keys(rates.hotels).length + ' hotels.</span> <label class="btn">Replace<input type="file" id="ratefile" accept=".json,application/json" hidden></label> <button type="button" class="btn ghost" id="forget">Remove from this browser</button>'
      : '<strong>Load the DHC rate sheet to compare.</strong> <span>Pick <code>dhc-contract-rates.json</code>. It stays in this browser and is never uploaded or published.</span> <label class="btn">Choose file<input type="file" id="ratefile" accept=".json,application/json" hidden></label>') +
      '<span id="ratefile-msg" class="na"></span></div>';
  }

  async function renderContracts() {
    const list = await getContracts(), rates = getRates();
    const rows = [];
    list.forEach(h => h.rooms.forEach(r => {
      const c = compare(rates, h.id, r.id), b = r.match && r.match.value;
      const vs = c && b ? (b - c.corp) / c.corp * 100 : null;
      rows.push({ h, r, c, b, vs, v: verdict(vs) });
    }));
    const cmp = rows.filter(x => x.v);
    const below = cmp.filter(x => x.vs < 0).length, close = cmp.filter(x => x.v.cls === 'watch').length;
    const above = cmp.filter(x => x.v.cls === 'good').length;
    const att = cmp.filter(x => x.v.cls === 'bad').sort((a, b) => a.vs - b.vs);
    const found = list.filter(h => h.found).length;

    let html = '<div class="pagehead"><h2>DHC rate letters vs Booking.com</h2><p>Each room type from the hotels\' rate letters, matched to the same room on Booking.com. ' +
      'Both sides are for 2 adults, 1 night from tomorrow, before tax. Single-occupancy letters add the hotel\'s extra-person charge. ' +
      'Booking.com uses the cheapest offer with breakfast when there is one, since every letter includes breakfast.</p></div>' + ratesPanel(rates);
    html += '<dl class="strip num">' +
      '<div><dt>Hotels found on Booking.com</dt><dd>' + found + ' of ' + list.length + '<small>' + rows.filter(x => x.b).length + ' of ' + rows.length + ' room types matched</small></dd></div>' +
      '<div><dt>Below corporate rate</dt><dd>' + (rates ? below : '—') + '<small>Booking.com cheaper than corporate</small></dd></div>' +
      '<div><dt>Within 5% of corporate</dt><dd>' + (rates ? close : '—') + '<small>watch these rooms</small></dd></div>' +
      '<div><dt>Above corporate rate</dt><dd>' + (rates ? above : '—') + '<small>by 5% or more</small></dd></div></dl>';
    if (att.length) html += '<section class="attn"><h2>Needs attention <span>' + att.length + ' room types where Booking.com is below the corporate rate</span></h2><ul>' +
      att.map(x => '<li class="' + x.v.cls + '"><a href="#dhc-' + esc(x.h.id) + '"><strong>' + esc(x.h.name) + '</strong> · ' + esc(x.r.name) + '</a><span>' + x.v.text + '</span></li>').join('') + '</ul></section>';
    list.forEach(h => {
      const hr = rows.filter(x => x.h === h);
      html += '<section class="contract" id="dhc-' + esc(h.id) + '"><h2>' + esc(h.name) +
        (rates && rates.hotels[h.id] ? ' <span>' + esc(rates.hotels[h.id].letter) + '</span>' : '') + '</h2>' +
        (!h.found ? '<p class="na">Not found on Booking.com in the latest run.</p>' :
        h.booking_rooms === 0 ? '<p class="na">Found on Booking.com, but no rooms were on sale for tomorrow night in the latest run.</p>' :
        '<div class="scroll"><table class="ctable"><thead><tr><th>Room (rate letter)</th><th>Booking.com room</th><th>Corporate (excl. tax)</th><th>Booking.com (excl. tax)</th><th>Booking.com vs corporate</th><th>vs yesterday</th><th>30 days</th></tr></thead><tbody>' +
        hr.map(x => '<tr' + (x.v ? ' class="v-' + x.v.cls + '"' : '') + '><td class="hname">' + esc(x.r.name) + (x.c ? '<span class="sub">' + esc(x.c.basis) + (x.c.derived ? ' · single + extra person' : '') + (x.c.taxIncluded ? ' · letter price had tax included, shown without' : '') + '</span>' : '') + '</td>' +
          '<td class="bname">' + (x.r.match ? esc(x.r.match.booking_room) + '<span class="sub">' + (x.r.match.meal === 'breakfast' ? 'Breakfast included' : 'Room only') + '</span>' : '<span class="na">No matching room</span>') + '</td>' +
          '<td>' + (x.c ? '<span class="num">' + n(x.c.corp) + '</span>' : '<span class="na">—</span>') + '</td>' +
          '<td>' + (x.b ? '<span class="price num">' + n(x.b) + '</span>' : '<span class="na">—</span>') + '</td>' +
          '<td>' + pct(x.vs) + '</td><td>' + delta(x.r.d1, 'yesterday') + '</td><td>' + spark(x.r.trend) + '</td></tr>' +
          (x.v ? '<tr class="insight v-' + x.v.cls + '"><td colspan="7">' + x.v.text + '</td></tr>' : '')).join('') +
        '</tbody></table></div>' +
        (h.unmatched.length ? '<p class="unmatched">Booking.com rooms not in the rate letter: ' + h.unmatched.map(esc).join(', ') + '</p>' : '')) +
        '</section>';
    });
    app.innerHTML = '<div class="hgrid">' + html + '</div>';
    const target = location.hash.match(/^#dhc-(.+)$/);
    if (target) { const el = document.getElementById('dhc-' + target[1]); if (el) el.scrollIntoView(); } else window.scrollTo(0, 0);
  }

  // ---------- Lowest rates: each rate-letter hotel's lowest DHC rate vs its lowest Booking.com rate ----------
  function dhcLowest(rates, hid) {
    const h = rates && rates.hotels[hid];
    if (!h) return null;
    let corp = null, rack = null;
    Object.keys(h.rooms).forEach(rid => {
      const c = compare(rates, hid, rid);
      if (c && (!corp || c.corp < corp.v)) corp = { v: c.corp, room: rid };
      const v = h.rooms[rid], rk = v.rack_double || v.rack_single;
      if (rk && (!rack || rk < rack.v)) rack = { v: rk, room: rid };
    });
    return { corp, rack };
  }
  const roomLabel = (list, h, rid) => { const r = h && h.rooms.find(x => x.id === rid); return r ? r.name.replace(/\s*\(.*\)$/, '') : rid; };
  const vsCell = v => v == null ? '<span class="na">—</span>' : '<span class="gap ' + (v < 0 ? 'neg' : 'pos') + ' num">' + (v > 0 ? '+' : '') + v.toFixed(0) + '%</span>';

  async function renderLowest() {
    const list = await getContracts(), rates = getRates();
    const byId = {}; S.hotels.forEach(h => { byId[h.id] = h; });
    const rows = list.map(c => {
      const b = c.booking_id && byId[c.booking_id], d = dhcLowest(rates, c.id);
      const corp = d && d.corp, rack = d && d.rack, now = b && b.price;
      return { c, b, corp, rack, now,
        vs: corp && now ? (now - corp.v) / corp.v * 100 : null,
        vsRack: rack && now ? (now - rack.v) / rack.v * 100 : null };
    });
    rows.sort((x, y) => (x.corp ? x.corp.v : 1e12) - (y.corp ? y.corp.v : 1e12) || (x.now || 1e12) - (y.now || 1e12));
    const cmp = rows.filter(r => r.vs != null), dhcWins = cmp.filter(r => r.vs > 0).length;
    const lowD = rows.filter(r => r.corp).sort((x, y) => x.corp.v - y.corp.v)[0];
    const lowB = rows.filter(r => r.b && r.b.day_low).sort((x, y) => x.b.day_low.price - y.b.day_low.price)[0];

    let html = '<div class="pagehead"><h2>Lowest rates</h2><p>For each hotel with a DHC rate letter: the lowest corporate rate in the letter, the lowest rack rate where the letter gives one, ' +
      'and the cheapest Booking.com room right now and so far today. Every rate is for 2 adults, 1 night from tomorrow, before tax. Single rooms are left out on Booking.com.</p></div>' + ratesPanel(rates);
    html += '<dl class="strip num">' +
      '<div><dt>DHC cheaper than Booking.com</dt><dd>' + (rates ? dhcWins + ' of ' + cmp.length : '—') + '<small>hotels, lowest rate vs lowest rate</small></dd></div>' +
      '<div><dt>Lowest DHC rate</dt><dd>' + (lowD ? n(lowD.corp.v) : '—') + '<small>' + (lowD ? esc(lowD.c.name) : 'load the rate sheet') + '</small></dd></div>' +
      '<div><dt>Lowest Booking.com rate today</dt><dd>' + (lowB ? n(lowB.b.day_low.price) : '—') + '<small>' + (lowB ? esc(lowB.c.name) + ' at ' + fmtTime(lowB.b.day_low.at) : '') + '</small></dd></div></dl>';
    html += '<section><div class="scroll"><table class="ctable lowtable"><thead><tr><th>Hotel</th><th>DHC lowest (corporate)</th><th>Rack (letter)</th><th>Booking.com now</th><th>Booking.com today</th><th>Booking.com vs DHC</th><th>Booking.com vs rack</th></tr></thead><tbody>' +
      rows.map(r => {
        const cls = r.vs == null ? '' : r.vs < 0 ? ' class="v-bad"' : r.vs < 5 ? ' class="v-watch"' : ' class="v-good"';
        return '<tr' + cls + '><td class="hname">' + (r.b ? '<a href="#h-' + esc(r.b.id) + '">' + esc(r.c.name) + '</a>' : esc(r.c.name)) + '</td>' +
          '<td>' + (r.corp ? '<span class="price num">' + n(r.corp.v) + '</span><span class="sub">' + esc(roomLabel(list, r.c, r.corp.room)) + '</span>' : '<span class="na">—</span>') + '</td>' +
          '<td>' + (r.rack ? '<span class="num">' + n(r.rack.v) + '</span><span class="sub">' + esc(roomLabel(list, r.c, r.rack.room)) + '</span>' : '<span class="na">' + (rates ? 'not in letter' : '—') + '</span>') + '</td>' +
          '<td>' + (!r.c.found ? '<span class="na">not on Booking.com</span>' : r.now ? '<span class="price num">' + n(r.now) + '</span><span class="sub">' + esc(r.b.low_room ? r.b.low_room.name : '') + '</span>' : '<span class="na">no rooms on sale</span>') + '</td>' +
          '<td>' + (r.b && r.b.day_low ? '<span class="num">' + n(r.b.day_low.price) + '</span><span class="sub">low at ' + fmtTime(r.b.day_low.at) + (r.b.day_high && r.b.day_high.price !== r.b.day_low.price ? ' · high ' + n(r.b.day_high.price) : '') + '</span>' : '<span class="na">—</span>') + '</td>' +
          '<td>' + vsCell(r.vs) + '</td><td>' + (r.vsRack == null ? '<span class="na">—</span>' : '<span class="num">' + (r.vsRack > 0 ? '+' : '') + r.vsRack.toFixed(0) + '%</span>') + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<p class="unmatched">"Booking.com vs DHC" above zero means DHC\'s lowest corporate rate is cheaper than anything on Booking.com for that hotel. "Today" runs from midnight Karachi time, across the hourly collections.</p></section>';
    app.innerHTML = '<div class="hgrid">' + html + '</div>';
    window.scrollTo(0, 0);
  }

  app.addEventListener('change', e => {
    if (e.target.id !== 'ratefile' || !e.target.files[0]) return;
    const msg = document.getElementById('ratefile-msg');
    e.target.files[0].text().then(t => {
      const r = JSON.parse(t);
      if (r.kind !== 'dhc-contract-rates' || !r.hotels) throw new Error('This is not a DHC rate sheet.');
      try { localStorage.setItem('krb-rates', JSON.stringify(r)); } catch (err) { throw new Error('This browser blocked saving the file.'); }
      route();
    }).catch(err => { msg.textContent = err.message.startsWith('Unexpected') ? 'That file is not valid JSON.' : err.message; });
  });

  function setNav() {
    const view = /^#dhc/.test(location.hash) ? 'dhc' : /^#low/.test(location.hash) ? 'low' : 'market';
    document.querySelectorAll('.nav a').forEach(a => a.setAttribute('aria-current', a.dataset.view === view ? 'page' : 'false'));
  }

  // ---------- shell ----------
  function route() {
    setNav();
    const m = location.hash.match(/^#h-(.+)$/);
    if (/^#dhc/.test(location.hash)) renderContracts();
    else if (/^#low/.test(location.hash)) renderLowest();
    else if (m) renderHotel(decodeURIComponent(m[1])); else renderOverview();
  }

  app.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (b && b.dataset.stars) { state.stars = b.dataset.stars; remember(); return renderOverview(); }
    if (b && b.dataset.period) { state.period = b.dataset.period; remember(); return renderOverview(); }
    if (b && b.dataset.sort) {
      const k = b.dataset.sort;
      state.dir = state.sort === k ? -state.dir : (k === 'name' ? 1 : -1);
      state.sort = k;
      return renderOverview();
    }
    if (b && b.id === 'forget') { try { localStorage.removeItem('krb-rates'); } catch (err) {} return route(); }
    const tr = e.target.closest('tr[data-go]');
    if (tr && !e.target.closest('a')) location.hash = 'h-' + tr.dataset.go;
  });
  app.addEventListener('input', e => {
    if (e.target.id !== 'q') return;
    state.q = e.target.value;
    const pos = e.target.selectionStart;
    renderOverview();
    const q = document.getElementById('q'); q.focus(); q.setSelectionRange(pos, pos);
  });
  window.addEventListener('hashchange', route);

  getSummary().then(s => {
    S = s;
    document.getElementById('sample').hidden = !s.sample;
    showAlert(s);
    document.getElementById('basis').textContent = 'Booking.com rates for hotels with DHC rate letters · 1 room, ' + s.adults + ' adults, 1 night from tomorrow · before tax';
    document.getElementById('stamp').innerHTML = 'Updated <b>' + fmtDay(s.updated) + ', ' + fmtTime(s.updated) + ' PKT</b><br>Check-in priced: ' + fmtDay(s.checkin + 'T12:00:00+05:00');
    const c = s.compared_to;
    document.getElementById('foot').innerHTML =
      'Rates are the prices Booking.com shows in ' + esc(s.currency) + ' for one room, ' + s.adults + ' adults, checking in the next day for 1 night, before tax. ' +
      'Each snapshot prices the next night, so "vs last week" compares today\'s next-night rate with the next-night rate a week ago. ' +
      'Compared with snapshots from ' + ['d1', 'd7', 'd30'].map(k => PERIODS[k] + ': ' + (c[k] ? fmtDay(c[k]) + ' ' + fmtTime(c[k]) : 'not collected yet')).join(', ') + '. ' +
      s.snapshots + ' snapshots kept since ' + fmtDay(s.first) + '.';
    route();
  }).catch(err => {
    app.innerHTML = '<p>Could not load the rates (' + esc(err.message) + '). If this is a fresh setup, the collector has not finished its first run yet.</p>';
  });
})();
