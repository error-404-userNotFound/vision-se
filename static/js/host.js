import * as THREE from '/static/vendor/three/build/three.module.js';

/* ---------------- One Euro Filter ---------------- */
class LowPass {
  constructor(alpha, y0 = 0) {
    this.a = alpha;
    this.y = y0;
    this.s = y0;
    this.initialized = false;
  }
  setAlpha(a) { this.a = a; }
  filter(x) {
    let y = x;
    if (this.initialized) y = this.a * x + (1 - this.a) * this.s;
    this.s = y;
    this.initialized = true;
    return y;
  }
}
function alpha(dt, cutoff) {
  const tau = 1 / (2 * Math.PI * cutoff);
  return 1 / (1 + tau / dt);
}
class OneEuro {
  constructor(freq = 60, minCutoff = 1.2, beta = 0.3, dCutoff = 1.0) {
    this.freq = freq;
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    this.xFilt = new LowPass(alpha(1 / freq, minCutoff));
    this.dxFilt = new LowPass(alpha(1 / freq, dCutoff));
    this.lastT = null;
    this.lastX = null;
  }
  filter(x, t) {
    if (this.lastT === null) {
      this.lastT = t;
      this.lastX = x;
      return x;
    }
    let dt = (t - this.lastT) / 1000;
    dt = Math.max(1e-3, Math.min(0.05, dt)); // clamp dt to avoid extreme gains
    this.lastT = t;

    const dx = (x - this.lastX) / dt;
    this.lastX = x;

    const edx = this.dxFilt.filter(dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    this.xFilt.setAlpha(alpha(dt, cutoff));
    return this.xFilt.filter(x);
  }
}

// Helpers for unwrapping angles (used only in One-Euro mode)
function unwrap(prev, curr) {
  let d = curr - prev;
  while (d >  Math.PI) { curr -= 2 * Math.PI; d = curr - prev; }
  while (d < -Math.PI) { curr += 2 * Math.PI; d = curr - prev; }
  return curr;
}
function clampAngleDelta(prev, curr, maxDelta) {
  let d = curr - prev;
  if (d >  maxDelta) return prev + maxDelta;
  if (d < -maxDelta) return prev - maxDelta;
  return curr;
}

/* ---------------- Render / stream parameters ---------------- */
let HOST_RENDER_WIDTH  = 5600;
let HOST_RENDER_HEIGHT = 3150;

// Renderer FPS
const HOST_RENDER_FPS    = 60;

// How often to pull new MJPEG frames (ms)
const MJPEG_TEXTURE_INTERVAL_MS = 40;

// WebRTC signaling polling (ms)
const SIGNAL_POLL_INTERVAL_MS   = 1000;

/* ---------------- DOM refs ---------------- */
const canvas   = document.getElementById('hostCanvas');
const mjpegImg = document.getElementById('mjpegHost');
const statusEl = document.getElementById('statusHost');

/* ---------------- Renderer & scene ---------------- */
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setPixelRatio(1);
renderer.setSize(HOST_RENDER_WIDTH, HOST_RENDER_HEIGHT, false);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const head = new THREE.Object3D();
scene.add(head);

const fov = 75, near = 0.03, far = 100;
const camera = new THREE.PerspectiveCamera(fov, HOST_RENDER_WIDTH / HOST_RENDER_HEIGHT, near, far);
head.add(camera);

scene.add(new THREE.GridHelper(10, 20, 0x333333, 0x222222));

/* ---------------- Shared settings ---------------- */
const settings = {
  screenScale: 2.36,
  screenDist:  1.50,
  screenCurveRadius: 6.0,
  eyePx:       16,
  converge:    false,
  camEnabled:  false,
  camOpacity:  100,
  camLens:     'wide',
  camFeedProfile: 'low',
  camBlend:    'screen',
  cursorEnabled: false,
  cursorSafePx:  1,
  cursorHz:      40,
  cursorGainX:   1.0,
  cursorGainY:   1.0,
  cursorSmoothing: 0.25,
  cursorJumpPx: 30,
  recenterNonce: 0,
  hostRenderWidth: 5600,
  hostRenderHeight:3150,
  mjpegWidth: 12000,
  mjpegFps:   30,
  hostTextureWidth: 4096,
  camMaxWidth:  480,
  camMaxHeight: 270,
  camMaxFps:    24,
  gestureEnabled: false,
  gestureInactiveMs: 700.0,
  gestureDoublePinchMs: 1750.0,
  gesturePinchOn: 0.30,
  gesturePinchOff: 0.42,
  gestureFrameWidth: 424.0,
  gestureFrameHeight: 240.0,
  gestureFrameFps: 12.0,
  gestureMirrorX: false,
  gestureDragDetectEnabled: true,
  gestureDragAdjMinRatio: 0.24,
  gestureDragThumbIndexMinRatio: 0.32,
  gestureDragExtendRatio: 1.08,
  gestureDragScaleGain: 1.0,
  gestureKeypointStreamEnabled: true,
  gestureSwapHands: false,
  filterMode: 'one_euro',
  version: 0,
  origin: 'server'
};
let lastRecenterNonce = 0;
let filterMode = 'one_euro';

/* ---------------- Screen mesh (Mac MJPEG texture) ---------------- */
let sourceAspect = 1280 / 800;

const texCanvas = document.createElement('canvas');
const texCtx    = texCanvas.getContext('2d');
texCanvas.width = 4096;
texCanvas.height = 2560;

let screenTex = new THREE.CanvasTexture(texCanvas);
screenTex.colorSpace = THREE.SRGBColorSpace;
screenTex.flipY = false;
screenTex.minFilter = THREE.LinearFilter;
screenTex.magFilter = THREE.LinearFilter;

const screenMat = new THREE.MeshBasicMaterial({
  map: screenTex,
  toneMapped: false,
  side: THREE.FrontSide
});
const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), screenMat);
scene.add(screenMesh);

