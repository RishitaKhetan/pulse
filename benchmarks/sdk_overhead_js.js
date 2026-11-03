// Benchmark: how much does the JS SDK (pulse/static/pulse.js) slow down an app?
// Target from CLAUDE.md: under 2% overhead.
//
// Runs the real pulse.js in Node with a pretend browser. The browser's
// fetch() sends in the background, so we count the time the SDK spends on
// the page's own thread: track() calls plus preparing each batch.
//
// Run it with:   node benchmarks/sdk_overhead_js.js
const fs = require('fs');
const path = require('path');

const code = fs.readFileSync(path.join(__dirname, '..', 'pulse', 'static', 'pulse.js'), 'utf8');
let sends = 0;
const win = {
  location: { href: 'http://localhost:8000/shop', pathname: '/shop', hash: '' },
  addEventListener() {},
};
const doc = { referrer: '', visibilityState: 'visible', addEventListener() {} };
const fakeFetch = () => { sends++; return Promise.resolve({ ok: true }); };
const hist = { pushState() {} };
new Function('window', 'document', 'fetch', 'history', 'sessionStorage', code)(
  win, doc, fakeFetch, hist, { getItem: () => null, setItem() {} },
);
const Pulse = win.Pulse;
Pulse.init({ autoTrack: false });

// Pretend page work for one user interaction: build ~2 ms of data, like rendering a list
function handleClick(i) {
  const items = [];
  for (let n = 0; n < 6000; n++) items.push({ id: n, name: 'product ' + n, price: n * 1.5 });
  return JSON.stringify({ click: i, items }).length;
}

function round(withPulse, n) {
  const t = process.hrtime.bigint();
  for (let i = 0; i < n; i++) {
    handleClick(i);
    if (withPulse) Pulse.track('add_to_cart', { product_id: i % 6, price: 49 });
  }
  return Number(process.hrtime.bigint() - t) / 1e6;
}

const N = 200, ROUNDS = 20;
round(false, N); round(true, N); // warm-up
const ratios = [], base = [];
for (let r = 0; r < ROUNDS; r++) {
  // swap order every round so CPU speed changes don't bias the result
  let a, b;
  if (r % 2 === 0) { a = round(false, N); b = round(true, N); } else { b = round(true, N); a = round(false, N); }
  ratios.push(b / a); base.push(a);
}
const median = xs => xs.slice().sort((x, y) => x - y)[Math.floor(xs.length / 2)];

// Direct cost of one track() call, measured on its own
const M = 100000, t = process.hrtime.bigint();
for (let i = 0; i < M; i++) Pulse.track('add_to_cart', { product_id: 1 });
const perCallUs = Number(process.hrtime.bigint() - t) / 1e3 / M;

const overhead = (median(ratios) - 1) * 100;
console.log(`Page work per interaction: ${(median(base) / N).toFixed(2)} ms`);
console.log(`Cost of one Pulse.track(): about ${perCallUs.toFixed(1)} microseconds (${sends} batches sent)`);
console.log(`${overhead < 2 ? 'PASS' : 'FAIL'}: overhead ${overhead.toFixed(2)}% (target: under 2%)`);
