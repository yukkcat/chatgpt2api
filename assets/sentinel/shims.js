// Browser shims shared by the node reference test and the embedded JS engine.
// Must be loaded BEFORE the sentinel SDK.
(function () {
  if (typeof globalThis.atob !== 'function') {
    const B64C = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    globalThis.atob = function (s) {
      s = String(s).replace(/[\t\n\f\r ]/g, '').replace(/=+$/, '');
      let out = '';
      const tbl = [];
      for (let i = 0; i < B64C.length; i++) tbl[B64C.charCodeAt(i)] = i;
      let bits = 0, nbits = 0;
      for (let i = 0; i < s.length; i++) {
        const c = s.charCodeAt(i);
        if (tbl[c] === undefined) continue;
        bits = (bits << 6) | tbl[c];
        nbits += 6;
        if (nbits >= 8) {
          nbits -= 8;
          out += String.fromCharCode((bits >> nbits) & 0xff);
        }
      }
      return out;
    };
    globalThis.btoa = function (s) {
      s = String(s);
      let out = '';
      for (let i = 0; i < s.length; i += 3) {
        const c1 = s.charCodeAt(i) & 0xff;
        const c2 = i + 1 < s.length ? s.charCodeAt(i + 1) & 0xff : NaN;
        const c3 = i + 2 < s.length ? s.charCodeAt(i + 2) & 0xff : NaN;
        out += B64C[c1 >> 2];
        out += B64C[((c1 & 3) << 4) | (isNaN(c2) ? 0 : c2 >> 4)];
        out += isNaN(c2) ? '=' : B64C[((c2 & 15) << 2) | (isNaN(c3) ? 0 : c3 >> 6)];
        out += isNaN(c3) ? '=' : B64C[c3 & 63];
      }
      return out;
    };
  }

  // Fingerprint overrides supplied by the host (must match the HTTP client's headers).
  const FP = globalThis.__SHIM_FP || {};
  const did = FP.oaiDid || 'c1d2e3f4a5b60718293a4b5c6d7e8f90';
  const defUA =
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36';
  const ua = FP.userAgent || defUA;
  const appVersion = FP.appVersion || ua.replace(/^Mozilla\//, '');
  const nav = {
    userAgent: ua,
    appVersion: appVersion,
    appName: 'Netscape',
    appCodeName: 'Mozilla',
    product: 'Gecko',
    productSub: '20030107',
    vendor: 'Google Inc.',
    vendorSub: '',
    language: FP.language || 'zh-CN',
    languages: FP.languages || ['zh-CN', 'zh', 'en'],
    hardwareConcurrency: FP.hardwareConcurrency || 32,
    deviceMemory: FP.deviceMemory || 8,
    webdriver: false,
    platform: FP.platform || 'Win32',
    cookieEnabled: true,
    onLine: true,
    doNotTrack: null,
    maxTouchPoints: 0,
    pdfViewerEnabled: true,
    plugins: { length: 5, item: () => null, namedItem: () => null, refresh: () => {} },
    mimeTypes: { length: 4, item: () => null, namedItem: () => null },
  };

  function makeCtx2d(el) {
    return {
      canvas: el,
      fillStyle: '#000000',
      strokeStyle: '#000000',
      globalAlpha: 1,
      globalCompositeOperation: 'source-over',
      font: '10px sans-serif',
      textBaseline: 'alphabetic',
      textAlign: 'start',
      direction: 'ltr',
      lineWidth: 1,
      lineCap: 'butt',
      lineJoin: 'miter',
      miterLimit: 10,
      lineDashOffset: 0,
      shadowBlur: 0,
      shadowColor: 'rgba(0, 0, 0, 0)',
      shadowOffsetX: 0,
      shadowOffsetY: 0,
      imageSmoothingEnabled: true,
      save() {}, restore() {}, scale() {}, rotate() {}, translate() {}, transform() {}, setTransform() {}, resetTransform() {},
      beginPath() {}, closePath() {}, moveTo() {}, lineTo() {}, arc() {}, arcTo() {}, bezierCurveTo() {},
      quadraticCurveTo() {}, rect() {}, roundRect() {}, fill() {}, stroke() {}, clip() {}, isPointInPath() { return false; },
      fillRect() {}, strokeRect() {}, clearRect() {}, fillText() {}, strokeText() {}, drawImage() {},
      setLineDash() {}, getLineDash() { return []; },
      createLinearGradient() { return { addColorStop() {} }; },
      createRadialGradient() { return { addColorStop() {} }; },
      createConicGradient() { return { addColorStop() {} }; },
      createPattern() { return {}; },
      measureText(s) {
        const w = (s || '').length * 6.5;
        return { width: w, actualBoundingBoxLeft: 0, actualBoundingBoxRight: w, actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2, fontBoundingBoxAscent: 10, fontBoundingBoxDescent: 3 };
      },
      getImageData(x, y, w, h) {
        const ww = Math.max(1, w | 0), hh = Math.max(1, h | 0);
        const data = new Uint8ClampedArray(ww * hh * 4);
        for (let i = 0; i < data.length; i++) data[i] = (i * 37 + 11) % 256;
        return { data, width: ww, height: hh, colorSpace: 'srgb' };
      },
      putImageData() {},
      getTransform() { return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }; },
    };
  }

  function makeEl(tag) {
    const el = {
      tagName: String(tag || 'div').toUpperCase(),
      nodeName: String(tag || 'div').toUpperCase(),
      nodeType: 1,
      style: {},
      dataset: {},
      classList: { add() {}, remove() {}, contains() { return false; }, toggle() {}, item: () => null, length: 0 },
      children: [],
      childNodes: [],
      parentNode: null,
      parentElement: null,
      src: '',
      href: '',
      id: '',
      className: '',
      width: 300,
      height: 150,
      offsetWidth: 100,
      offsetHeight: 20,
      offsetTop: 0,
      offsetLeft: 0,
      clientWidth: 100,
      clientHeight: 20,
      scrollWidth: 100,
      scrollHeight: 20,
      innerText: '',
      textContent: '',
      innerHTML: '',
      value: '',
      checked: false,
      disabled: false,
      hidden: false,
      appendChild(c) { this.children.push(c); if (c) c.parentNode = this; return c; },
      insertBefore(c) { this.children.unshift(c); return c; },
      removeChild(c) { return c; },
      replaceChild(c) { return c; },
      remove() {},
      setAttribute() {}, getAttribute() { return null; }, removeAttribute() {}, hasAttribute() { return false; },
      setAttributeNS() {}, getAttributeNS() { return null; },
      addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
      focus() {}, blur() {}, click() {},
      cloneNode() { return makeEl(tag); },
      contains() { return false; }, matches() { return false; }, closest() { return null; },
      querySelector() { return null; }, querySelectorAll() { return []; },
      getElementsByTagName() { return []; }, getElementsByClassName() { return []; },
      getBoundingClientRect() {
        return { x: 0, y: 0, top: 0, left: 0, right: 100, bottom: 20, width: 100, height: 20, toJSON() { return this; } };
      },
      getClientRects() { return [{ x: 0, y: 0, width: 100, height: 20, top: 0, left: 0, right: 100, bottom: 20 }]; },
      getContext(kind) { return kind === '2d' ? makeCtx2d(el) : null; },
      toDataURL() { return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='; },
      toBlob(cb) { if (cb) cb(null); },
      play() {}, pause() {}, load() {},
      requestFullscreen() { return Promise.resolve(); },
      animate() { return { cancel() {}, finish() {}, play() {}, pause() {} }; },
      getRootNode() { return globalThis.document; },
    };
    return el;
  }

  const doc = {
    scripts: [],
    cookie: FP.cookie || ('oai-did=' + did + '; oai-lang=zh-CN'),
    readyState: 'complete',
    hidden: false,
    visibilityState: 'visible',
    title: 'ChatGPT',
    referrer: '',
    characterSet: 'UTF-8',
    contentType: 'text/html',
    domain: 'chatgpt.com',
    URL: 'https://chatgpt.com/',
    documentURI: 'https://chatgpt.com/',
    compatMode: 'CSS1Compat',
    location: { href: 'https://chatgpt.com/', origin: 'https://chatgpt.com', pathname: '/', protocol: 'https:', host: 'chatgpt.com', hostname: 'chatgpt.com', port: '', search: '', hash: '', ancestorOrigins: { length: 0 } },
    documentElement: makeEl('html'),
    head: makeEl('head'),
    body: makeEl('body'),
    createElement: makeEl,
    createElementNS: makeEl,
    createTextNode(t) { return { textContent: String(t), nodeType: 3, parentNode: null }; },
    createDocumentFragment() { return makeEl('fragment'); },
    getElementById() { return null; },
    getElementsByTagName() { return []; },
    getElementsByClassName() { return []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    hasFocus() { return true; },
    elementFromPoint() { return null; },
    elementsFromPoint() { return []; },
    getSelection() { return { toString: () => '', rangeCount: 0 }; },
    write() {}, writeln() {}, open() {}, close() {},
  };

  const store = {
    STATSIG_LOCAL_STORAGE_INTERNAL_STORE_V4: '{}',
    STATSIG_LOCAL_STORAGE_STABLE_ID: '7f3c1a2b4d5e6f708192a3b4c5d6e7f8',
    'client-correlated-secret': '9a8b7c6d5e4f30211f2e3d4c5b6a7988',
    'oai/apps/capExpiresAt': String(Date.now() + 86400000),
    'oai-did': did,
    STATSIG_LOCAL_STORAGE_LOGGING_REQUEST: '{}',
    'UiState.isNavigationCollapsed.1': 'false',
  };
  const localStorageShim = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { for (const k of Object.keys(store)) delete store[k]; },
    key: (i) => Object.keys(store)[i] || null,
    get length() { return Object.keys(store).length; },
  };

  globalThis.window = globalThis;
  globalThis.self = globalThis;
  globalThis.top = globalThis;
  globalThis.parent = globalThis;
  globalThis.frames = globalThis;
  globalThis.document = doc;
  globalThis.navigator = nav;
  globalThis.localStorage = localStorageShim;
  globalThis.sessionStorage = localStorageShim;
  globalThis.location = doc.location;
  globalThis.performance = { now: () => Date.now(), timeOrigin: Date.now() - 1000, memory: undefined };
  if (typeof globalThis.crypto !== 'object' || !globalThis.crypto) {
    globalThis.crypto = {
      randomUUID: () => '12345678-1234-4123-8123-123456789abc',
      getRandomValues: (arr) => { for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256); return arr; },
    };
  }
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.dispatchEvent = () => true;
  globalThis.postMessage = () => {};
  globalThis.matchMedia = () => ({ matches: false, media: '', addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  const sw = FP.screenWidth || 2560;
  const sh = FP.screenHeight || 1440;
  globalThis.screen = {
    width: sw, height: sh, availWidth: sw, availHeight: sh,
    colorDepth: 24, pixelDepth: 24, availLeft: 0, availTop: 0,
    orientation: { angle: 0, type: 'landscape-primary', onchange: null },
  };
  globalThis.devicePixelRatio = FP.devicePixelRatio || 1.25;
  globalThis.innerWidth = sw;
  globalThis.innerHeight = sh - 120;
  globalThis.outerWidth = sw;
  globalThis.outerHeight = sh - 60;
  globalThis.screenX = 0;
  globalThis.screenY = 0;
  globalThis.screenLeft = 0;
  globalThis.screenTop = 0;
  globalThis.scrollX = 0;
  globalThis.scrollY = 0;
  globalThis.pageXOffset = 0;
  globalThis.pageYOffset = 0;
  globalThis.chrome = { runtime: {}, app: { isInstalled: false, InstallState: {}, RunningState: {} }, csi: () => ({}), loadTimes: () => ({}) };
  globalThis.history = {
    length: 2, scrollRestoration: 'auto', state: null,
    pushState() {}, replaceState() {}, go() {}, back() {}, forward() {},
  };
  globalThis.Notification = function () {};
  globalThis.Notification.permission = 'default';
  globalThis.Notification.requestPermission = () => Promise.resolve('default');
  globalThis.RTCPeerConnection = function () { throw new Error('not available'); };
  globalThis.webkitRTCPeerConnection = globalThis.RTCPeerConnection;
  globalThis.AudioContext = function () { throw new Error('not available'); };
  globalThis.webkitAudioContext = globalThis.AudioContext;
  globalThis.OfflineAudioContext = function () { throw new Error('not available'); };
  globalThis.MediaStream = function () {};
  globalThis.indexedDB = { open: () => ({ onsuccess: null, onerror: null, onupgradeneeded: null }) };
  globalThis.caches = { keys: () => Promise.resolve([]), open: () => Promise.resolve({}) };
  globalThis.requestAnimationFrame = (cb) => (typeof setTimeout === 'function' ? setTimeout(() => cb(Date.now()), 16) : 0);
  globalThis.cancelAnimationFrame = (id) => { if (typeof clearTimeout === 'function') clearTimeout(id); };
  globalThis.XMLHttpRequest = function () { this.open = () => {}; this.send = () => {}; this.setRequestHeader = () => {}; };
  globalThis.Worker = function () { throw new Error('not available'); };
  globalThis.speechSynthesis = { getVoices: () => [], speaking: false, pending: false, paused: false };
  globalThis.MutationObserver = function () { this.observe = () => {}; this.disconnect = () => {}; this.takeRecords = () => []; };
  globalThis.IntersectionObserver = globalThis.MutationObserver;
  globalThis.ResizeObserver = globalThis.MutationObserver;
  globalThis.PerformanceObserver = globalThis.MutationObserver;
  globalThis.CSS = { supports: () => true, escape: (s) => String(s) };
  globalThis.WebGLRenderingContext = function () {};
  globalThis.HTMLCanvasElement = function () {};
  globalThis.HTMLIFrameElement = function () {};
  globalThis.HTMLElement = function () {};
  globalThis.Element = function () {};
  globalThis.Node = function () {};
  globalThis.Event = function (t) { this.type = t; };
  globalThis.CustomEvent = globalThis.Event;
  globalThis.ondeviceorientation = null;
  globalThis.ondevicemotion = null;
  globalThis.openDatabase = undefined;
  globalThis.showOpenFilePicker = undefined;
  globalThis.queryLocalFonts = undefined;

  // ---- web platform APIs missing from bare V8 ----
  if (typeof globalThis.TextEncoder !== 'function') {
    globalThis.TextEncoder = function TextEncoder() {
      this.encoding = 'utf-8';
      this.encode = function (s) {
        s = String(s == null ? '' : s);
        const out = [];
        for (let i = 0; i < s.length; i++) {
          let c = s.charCodeAt(i);
          if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
            const c2 = s.charCodeAt(i + 1);
            if (c2 >= 0xdc00 && c2 <= 0xdfff) {
              c = ((c - 0xd800) << 10) + (c2 - 0xdc00) + 0x10000;
              i++;
            }
          }
          if (c < 0x80) out.push(c);
          else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
          else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
          else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
        }
        return new Uint8Array(out);
      };
      this.encodeInto = function (s, dest) {
        const bytes = this.encode(s);
        const n = Math.min(bytes.length, dest.length);
        for (let i = 0; i < n; i++) dest[i] = bytes[i];
        return { read: s.length, written: n };
      };
    };
  }
  if (typeof globalThis.TextDecoder !== 'function') {
    globalThis.TextDecoder = function TextDecoder() {
      this.encoding = 'utf-8';
      this.decode = function (buf) {
        if (!buf) return '';
        const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf.buffer || buf);
        let out = '';
        for (let i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i]);
        return out;
      };
    };
  }
  if (typeof globalThis.URL !== 'function') {
    globalThis.URL = function URL(input, base) {
      const raw = String(input == null ? '' : input);
      let href = raw;
      if (base && !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) {
        const b = String(base).replace(/[^/]*$/, '');
        href = b + raw;
      }
      if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href)) href = 'https://chatgpt.com/' + href.replace(/^\/+/, '');
      const m = /^([a-zA-Z][a-zA-Z0-9+.-]*:)\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/.exec(href) || [];
      const scheme = m[1] || 'https:';
      const hostpart = m[2] || 'chatgpt.com';
      const path = m[3] || '/';
      const query = m[4] || '';
      const hash = m[5] || '';
      const hostIdx = hostpart.lastIndexOf(':');
      this.href = scheme + '//' + hostpart + path + query + hash;
      this.protocol = scheme;
      this.host = hostpart;
      this.hostname = hostIdx > 0 ? hostpart.slice(0, hostIdx) : hostpart;
      this.port = hostIdx > 0 ? hostpart.slice(hostIdx + 1) : '';
      this.pathname = path;
      this.search = query;
      this.hash = hash;
      this.origin = scheme + '//' + hostpart;
      this.username = '';
      this.password = '';
      this.searchParams = {
        get: () => null, has: () => false, set() {}, append() {}, delete() {}, keys: () => [][Symbol.iterator](),
        entries: () => [][Symbol.iterator](), values: () => [][Symbol.iterator](), forEach() {}, toString: () => '',
      };
      this.toString = () => this.href;
      this.toJSON = () => this.href;
    };
    globalThis.URL.createObjectURL = () => 'blob:https://chatgpt.com/00000000-0000-0000-0000-000000000000';
    globalThis.URL.revokeObjectURL = () => {};
  }
  if (typeof globalThis.URLSearchParams !== 'function') {
    globalThis.URLSearchParams = function URLSearchParams(init) {
      this._p = [];
      if (typeof init === 'string') {
        init.replace(/^\?/, '').split('&').filter(Boolean).forEach((kv) => {
          const i = kv.indexOf('=');
          this._p.push([decodeURIComponent(i < 0 ? kv : kv.slice(0, i)), decodeURIComponent(i < 0 ? '' : kv.slice(i + 1))]);
        });
      }
      this.get = (k) => { const e = this._p.find((x) => x[0] === k); return e ? e[1] : null; };
      this.has = (k) => this._p.some((x) => x[0] === k);
      this.set = (k, v) => { this.delete(k); this._p.push([k, String(v)]); };
      this.append = (k, v) => { this._p.push([k, String(v)]); };
      this.delete = (k) => { this._p = this._p.filter((x) => x[0] !== k); };
      this.forEach = (fn) => { this._p.forEach((x) => fn(x[1], x[0], this)); };
      this.keys = () => this._p.map((x) => x[0])[Symbol.iterator]();
      this.values = () => this._p.map((x) => x[1])[Symbol.iterator]();
      this.entries = () => this._p.map((x) => [x[0], x[1]])[Symbol.iterator]();
      this[Symbol.iterator] = () => this.entries();
      this.toString = () => this._p.map((x) => encodeURIComponent(x[0]) + '=' + encodeURIComponent(x[1])).join('&');
    };
  }
  if (typeof globalThis.Blob !== 'function') {
    globalThis.Blob = function Blob(parts, opts) {
      this.size = (parts || []).reduce((n, p) => n + (p && p.length ? p.length : 0), 0);
      this.type = (opts && opts.type) || '';
      this.slice = () => new globalThis.Blob();
      this.text = () => Promise.resolve('');
      this.arrayBuffer = () => Promise.resolve(new ArrayBuffer(0));
    };
  }
  if (typeof globalThis.DOMException !== 'function') {
    globalThis.DOMException = function DOMException(msg, name) { this.message = msg; this.name = name || 'Error'; };
  }
  if (typeof globalThis.AbortController !== 'function') {
    globalThis.AbortController = function AbortController() {
      this.signal = { aborted: false, addEventListener() {}, removeEventListener() {}, onabort: null };
      this.abort = () => { this.signal.aborted = true; };
    };
  }
  if (typeof globalThis.EventTarget !== 'function') {
    globalThis.EventTarget = function EventTarget() {
      this.addEventListener = () => {};
      this.removeEventListener = () => {};
      this.dispatchEvent = () => true;
    };
  }
  if (typeof globalThis.Image !== 'function') {
    globalThis.Image = function Image() { return makeEl('img'); };
  }
  if (typeof globalThis.console !== 'object' || !globalThis.console) {
    const noop = () => {};
    globalThis.console = { log: noop, warn: noop, error: noop, info: noop, debug: noop, trace: noop, dir: noop, table: noop };
  }
  if (typeof globalThis.fetch !== 'function') {
    globalThis.fetch = () => Promise.reject(new Error('fetch not available'));
  }
})();