// Direction from head where the screen is anchored
let screenAnchorDir = new THREE.Vector3(0, 0, -1);

let curvedGeomKey = '';
function buildCurvedGeometry(width, height, radius) {
  const safeW = Math.max(0.01, width);
  const safeH = Math.max(0.01, height);
  const safeRadius = Math.max(0.6, radius || 6.0);
  const segW = Math.max(48, Math.min(220, Math.round(safeW * 40)));
  const geo = new THREE.PlaneGeometry(safeW, safeH, segW, 1);

  // Arc length ~= safeW and capped angle prevents over-folding for tiny radii.
  const maxTheta = 2.6;
  const theta = Math.max(1e-3, Math.min(maxTheta, safeW / safeRadius));
  const bendRadius = safeW / theta;

  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const a = x / bendRadius;
    const bx = Math.sin(a) * bendRadius;
    const bz = bendRadius * (1 - Math.cos(a));
    pos.setXYZ(i, bx, y, bz);
  }
  pos.needsUpdate = true;
  geo.computeVertexNormals();
  return geo;
}

function updateCurvedGeometry(width, height, radius) {
  const key = `${width.toFixed(4)}|${height.toFixed(4)}|${radius.toFixed(4)}`;
  if (key === curvedGeomKey) return;
  curvedGeomKey = key;
  const next = buildCurvedGeometry(width, height, radius);
  if (screenMesh.geometry) screenMesh.geometry.dispose();
  screenMesh.geometry = next;
}

const DRAG_SCALE_MIN = 0.25;
const DRAG_SCALE_MAX = 8.0;
let dragScaleOffset = 1.0;
let dragScaleTracking = false;
let dragBaselineSpanPx = 0.0;
let dragBaselineScaleOffset = 1.0;

function clampRange(v, lo, hi) {
  return Math.max(lo, Math.min(hi, Number(v)));
}

function getEffectiveScreenScale() {
  const base = Math.max(0.05, Number(settings.screenScale) || 1.0);
  const scale = base * Math.max(0.05, Number(dragScaleOffset) || 1.0);
  return clampRange(scale, DRAG_SCALE_MIN, DRAG_SCALE_MAX);
}

function applyScreenTransform() {
  const h = getEffectiveScreenScale();
  const w = h * sourceAspect;
  const r = Math.max(0.6, settings.screenCurveRadius || 6.0);
  updateCurvedGeometry(w, h, r);
  const pos = screenAnchorDir.clone().normalize().multiplyScalar(settings.screenDist);
  screenMesh.position.copy(pos);
  screenMesh.lookAt(new THREE.Vector3(0, 0, 0));
}

/* ---------------- MJPEG source ---------------- */
mjpegImg.src = `/screen.mjpeg?ts=${Date.now()}`;
let mjpegAdopted = false;

function recreateScreenTexture() {
  if (screenTex) screenTex.dispose();
  screenTex = new THREE.CanvasTexture(texCanvas);
  screenTex.colorSpace = THREE.SRGBColorSpace;
  screenTex.flipY = false;
  screenTex.minFilter = THREE.LinearFilter;
  screenTex.magFilter = THREE.LinearFilter;
  screenMesh.material.map = screenTex;
  screenMesh.material.needsUpdate = true;
}

function textureTargetWidthPx() {
  const w = Math.round(Number(settings.hostTextureWidth) || 3072);
  return Math.max(1024, Math.min(6144, w));
}

function applyTextureSizeForAspect(aspect, force = false) {
  const safeAspect = Math.max(1e-6, Number(aspect) || (1280 / 800));
  const base = textureTargetWidthPx();
  let tw = base;
  let th = base;
  if (safeAspect >= 1.0) {
    tw = base;
    th = Math.max(1, Math.round(base / safeAspect));
  } else {
    th = base;
    tw = Math.max(1, Math.round(base * safeAspect));
  }
  if (!force && texCanvas.width === tw && texCanvas.height === th) return;
  texCanvas.width = tw;
  texCanvas.height = th;
  recreateScreenTexture();
}

function adoptAspectIfReady() {
  if (mjpegImg.naturalWidth > 0 && mjpegImg.naturalHeight > 0) {
    mjpegAdopted = true;
    sourceAspect = mjpegImg.naturalWidth / mjpegImg.naturalHeight;
    applyTextureSizeForAspect(sourceAspect);
    applyScreenTransform();
  }
}
mjpegImg.addEventListener('load', adoptAspectIfReady);

function updateScreenTexture(now) {
  if (now - (updateScreenTexture._last || 0) < MJPEG_TEXTURE_INTERVAL_MS) return;
  try {
    const ctx = texCtx;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, texCanvas.width, texCanvas.height);
    ctx.translate(0, texCanvas.height);
    ctx.scale(1, -1);
    ctx.drawImage(mjpegImg, 0, 0, texCanvas.width, texCanvas.height);
    ctx.restore();
    screenTex.needsUpdate = true;
  } catch (e) {
    // transient errors ignored
  }
  adoptAspectIfReady();
  updateScreenTexture._last = now;
}

/* ---------------- Device orientation (from phone) ---------------- */
const zee   = new THREE.Vector3(0, 0, 1);
const euler = new THREE.Euler();
const q0    = new THREE.Quaternion();
const qScreen = new THREE.Quaternion();
const targetQ = new THREE.Quaternion();
const calibInv = new THREE.Quaternion();

let haveOrientation = false;
let haveCalib       = false;

// Raw last angles (radians)
let lastAlpha = 0, lastBeta = 0, lastGamma = 0;

// Filtered angles for One-Euro
let filtAlpha = 0, filtBeta = 0, filtGamma = 0;

// For unwrap & filter
let aPrev = 0, bPrev = 0, gPrev = 0;

const filtA = new OneEuro(60, 1.2, 0.3, 1.0);
const filtB = new OneEuro(60, 1.2, 0.3, 1.0);
const filtG = new OneEuro(60, 1.2, 0.3, 1.0);

function setObjectQuaternion(outQ, alpha, beta, gamma, orient) {
  euler.set(beta, alpha, -gamma, 'YXZ');
  outQ.setFromEuler(euler);
  q0.setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
  outQ.multiply(q0);
  qScreen.setFromAxisAngle(zee, -orient);
  outQ.multiply(qScreen);
}

function handleOrientationMessage(msg) {
  const t = msg.t || performance.now();
  const aRaw = THREE.MathUtils.degToRad(msg.alphaDeg || 0);
  const bRaw = THREE.MathUtils.degToRad(msg.betaDeg  || 0);
  const gRaw = THREE.MathUtils.degToRad(msg.gammaDeg || 0);
  const orient = THREE.MathUtils.degToRad(msg.orientDeg || 0);

  lastAlpha = aRaw;
  lastBeta  = bRaw;
  lastGamma = gRaw;

  if (filterMode === 'one_euro') {
    // Unwrap for the filter only
    let a = unwrap(aPrev, aRaw);
    let b = unwrap(bPrev, bRaw);
    let g = unwrap(gPrev, gRaw);

    const maxDelta = Math.PI / 2;
    a = clampAngleDelta(aPrev, a, maxDelta);
    b = clampAngleDelta(bPrev, b, maxDelta);
    g = clampAngleDelta(gPrev, g, maxDelta);

    aPrev = a;
    bPrev = b;
    gPrev = g;

    filtAlpha = filtA.filter(a, t);
    filtBeta  = filtB.filter(b, t);
    filtGamma = filtG.filter(g, t);

    setObjectQuaternion(targetQ, filtAlpha, filtBeta, filtGamma, orient);
  } else {
    // Simple mode: raw angles only
    setObjectQuaternion(targetQ, aRaw, bRaw, gRaw, orient);
  }

  haveOrientation = true;
}

/* ---------------- Recenter (via recenterNonce) ---------------- */
function applyRecenter() {
  calibInv.copy(targetQ).invert();
  haveCalib = true;

  const tmpQ = targetQ.clone();
  tmpQ.premultiply(calibInv);
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(tmpQ).normalize();
  screenAnchorDir.copy(fwd);
  applyScreenTransform();
}

/* ---------------- Gesture drag tracking (server-driven) ---------------- */
let pullingGestureStatus = false;

function clamp01(v) {
  return Math.max(0, Math.min(1, Number(v)));
}

function getRollStableHeadBasis() {
  // Drag placement should follow yaw/pitch, but not inherit transient head roll,
  // otherwise dragged windows can end up with unwanted apparent tilt.
  const worldUp = new THREE.Vector3(0, 1, 0);
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(head.quaternion).normalize();
  let right = new THREE.Vector3().crossVectors(fwd, worldUp);
  if (right.lengthSq() < 1e-6) {
    right = new THREE.Vector3(1, 0, 0);
  } else {
    right.normalize();
  }
  const up = new THREE.Vector3().crossVectors(right, fwd).normalize();
  return { fwd, right, up };
}

function applyTrackingAnchor(normX, normY) {
  const u = clamp01(normX);
  const v = clamp01(normY);
  const fovY = THREE.MathUtils.degToRad(camera.fov || 75);
  const tanY = Math.tan(fovY * 0.5);
  const tanX = tanY * Math.max(0.5, camera.aspect || (HOST_RENDER_WIDTH / HOST_RENDER_HEIGHT));
  const x = (u - 0.5) * 2.0 * tanX;
  const y = (0.5 - v) * 2.0 * tanY;
  const basis = getRollStableHeadBasis();
  const worldDir = basis.fwd.clone()
    .addScaledVector(basis.right, x)
    .addScaledVector(basis.up, y)
    .normalize();
  screenAnchorDir.copy(worldDir);
  applyScreenTransform();
}

function updateDragScaleFromStatus(gs) {
  const tracking = !!(gs && gs.trackingEnabled);
  if (!tracking || !settings.gestureDragDetectEnabled) {
    if (dragScaleTracking) {
      dragScaleTracking = false;
      dragBaselineSpanPx = 0.0;
      dragBaselineScaleOffset = dragScaleOffset;
    }
    return;
  }

  const spanPx = Math.max(0, Number(gs.dragHandSpanPx || 0));
  if (!dragScaleTracking) {
    dragScaleTracking = true;
    dragBaselineSpanPx = Math.max(1.0, spanPx);
    dragBaselineScaleOffset = dragScaleOffset;
  }
  if (spanPx <= 1.0 || dragBaselineSpanPx <= 1.0) {
    return;
  }

  const ratio = spanPx / dragBaselineSpanPx;
  const gain = clampRange(Number(settings.gestureDragScaleGain) || 1.0, 0.40, 3.00);
  const ratioAdj = Math.pow(Math.max(0.05, ratio), gain);
  const nextOffset = clampRange(dragBaselineScaleOffset * ratioAdj, 0.20, 5.0);
  if (Math.abs(nextOffset - dragScaleOffset) > 0.001) {
    dragScaleOffset = nextOffset;
    applyScreenTransform();
  }
}

async function pullGestureStatus() {
  if (pullingGestureStatus) return;
  pullingGestureStatus = true;
  try {
    const r = await fetch('/gesture_status', { cache: 'no-store' });
    if (!r.ok) return;
    const gs = await r.json();
    if (!gs) return;
    if (!settings.gestureDragDetectEnabled) {
      updateDragScaleFromStatus({ trackingEnabled: false });
      return;
    }
    if (gs.trackingEnabled) {
      applyTrackingAnchor(gs.trackingCenterNormX, gs.trackingCenterNormY);
    }
    updateDragScaleFromStatus(gs);
  } catch {
    // ignore
  } finally {
    pullingGestureStatus = false;
  }
}

/* ---------------- Settings sync ---------------- */
let pullingSettings = false;
async function pullSettings() {
  if (pullingSettings) return;
  pullingSettings = true;
  try {
    const r = await fetch('/settings', { cache: 'no-store' });
    if (!r.ok) return;
    const s = await r.json();
    const prevTextureWidth = Math.round(Number(settings.hostTextureWidth || 3072));
    let changed = false;
    for (const k of Object.keys(settings)) {
      if (s[k] !== undefined && settings[k] !== s[k]) {
        settings[k] = s[k];
        changed = true;
      }
    }
    if (changed) {
      // Host render resolution
      if (settings.hostRenderWidth && settings.hostRenderHeight) {
        const w = Math.max(640, Math.round(settings.hostRenderWidth));
        const h = Math.max(360, Math.round(settings.hostRenderHeight));
        if (w !== HOST_RENDER_WIDTH || h !== HOST_RENDER_HEIGHT) {
          HOST_RENDER_WIDTH  = w;
          HOST_RENDER_HEIGHT = h;
          renderer.setSize(HOST_RENDER_WIDTH, HOST_RENDER_HEIGHT, false);
          camera.aspect = HOST_RENDER_WIDTH / HOST_RENDER_HEIGHT;
          camera.updateProjectionMatrix();
        }
      }
      filterMode = (settings.filterMode === 'simple') ? 'simple' : 'one_euro';
      const nextTextureWidth = Math.round(Number(settings.hostTextureWidth || 3072));
      if (nextTextureWidth !== prevTextureWidth) {
        applyTextureSizeForAspect(sourceAspect || (1280 / 800), true);
      }

      applyScreenTransform();
      if (settings.recenterNonce !== lastRecenterNonce) {
        lastRecenterNonce = settings.recenterNonce;
        applyRecenter();
      }
    }
  } catch (e) {
    // ignore
  } finally {
    pullingSettings = false;
  }
}
setInterval(pullSettings, 1500);
setInterval(pullGestureStatus, 20);

/* ---------------- Gaze → mouse ---------------- */
const raycaster = new THREE.Raycaster();
const plane = new THREE.Plane();
const ray   = new THREE.Ray();

const uvU = new OneEuro(60, 1.2 + 1.2 * settings.cursorSmoothing, 0.3, 1.0);
const uvV = new OneEuro(60, 1.2 + 1.2 * settings.cursorSmoothing, 0.3, 1.0);

let geomCached = null;
async function getScreenGeom() {
  if (geomCached) return geomCached;
  try {
    const r = await fetch('/screen_geom', { cache: 'no-store' });
    if (!r.ok) return null;
    geomCached = await r.json();
    return geomCached;
  } catch {
    return null;
  }
}

let lastCursorSend = 0;
let lastSentPx = null, lastSentPy = null;
let phoneLinkActive = false;

function minCursorIntervalMs() {
  return Math.max(5, 1000 / Math.max(1, settings.cursorHz | 0));
}

async function maybeSendCursor(nowMs) {
  if (!settings.cursorEnabled || !phoneLinkActive || !haveOrientation || !haveCalib) {
    return;
  }
  if (nowMs - lastCursorSend < minCursorIntervalMs()) return;

  const q = head.quaternion;
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(q).normalize();
  const origin = new THREE.Vector3(0, 0, 0);

  raycaster.set(origin, fwd);
  const hits = raycaster.intersectObject(screenMesh, false);

  let u, v, hadHit = false;
  if (hits && hits.length > 0 && hits[0].uv) {
    u = hits[0].uv.x;
    v = 1.0 - hits[0].uv.y;
    hadHit = true;
  } else {
    const center = screenMesh.getWorldPosition(new THREE.Vector3());
    const n = screenMesh.getWorldDirection(new THREE.Vector3()).normalize();
    plane.setFromNormalAndCoplanarPoint(n, center);
    const denom = fwd.dot(plane.normal);
    if (Math.abs(denom) < 1e-4) return;
    const hit = new THREE.Vector3();
    ray.set(origin, fwd);
    if (!ray.intersectPlane(plane, hit)) return;
    const inv = new THREE.Matrix4().copy(screenMesh.matrixWorld).invert();
    const local = hit.clone().applyMatrix4(inv);
    local.x *= settings.cursorGainX;
    local.y *= settings.cursorGainY;
    const h = getEffectiveScreenScale();
    const w = h * sourceAspect;
    u = local.x / w + 0.5;
    v = 1.0 - (local.y / h + 0.5);
  }

  const geo = await getScreenGeom();
  if (!geo) return;
  const safe = Math.max(0, Math.floor(settings.cursorSafePx));

  let pxRaw = Math.round(u * geo.width) + geo.left;
  let pyRaw = Math.round(v * geo.height) + geo.top;
  pxRaw = Math.min(geo.left + geo.width  - 1 - safe, Math.max(geo.left + safe, pxRaw));
  pyRaw = Math.min(geo.top  + geo.height - 1 - safe, Math.max(geo.top  + safe, pyRaw));

  const t = performance.now();
  const us = uvU.filter(u, t);
  const vs = uvV.filter(v, t);
  let pxSmooth = Math.round(us * geo.width) + geo.left;
  let pySmooth = Math.round(vs * geo.height) + geo.top;
  pxSmooth = Math.min(geo.left + geo.width  - 1 - safe, Math.max(geo.left + safe, pxSmooth));
  pySmooth = Math.min(geo.top  + geo.height - 1 - safe, Math.max(geo.top  + safe, pySmooth));

  const jump = Math.max(1, Math.floor(settings.cursorJumpPx));
  const useRaw = (lastSentPx == null) ||
                 (Math.abs(pxRaw - lastSentPx) > jump) ||
                 (Math.abs(pyRaw - lastSentPy) > jump);

  const sendX = useRaw ? pxRaw : pxSmooth;
  const sendY = useRaw ? pyRaw : pySmooth;

  try {
    const resp = await fetch('/cursor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x: sendX, y: sendY })
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.ok) {
      statusEl.textContent = hadHit ? 'host: cursor ok' : 'host: cursor clamped';
      lastSentPx = sendX;
      lastSentPy = sendY;
    } else {
      statusEl.textContent = 'host: cursor err';
    }
    lastCursorSend = nowMs;
  } catch {
    statusEl.textContent = 'host: cursor net err';
  }
}

/* ---------------- WebRTC: host side ---------------- */
let pc = null;
let orientChannel = null;
let hostCandPollTimer = null;
let hostReconnectTimer = null;
let hostWatchdogTimer = null;
let hostSessionId = 0;
let activeOfferId = null;
const HOST_RECONNECT_DELAY_MS = 1200;
const HOST_CONNECT_TIMEOUT_MS = 14000;
let hostConnectStartedAt = 0;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clearHostPollTimer() {
  if (hostCandPollTimer) {
    clearInterval(hostCandPollTimer);
    hostCandPollTimer = null;
  }
}

function setPhoneLinkActive(active, reason = '') {
  const next = !!active;
  if (phoneLinkActive === next) return;
  phoneLinkActive = next;
  if (!phoneLinkActive) {
    haveOrientation = false;
    statusEl.textContent = reason ? `host: phone disconnected (${reason})` : 'host: phone disconnected';
  } else {
    statusEl.textContent = 'host: phone connected';
  }
}

function startHostWatchdog() {
  if (hostWatchdogTimer) return;
  hostWatchdogTimer = setInterval(() => {
    if (hostReconnectTimer) return;
    if (!pc) {
      scheduleHostReconnect('no_pc', 450);
      return;
    }
    const st = pc.connectionState || 'new';
    if ((st === 'new' || st === 'connecting') && hostConnectStartedAt > 0) {
      if ((performance.now() - hostConnectStartedAt) > HOST_CONNECT_TIMEOUT_MS) {
        scheduleHostReconnect('connect_timeout', 550);
      }
      return;
    }
    if (st === 'failed' || st === 'closed') {
      scheduleHostReconnect(st, 300);
    }
  }, 1400);
}

function closeHostPeer() {
  clearHostPollTimer();
  if (orientChannel) {
    try { orientChannel.close(); } catch {}
    orientChannel = null;
  }
  setPhoneLinkActive(false, 'peer closed');
  if (pc) {
    try { pc.onicecandidate = null; } catch {}
    try { pc.onconnectionstatechange = null; } catch {}
    try { pc.ontrack = null; } catch {}
    try { pc.close(); } catch {}
    pc = null;
  }
}

function scheduleHostReconnect(reason, delayMs = HOST_RECONNECT_DELAY_MS) {
  if (hostReconnectTimer) return;
  console.warn('host reconnect scheduled:', reason);
  statusEl.textContent = `host: reconnecting (${reason})`;
  hostReconnectTimer = setTimeout(() => {
    hostReconnectTimer = null;
    setupWebRTC().catch((err) => {
      console.error('host reconnect failed', err);
      scheduleHostReconnect('retry', 1500);
    });
  }, delayMs);
}

async function sendHostOffer(desc, offerId) {
  const payload = {
    type: desc?.type || 'offer',
    sdp: desc?.sdp || '',
    offerId
  };
  await fetch('/signal/host_offer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

async function fetchViewerAnswer(offerId) {
  try {
    const r = await fetch('/signal/viewer_answer', { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    if (j && j.type === 'answer' && j.sdp) {
      if (!offerId) return j;
      if (!j.offerId || j.offerId === offerId) return j;
    }
    return null;
  } catch {
    return null;
  }
}

async function sendHostCandidate(cand) {
  await fetch('/signal/host_candidates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate: cand })
  });
}

async function pollViewerCandidates() {
  if (!pc) return;
  try {
    const r = await fetch('/signal/viewer_candidates', { cache: 'no-store' });
    if (!r.ok) return;
    const list = await r.json();
    if (!Array.isArray(list)) return;
    for (const cand of list) {
      if (cand) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(cand));
        } catch (e) {
          console.warn('addIceCandidate viewer->host failed', e);
        }
      }
    }
  } catch {
    // ignore
  }
}

async function setupWebRTC() {
  hostSessionId += 1;
  const thisSession = hostSessionId;
  closeHostPeer();
  hostConnectStartedAt = performance.now();
  statusEl.textContent = 'host: creating peerconnection';

  pc = new RTCPeerConnection({ iceServers: [] });

  const stream = canvas.captureStream(HOST_RENDER_FPS);
  const tracks = stream.getVideoTracks();
  if (tracks.length === 0) {
    console.error('No tracks from canvas.captureStream');
  } else {
    pc.addTrack(tracks[0], stream);
  }

  orientChannel = pc.createDataChannel('orient');
  orientChannel.onopen = () => {
    setPhoneLinkActive(true, 'orient open');
    statusEl.textContent = 'host: orient channel open';
  };
  orientChannel.onclose = () => {
    setPhoneLinkActive(false, 'orient closed');
  };
  orientChannel.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'orientation') {
        setPhoneLinkActive(true, 'orientation');
        handleOrientationMessage(msg);
      }
    } catch {
      // ignore
    }
  };

  pc.onicecandidate = (ev) => {
    if (ev.candidate) {
      sendHostCandidate(ev.candidate.toJSON ? ev.candidate.toJSON() : ev.candidate);
    }
  };

  pc.onconnectionstatechange = () => {
    if (!pc || thisSession !== hostSessionId) return;
    const st = pc.connectionState;
    statusEl.textContent = 'host: pc ' + st;
    if (st === 'connected') {
      setPhoneLinkActive(true, 'pc connected');
    }
    if (st === 'failed' || st === 'closed') {
      setPhoneLinkActive(false, st);
      scheduleHostReconnect(st);
      return;
    }
    if (st === 'disconnected') {
      setPhoneLinkActive(false, 'pc disconnected');
      setTimeout(() => {
        if (!pc || thisSession !== hostSessionId) return;
        if (pc.connectionState === 'disconnected') {
          scheduleHostReconnect('disconnected');
        }
      }, 1400);
    }
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  activeOfferId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  await sendHostOffer(offer, activeOfferId);
  statusEl.textContent = 'host: offer sent, waiting for answer';

  let answer = null;
  let lastOfferPostAt = performance.now();
  while (!answer && thisSession === hostSessionId && pc) {
    answer = await fetchViewerAnswer(activeOfferId);
    if (!answer) {
      if ((performance.now() - lastOfferPostAt) > 3000 && pc.localDescription) {
        await sendHostOffer(pc.localDescription.toJSON ? pc.localDescription.toJSON() : pc.localDescription, activeOfferId);
        lastOfferPostAt = performance.now();
      }
      await sleep(SIGNAL_POLL_INTERVAL_MS);
    }
  }
  if (!pc || thisSession !== hostSessionId || !answer) return;
  await pc.setRemoteDescription(answer);
  statusEl.textContent = 'host: answer set';

  clearHostPollTimer();
  hostCandPollTimer = setInterval(() => {
    if (!pc || thisSession !== hostSessionId) return;
    pollViewerCandidates();
  }, SIGNAL_POLL_INTERVAL_MS);
}

/* ---------------- Main loop ---------------- */
function animate(now = 0) {
  requestAnimationFrame(animate);

  if (haveOrientation) {
    const q = targetQ.clone();
    if (haveCalib) q.premultiply(calibInv);
    head.quaternion.slerp(q, 0.18);
  }

  if (settings.converge) {
    const t = screenMesh.position;
    camera.lookAt(t);
  }

  const minFrameInterval = 1000 / HOST_RENDER_FPS;
  if (now - (animate._lastRender || 0) >= minFrameInterval) {
    updateScreenTexture(now);
    renderer.setSize(HOST_RENDER_WIDTH, HOST_RENDER_HEIGHT, false);
    renderer.render(scene, camera);
    animate._lastRender = now;
  }

  maybeSendCursor(performance.now());
}

function init() {
  applyTextureSizeForAspect(sourceAspect || (1280 / 800), true);
  applyScreenTransform();
  pullSettings();
  pullGestureStatus();
  startHostWatchdog();
  window.addEventListener('online', () => scheduleHostReconnect('network_online', 350));
  setupWebRTC().catch(err => {
    console.error('WebRTC host init failed', err);
    statusEl.textContent = 'host: webrtc error';
    scheduleHostReconnect('init_error', 1500);
  });
  animate();
}

window.addEventListener('beforeunload', () => {
  closeHostPeer();
});

init();
