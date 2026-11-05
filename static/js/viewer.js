/* ---------------- DOM refs ---------------- */
const remoteVideo = document.getElementById('remoteVideo');

const eyeCanvasL = document.getElementById('eyeCanvasL');
const eyeCanvasR = document.getElementById('eyeCanvasR');
const eyeCtxL = eyeCanvasL.getContext('2d');
const eyeCtxR = eyeCanvasR.getContext('2d');

const camVideoL = document.getElementById('camOverlayL');
const camVideoR = document.getElementById('camOverlayR');
const mpOverlayL = document.getElementById('mpOverlayL');
const mpOverlayR = document.getElementById('mpOverlayR');
const mpCtxL = mpOverlayL ? mpOverlayL.getContext('2d') : null;
const mpCtxR = mpOverlayR ? mpOverlayR.getContext('2d') : null;

const hud      = document.getElementById('hud');
const gear     = document.getElementById('gear');
const statusEl = document.getElementById('status');

const enableMotionBtn = document.getElementById('enableMotion');
const recenterBtn     = document.getElementById('recenter');
const fsBtn           = document.getElementById('fs');
const hideBtn         = document.getElementById('hideHud');

const sizeEl     = document.getElementById('size');
const sizeVal    = document.getElementById('sizeVal');
const distEl     = document.getElementById('dist');
const distVal    = document.getElementById('distVal');
const curveRadiusEl  = document.getElementById('curveRadius');
const curveRadiusVal = document.getElementById('curveRadiusVal');
const eyePxEl    = document.getElementById('eyePx');
const eyePxVal   = document.getElementById('eyePxVal');
const convergeEl = document.getElementById('converge');

const enableCamBtn   = document.getElementById('enableCam');
const camLensSel     = document.getElementById('camLens');
const camOpacityEl   = document.getElementById('camOpacity');
const camOpacityVal  = document.getElementById('camOpacityVal');
const camEnabledEl   = document.getElementById('camEnabled');
const camBlendSel    = document.getElementById('camBlend');

const cursorEnabledEl = document.getElementById('cursorEnabled');
const gestureEnabledEl = document.getElementById('gestureEnabled');
const filterModeSel   = document.getElementById('filterMode');
const gestureInactiveMsEl = document.getElementById('gestureInactiveMs');
const gestureInactiveMsVal = document.getElementById('gestureInactiveMsVal');
const gestureDoubleMsEl = document.getElementById('gestureDoubleMs');
const gestureDoubleMsVal = document.getElementById('gestureDoubleMsVal');

const dotSizeEl        = document.getElementById('dotSize');
const dotSizeVal       = document.getElementById('dotSizeVal');
const screenOpacityEl  = document.getElementById('screenOpacity');
const screenOpacityVal = document.getElementById('screenOpacityVal');
const mpOverlayEnabledEl = document.getElementById('mpOverlayEnabled');

const retDotL = document.querySelector('#reticleL .retDot');
const retDotR = document.querySelector('#reticleR .retDot');

/* ========= Manual tweak for outside camera stereo offset =========
   If you still see double ONLY in the outside view (not 3D screen),
   you can tweak this value by a few pixels. Positive shifts the
   left/right views outward, negative pulls them inward.

   Recommended range: between -40 and +40.
   Default 0 keeps behavior identical to previous version. */
const CAM_OFFSET_TWEAK_PX = 0;

/* ---------------- Settings mirror (server-synced) ---------------- */
const settings = {
  screenScale: 2.60,
  screenDist:  1.50,
  screenCurveRadius: 6.0,
  eyePx:       16.0,
  converge:    false,
  camEnabled:  false,
  camOpacity:  70.0,
  camLens:     'normal',
  camFeedProfile: 'low',
  camBlend:    'screen',
  cursorEnabled: false,
  cursorSafePx: 1.0,
  cursorHz:   60,
  cursorGainX: 1.0,
  cursorGainY: 1.0,
  cursorSmoothing: 0.25,
  cursorJumpPx: 24.0,
  recenterNonce: 0,
  hostRenderWidth:  5600,
  hostRenderHeight: 3150,
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
  filterMode: 'simple',
  version: 0,
  origin: 'server'
};
let lastPostVersion = 0;

/* ---------------- Camera overlay on phone ---------------- */
let camStream = null;

/* Stereo for 3D world + dot */
let currentStereoShiftPx = 0;

/* Ultra-wide selection state (from your prototype) */
let useUltra = false;
let devicesCache = [];
let camPermissionUnlocked = false;
let mpOverlayEnabled = true;
let lastCamConstraintSig = '';

const MP_HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];
let lastKeypointPacket = null;
let lastKeypointSeq = 0;
let keypointPollBusy = false;
let keypointLastPollTs = 0;
const KEYPOINT_POLL_INTERVAL_MS = 55;
let heartbeatBusy = false;
let heartbeatLastTs = 0;
const HEARTBEAT_INTERVAL_MS = 900;

/* ---------------- Camera overlay style ---------------- */
function applyCamStyle() {
  const o = settings.camEnabled ? Math.max(0, Math.min(100, settings.camOpacity)) / 100 : 0;
  camVideoL.style.opacity = String(o);
  camVideoR.style.opacity = String(o);
  const mode = settings.camBlend === 'normal' ? 'normal' : 'screen';
  camVideoL.style.mixBlendMode = mode;
  camVideoR.style.mixBlendMode = mode;
  applyMediapipeOverlayStyle();
}

function applyMediapipeOverlayStyle() {
  const show = mpOverlayEnabled && settings.camEnabled;
  const op = show ? 1 : 0;
  if (mpOverlayL) mpOverlayL.style.opacity = String(op);
  if (mpOverlayR) mpOverlayR.style.opacity = String(op);
}

/**
 * Map settings.camLens to useUltra (real hardware wide camera).
 * No digital scaling here; real lens does the FOV.
 */
function applyCamLensStyle() {
  useUltra = (settings.camLens === 'wide');
  updateReticleAndCamTransforms();
}

/**
 * Compute camera stereo offset in pixels, reusing your old prototype mapping:
 * - At eyePx = 16, base offset = -60 (your preferred non-double setting).
 * - At eyePx = 0, offset = 0.
 * Then we add CAM_OFFSET_TWEAK_PX for manual fine tuning.
 */
function computeCamOffsetPx() {
  const BASE_EYE    = 16.0;     // your current preferred eyePx
  const BASE_OFFSET = -60.0;    // your old preferred camera offset
  const eye = settings.eyePx || 0;
  if (BASE_EYE === 0) return CAM_OFFSET_TWEAK_PX;
  const base = (eye / BASE_EYE) * BASE_OFFSET;
  return base + CAM_OFFSET_TWEAK_PX;
}

/**
 * Update transforms:
 * - Red dots: based on currentStereoShiftPx (anchored to 3D world & gaze cursor).
 * - Outside camera overlays: based on camOffsetPx (old prototype logic).
 *   IMPORTANT: Each overlay video is clipped to its half of the screen
 *   by the camContainer* divs in HTML, so they never overlap in the center.
 */
function updateReticleAndCamTransforms() {
  const sWorld = currentStereoShiftPx || 0;

  // Red dots stay tied to the 3D world stereo
  if (retDotL) retDotL.style.transform = `translateX(${ sWorld}px)`;
  if (retDotR) retDotR.style.transform = `translateX(${-sWorld}px)`;

  // Outside camera overlay uses your old offset logic + tweak
  const camOffsetPx = computeCamOffsetPx();
  const leftShift  = -camOffsetPx / 2;
  const rightShift =  camOffsetPx / 2;

  camVideoL.style.transformOrigin = '50% 50%';
  camVideoR.style.transformOrigin = '50% 50%';
  if (mpOverlayL) mpOverlayL.style.transformOrigin = '50% 50%';
  if (mpOverlayR) mpOverlayR.style.transformOrigin = '50% 50%';

  // Each video is inside a 50vw container with overflow:hidden,
  // so even if these shifts cross the center, the other half is clipped.
  camVideoL.style.transform = `translateX(${leftShift}px)`;
  camVideoR.style.transform = `translateX(${rightShift}px)`;
  if (mpOverlayL) mpOverlayL.style.transform = `translateX(${leftShift}px)`;
  if (mpOverlayR) mpOverlayR.style.transform = `translateX(${rightShift}px)`;
}

/* ---------------- Camera device helpers (from your prototype) ---------------- */
async function refreshDevices() {
  try { devicesCache = (await navigator.mediaDevices.enumerateDevices()) || []; }
  catch (e) { devicesCache = []; }
}

function findUltraWideDeviceId() {
  const vids = devicesCache.filter(d => d.kind === 'videoinput');
  const ultra = vids.find(d => /back/i.test(d.label) && /ultra/i.test(d.label));
  if (ultra) return ultra.deviceId;
  const half = vids.find(d => /0\.5/.test(d.label));
  return (half && half.deviceId) || null;
}

async function unlockCameraLabelsIfNeeded() {
  if (camPermissionUnlocked) return;
  try {
    const tmp = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    tmp.getTracks().forEach(t => t.stop());
    camPermissionUnlocked = true;
    await refreshDevices();
  } catch (e) {
    console.warn('Failed to unlock camera labels', e);
  }
}

async function stopCamera() {
  if (!camStream) return;
  camStream.getTracks().forEach(t => t.stop());
  camStream = null;
  lastCamConstraintSig = '';
  camVideoL.srcObject = null;
  camVideoR.srcObject = null;
  clearMediapipeOverlay();
}

/**
 * Start camera using:
 * - settings.camMaxWidth / camMaxHeight / camMaxFps (from server).
 * - useUltra (mapped from settings.camLens).
 * Logic mirrors your prototype's startCamera().
 */
async function startCamera() {
  await stopCamera();

  const w = settings.camMaxWidth  || 480;
  const h = settings.camMaxHeight || 270;
  const f = settings.camMaxFps    || 24;

  let deviceId = null;
  if (useUltra) deviceId = findUltraWideDeviceId();

  const base = {
    width:     { ideal: w },
    height:    { ideal: h },
    frameRate: { ideal: f, max: f }
  };

  const constraints = {
    video: deviceId
      ? { deviceId: { exact: deviceId }, ...base }
      : { facingMode: { ideal: 'environment' }, ...base },
    audio: false
  };

  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  camStream = stream;
  lastCamConstraintSig = `${useUltra ? 'wide' : 'normal'}|${Math.round(w)}x${Math.round(h)}@${Math.round(f)}`;
  camVideoL.srcObject = stream;
  camVideoR.srcObject = stream;
  await Promise.all([
    camVideoL.play().catch(() => {}),
    camVideoR.play().catch(() => {})
  ]);

  applyCamStyle();
  updateReticleAndCamTransforms();

  if (useUltra) {
    try {
      const [track] = stream.getVideoTracks();
      const caps = track.getCapabilities && track.getCapabilities();
      if (caps && 'zoom' in caps && caps.zoom.min <= 0.5 && caps.zoom.max >= 0.5) {
        await track.applyConstraints({ advanced: [{ zoom: 0.5 }] });
      }
    } catch (e) {
      console.warn('Ultra-wide zoom constraints failed, continuing with base stream', e);
    }
  }
}

function cameraShouldRun() {
  return !!(settings.camEnabled || settings.gestureEnabled);
}

function cameraConstraintSig() {
  return `${settings.camLens}|${Math.round(settings.camMaxWidth || 0)}x${Math.round(settings.camMaxHeight || 0)}@${Math.round(settings.camMaxFps || 0)}`;
}

async function syncCameraForCurrentNeeds(forceRestart = false) {
  const need = cameraShouldRun();
  if (need && !camStream) {
    try {
      await unlockCameraLabelsIfNeeded();
      await startCamera();
    } catch (e) {
      console.warn('camera sync start failed', e);
    }
    return;
  }
  if (!need && camStream) {
    await stopCamera();
    return;
  }
  if (need && camStream) {
    const sig = cameraConstraintSig();
    if (forceRestart || !lastCamConstraintSig || sig !== lastCamConstraintSig) {
      try {
        await unlockCameraLabelsIfNeeded();
        await startCamera();
      } catch (e) {
        console.warn('camera constraint restart failed', e);
      }
    }
  }
}

/* ---------------- Phone camera uplink for server-side gesture detection ---------------- */
const gestureCanvas = document.createElement('canvas');
const gestureCtx = gestureCanvas.getContext('2d', { alpha: false });
let gestureLoopStarted = false;
let gestureUploadBusy = false;
let gestureLastUploadTs = 0;

async function uploadGestureFrame(blob) {
  try {
    await fetch('/phone_cam_frame', {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg' },
      body: blob
    });
  } catch {
    // ignore transient upload errors
  }
}

function computeGestureUploadSize() {
  const maxW = Math.max(224, Math.round(settings.gestureFrameWidth || 424));
  const maxH = Math.max(160, Math.round(settings.gestureFrameHeight || 240));
  const srcW = Math.max(1, camVideoL.videoWidth || maxW);
  const srcH = Math.max(1, camVideoL.videoHeight || maxH);
  const scale = Math.min(1, maxW / srcW, maxH / srcH);
  const targetW = Math.max(160, Math.round(srcW * scale));
  const targetH = Math.max(120, Math.round(srcH * scale));
  return [targetW, targetH];
}

async function maybeUploadGestureFrame(nowMs) {
  if (!settings.gestureEnabled) return;
  if (!camStream || !gestureCtx) return;
  if (!camVideoL || camVideoL.readyState < 2) return;
  if (gestureUploadBusy) return;

  const fps = Math.max(2, Math.min(30, Math.round(settings.gestureFrameFps || 12)));
  const minInterval = 1000 / fps;
  if (nowMs - gestureLastUploadTs < minInterval) return;

  const [targetW, targetH] = computeGestureUploadSize();
  if (gestureCanvas.width !== targetW || gestureCanvas.height !== targetH) {
    gestureCanvas.width = targetW;
    gestureCanvas.height = targetH;
  }

  gestureCtx.save();
  gestureCtx.setTransform(1, 0, 0, 1, 0, 0);
  gestureCtx.clearRect(0, 0, targetW, targetH);
  gestureCtx.drawImage(camVideoL, 0, 0, targetW, targetH);
  gestureCtx.restore();

  gestureUploadBusy = true;
  gestureCanvas.toBlob(async (blob) => {
    try {
      if (blob) {
        await uploadGestureFrame(blob);
      }
    } finally {
      gestureUploadBusy = false;
    }
  }, 'image/jpeg', 0.68);

  gestureLastUploadTs = nowMs;
}

async function maybeSendPhoneHeartbeat(nowMs) {
  if (heartbeatBusy) return;
  if ((nowMs - heartbeatLastTs) < HEARTBEAT_INTERVAL_MS) return;
  heartbeatBusy = true;
  try {
    await fetch('/phone_heartbeat', { method: 'POST', cache: 'no-store' });
  } catch {
    // ignore transient network errors
  } finally {
    heartbeatBusy = false;
    heartbeatLastTs = nowMs;
  }
}

function startGestureUploadLoop() {
  if (gestureLoopStarted) return;
  gestureLoopStarted = true;
  const loop = (now) => {
    maybeSendPhoneHeartbeat(now);
    maybeUploadGestureFrame(now);
    maybePollGestureKeypoints(now);
    drawMediapipeOverlay(now);
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

function clamp01(v) {
  return Math.max(0, Math.min(1, Number(v) || 0));
}

function clearMediapipeOverlay() {
  if (mpCtxL && mpOverlayL) {
    mpCtxL.clearRect(0, 0, mpOverlayL.width, mpOverlayL.height);
  }
  if (mpCtxR && mpOverlayR) {
    mpCtxR.clearRect(0, 0, mpOverlayR.width, mpOverlayR.height);
  }
}

function ensureOverlayCanvasSize(canvas, ctx) {
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  const cssW = Math.max(1, canvas.clientWidth || 1);
  const cssH = Math.max(1, canvas.clientHeight || 1);
  const w = Math.max(1, Math.round(cssW * dpr));
  const h = Math.max(1, Math.round(cssH * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  return { cssW, cssH, dpr };
}

function mapNormToCover(nx, ny, srcW, srcH, dstW, dstH) {
  const x = clamp01(nx);
  const y = clamp01(ny);
  const scale = Math.max(dstW / Math.max(1, srcW), dstH / Math.max(1, srcH));
  const drawW = srcW * scale;
  const drawH = srcH * scale;
  const offX = (dstW - drawW) * 0.5;
  const offY = (dstH - drawH) * 0.5;
  return [offX + x * drawW, offY + y * drawH];
}

function handColor(handedness) {
  const h = String(handedness || '').toLowerCase();
  if (h === 'left') return '#22d3ee';
  if (h === 'right') return '#f97316';
  return '#a3e635';
}

async function maybePollGestureKeypoints(nowMs) {
  if (!settings.gestureEnabled || !settings.gestureKeypointStreamEnabled) return;
  if (keypointPollBusy) return;
  if ((nowMs - keypointLastPollTs) < KEYPOINT_POLL_INTERVAL_MS) return;

  keypointPollBusy = true;
  keypointLastPollTs = nowMs;
  try {
    const r = await fetch(`/gesture_keypoints?since=${lastKeypointSeq}`, { cache: 'no-store' });
    if (!r.ok) return;
    const p = await r.json();
    if (!p || p.stale) return;
    const seq = Number(p.seq || 0);
    if (!Number.isFinite(seq) || seq <= lastKeypointSeq) return;
    lastKeypointSeq = seq;
    lastKeypointPacket = p;
  } catch {
    // ignore transient network errors
  } finally {
    keypointPollBusy = false;
  }
}

function drawMediapipeOverlay(nowMs) {
  if (!mpCtxL || !mpCtxR || !mpOverlayL || !mpOverlayR) return;

  const leftGeom = ensureOverlayCanvasSize(mpOverlayL, mpCtxL);
  const rightGeom = ensureOverlayCanvasSize(mpOverlayR, mpCtxR);

  if (!mpOverlayEnabled || !settings.camEnabled) return;
  const packet = lastKeypointPacket;
  if (!packet || !Array.isArray(packet.hands)) return;
  const ageMs = Date.now() - (Number(packet.ts || 0) * 1000);
  if (!Number.isFinite(ageMs) || ageMs > 1400) return;
  if (!packet.hands.length) return;

  const srcW = Math.max(1, Number(packet.frameWidth || camVideoL.videoWidth || 1));
  const srcH = Math.max(1, Number(packet.frameHeight || camVideoL.videoHeight || 1));

  const drawOn = (ctx, geom) => {
    for (const hand of packet.hands) {
      const pts = Array.isArray(hand.landmarks) ? hand.landmarks : [];
      if (pts.length < 21) continue;

      const color = handColor(hand.handedness);
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 2;

      for (const [a, b] of MP_HAND_CONNECTIONS) {
        const pa = pts[a];
        const pb = pts[b];
        if (!pa || !pb) continue;
        const [x1, y1] = mapNormToCover(pa[0], pa[1], srcW, srcH, geom.cssW, geom.cssH);
        const [x2, y2] = mapNormToCover(pb[0], pb[1], srcW, srcH, geom.cssW, geom.cssH);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      for (const p of pts) {
        const [x, y] = mapNormToCover(p[0], p[1], srcW, srcH, geom.cssW, geom.cssH);
        ctx.beginPath();
        ctx.arc(x, y, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    if (packet.trackingEnabled) {
      const tx = clamp01(packet.trackingCenterNormX);
      const ty = clamp01(packet.trackingCenterNormY);
      const [cx, cy] = mapNormToCover(tx, ty, srcW, srcH, geom.cssW, geom.cssH);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - 8, cy);
      ctx.lineTo(cx + 8, cy);
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx, cy + 8);
      ctx.stroke();
    }
  };

  drawOn(mpCtxL, leftGeom);
  drawOn(mpCtxR, rightGeom);
}

/* ---------------- Viewer-local visual settings ---------------- */
function applyDotSize() {
  if (!dotSizeEl || !dotSizeVal) return;
  const px = parseInt(dotSizeEl.value, 10) || 8;
  dotSizeVal.textContent = `${px} px`;
  if (retDotL) {
    retDotL.style.width = px + 'px';
    retDotL.style.height = px + 'px';
  }
  if (retDotR) {
    retDotR.style.width = px + 'px';
    retDotR.style.height = px + 'px';
  }
}

function applyScreenOpacity() {
  if (!screenOpacityEl || !screenOpacityVal) return;
  const val = parseInt(screenOpacityEl.value, 10) || 100;
  const op = Math.max(0, Math.min(100, val)) / 100;
  screenOpacityVal.textContent = `${val}%`;
  eyeCanvasL.style.opacity = op;
  eyeCanvasR.style.opacity = op;
}

function applyCurveRadiusValue() {
  if (!curveRadiusEl || !curveRadiusVal) return;
  const val = parseFloat(curveRadiusEl.value) || 6.0;
  curveRadiusVal.textContent = `${val.toFixed(2)} m`;
}

function applyGestureTimingLabels() {
  if (gestureInactiveMsEl && gestureInactiveMsVal) {
    const ms = parseInt(gestureInactiveMsEl.value, 10) || 700;
    gestureInactiveMsVal.textContent = `${ms} ms`;
  }
  if (gestureDoubleMsEl && gestureDoubleMsVal) {
    const ms = parseInt(gestureDoubleMsEl.value, 10) || 1750;
    gestureDoubleMsVal.textContent = `${ms} ms`;
  }
}

/* ---------------- Settings sync with server ---------------- */
let postBusy = false;
async function postSettings() {
  if (postBusy) return;
  try {
    postBusy = true;
    const payload = { ...settings, origin: 'phone' };
    const r = await fetch('/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const s = await r.json().catch(() => null);
    if (s && typeof s.version === 'number') lastPostVersion = s.version;
  } catch {
    // ignore
  } finally {
    postBusy = false;
  }
}

let pullingSettings = false;
async function pullSettings() {
  if (pullingSettings) return;
  pullingSettings = true;
  try {
    const r = await fetch('/settings', { cache: 'no-store' });
    if (!r.ok) return;
    const s = await r.json();
    if (typeof s.version === 'number' && s.version <= lastPostVersion && s.origin === 'phone') return;
    const prevCamSig = cameraConstraintSig();
    let changed = false;
    for (const k of Object.keys(settings)) {
      if (s[k] !== undefined && settings[k] !== s[k]) {
        settings[k] = s[k];
        changed = true;
      }
    }
    if (changed) {
      sizeEl.value   = String(settings.screenScale.toFixed(2));
      sizeVal.textContent = `${(+settings.screenScale).toFixed(2)}×`;
      distEl.value   = String(settings.screenDist.toFixed(2));
      distVal.textContent = `${(+settings.screenDist).toFixed(2)} m`;
      curveRadiusEl.value = String(settings.screenCurveRadius.toFixed(2));
      applyCurveRadiusValue();
      eyePxEl.value  = String(Math.round(settings.eyePx));
      eyePxVal.textContent = `${Math.round(settings.eyePx)} px`;
      convergeEl.checked   = !!settings.converge;

      camOpacityEl.value   = String(settings.camOpacity);
      camOpacityVal.textContent = `${settings.camOpacity}%`;
      camEnabledEl.checked = !!settings.camEnabled;
      camBlendSel.value    = settings.camBlend;
      camLensSel.value     = settings.camLens;

      cursorEnabledEl.checked = !!settings.cursorEnabled;
      gestureEnabledEl.checked = !!settings.gestureEnabled;
      gestureInactiveMsEl.value = String(Math.round(settings.gestureInactiveMs || 700));
      gestureDoubleMsEl.value = String(Math.round(settings.gestureDoublePinchMs || 1750));
      applyGestureTimingLabels();
      filterModeSel.value  = settings.filterMode === 'simple' ? 'simple' : 'one_euro';

      applyCamStyle();
      applyCamLensStyle(); // sets useUltra and updates overlay transforms

      await syncCameraForCurrentNeeds(prevCamSig !== cameraConstraintSig());
      statusEl.textContent = settings.cursorEnabled ? 'connected, cursor on' : 'connected, cursor off';
    }
  } catch {
    // ignore
  } finally {
    pullingSettings = false;
  }
}
setInterval(pullSettings, 1500);

/* ---------------- HUD handlers ---------------- */
sizeEl.addEventListener('input', async () => {
  settings.screenScale = parseFloat(sizeEl.value);
  sizeVal.textContent = `${(+settings.screenScale).toFixed(2)}×`;
  await postSettings();
});
distEl.addEventListener('input', async () => {
  settings.screenDist = parseFloat(distEl.value);
  distVal.textContent = `${(+settings.screenDist).toFixed(2)} m`;
  await postSettings();
});
curveRadiusEl.addEventListener('input', async () => {
  settings.screenCurveRadius = parseFloat(curveRadiusEl.value);
  applyCurveRadiusValue();
  await postSettings();
});
eyePxEl.addEventListener('input', async () => {
  settings.eyePx = parseFloat(eyePxEl.value);
  eyePxVal.textContent = `${Math.round(settings.eyePx)} px`;
  updateReticleAndCamTransforms();
  await postSettings();
});
convergeEl.addEventListener('change', async () => {
  settings.converge = !!convergeEl.checked;
  await postSettings();
});

enableCamBtn.addEventListener('click', async () => {
  try {
    settings.camEnabled = true;
    camEnabledEl.checked = true;
    await syncCameraForCurrentNeeds();
    await postSettings();
  } catch (e) {
    console.warn('camera start failed', e);
  }
});
camEnabledEl.addEventListener('change', async () => {
  settings.camEnabled = !!camEnabledEl.checked;
  await syncCameraForCurrentNeeds();
  await postSettings();
});
camOpacityEl.addEventListener('input', async () => {
  settings.camOpacity = parseInt(camOpacityEl.value, 10) || 0;
  camOpacityVal.textContent = `${settings.camOpacity}%`;
  applyCamStyle();
  await postSettings();
});
camBlendSel.addEventListener('change', async () => {
  settings.camBlend = camBlendSel.value;
  applyCamStyle();
  await postSettings();
});
camLensSel.addEventListener('change', async () => {
  settings.camLens = camLensSel.value;
  applyCamLensStyle(); // sets useUltra
  if (cameraShouldRun()) {
    try {
      await unlockCameraLabelsIfNeeded();
      await startCamera();
    } catch {}
  }
  await postSettings();
});

cursorEnabledEl.addEventListener('change', async () => {
  settings.cursorEnabled = !!cursorEnabledEl.checked;
  statusEl.textContent = settings.cursorEnabled ? 'connected, cursor on' : 'connected, cursor off';
  await postSettings();
});
gestureEnabledEl.addEventListener('change', async () => {
  settings.gestureEnabled = !!gestureEnabledEl.checked;
  await syncCameraForCurrentNeeds();
  await postSettings();
});
gestureInactiveMsEl.addEventListener('input', async () => {
  settings.gestureInactiveMs = parseInt(gestureInactiveMsEl.value, 10) || 700;
  applyGestureTimingLabels();
  await postSettings();
});
gestureDoubleMsEl.addEventListener('input', async () => {
  settings.gestureDoublePinchMs = parseInt(gestureDoubleMsEl.value, 10) || 1750;
  applyGestureTimingLabels();
  await postSettings();
});
filterModeSel.addEventListener('change', async () => {
  const val = filterModeSel.value === 'simple' ? 'simple' : 'one_euro';
  settings.filterMode = val;
  await postSettings();
});

dotSizeEl.addEventListener('input', () => {
  applyDotSize();
});
screenOpacityEl.addEventListener('input', () => {
  applyScreenOpacity();
});
if (mpOverlayEnabledEl) {
  mpOverlayEnabledEl.addEventListener('change', () => {
    mpOverlayEnabled = !!mpOverlayEnabledEl.checked;
    applyMediapipeOverlayStyle();
    if (!mpOverlayEnabled) {
      clearMediapipeOverlay();
    }
  });
}

hideBtn.addEventListener('click', () => {
  hud.style.display = 'none';
  gear.style.display = 'flex';
});
gear.addEventListener('click', () => {
  hud.style.display = 'flex';
  gear.style.display = 'none';
});

fsBtn.addEventListener('click', async () => {
  const el = document.documentElement;
  try {
    (el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen).call(el);
  } catch {}
});

recenterBtn.addEventListener('click', async () => {
  try {
    await fetch('/recenter', { method: 'POST' });
  } catch {}
});

/* ---------------- Motion sensors & orientation sending ---------------- */
let orientChannel = null;

function screenOrientationDeg() {
  const ang =
    (screen.orientation && typeof screen.orientation.angle === 'number')
      ? screen.orientation.angle
      : (window.orientation || 0);
  return ang || 0;
}

async function enableMotion() {
  try {
    const needDM = typeof DeviceMotionEvent !== 'undefined' &&
      typeof DeviceMotionEvent.requestPermission === 'function';
    const needDO = typeof DeviceOrientationEvent !== 'undefined' &&
      typeof DeviceOrientationEvent.requestPermission === 'function';
    if (needDM) {
      try { await DeviceMotionEvent.requestPermission(); } catch {}
    }
    if (needDO) {
      try { await DeviceOrientationEvent.requestPermission(); } catch {}
    }
  } finally {
    window.addEventListener('deviceorientation', onDeviceOrientation, { passive: true });
    statusEl.textContent = 'motion on (waiting for WebRTC)';
  }
}
enableMotionBtn.addEventListener('click', enableMotion);

function onDeviceOrientation(evt) {
  if (!orientChannel || orientChannel.readyState !== 'open') return;
  if (evt.alpha == null) return;
  const msg = {
    type: 'orientation',
    alphaDeg: evt.alpha || 0,
    betaDeg:  evt.beta  || 0,
    gammaDeg: evt.gamma || 0,
    orientDeg: screenOrientationDeg(),
    t: performance.now()
  };
  try {
    orientChannel.send(JSON.stringify(msg));
  } catch {
    // ignore
  }
}

/* ---------------- WebRTC: viewer side ---------------- */
let pc = null;
let viewerCandPollTimer = null;
let viewerReconnectTimer = null;
let viewerWatchdogTimer = null;
let viewerSessionId = 0;
let activeOfferId = null;
const VIEWER_RECONNECT_DELAY_MS = 1200;
const VIEWER_CONNECT_TIMEOUT_MS = 14000;
const VIEWER_VIDEO_STALL_MS = 4500;
let viewerConnectStartedAt = 0;
let lastRemoteVideoTime = 0;
let lastRemoteVideoProgressAt = 0;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clearViewerPollTimer() {
  if (viewerCandPollTimer) {
    clearInterval(viewerCandPollTimer);
    viewerCandPollTimer = null;
  }
}

function startViewerWatchdog() {
  if (viewerWatchdogTimer) return;
  viewerWatchdogTimer = setInterval(() => {
    if (viewerReconnectTimer) return;
    if (!pc) {
      scheduleViewerReconnect('no_pc', 400);
      return;
    }
    const st = pc.connectionState || 'new';
    if ((st === 'new' || st === 'connecting') && viewerConnectStartedAt > 0) {
      if ((performance.now() - viewerConnectStartedAt) > VIEWER_CONNECT_TIMEOUT_MS) {
        scheduleViewerReconnect('connect_timeout', 500);
      }
      return;
    }
    if (st === 'connected') {
      const ct = Number(remoteVideo.currentTime || 0);
      const now = Date.now();
      if (ct > (lastRemoteVideoTime + 0.002)) {
        lastRemoteVideoTime = ct;
        lastRemoteVideoProgressAt = now;
      }
      if (lastRemoteVideoProgressAt > 0 && (now - lastRemoteVideoProgressAt) > VIEWER_VIDEO_STALL_MS) {
        scheduleViewerReconnect('video_stall', 500);
      }
    }
  }, 1300);
}

function closeViewerPeer() {
  clearViewerPollTimer();
  if (orientChannel) {
    try { orientChannel.close(); } catch {}
    orientChannel = null;
  }
  if (pc) {
    try { pc.ontrack = null; } catch {}
    try { pc.ondatachannel = null; } catch {}
    try { pc.onicecandidate = null; } catch {}
    try { pc.onconnectionstatechange = null; } catch {}
    try { pc.close(); } catch {}
    pc = null;
  }
}

function scheduleViewerReconnect(reason, delayMs = VIEWER_RECONNECT_DELAY_MS) {
  if (viewerReconnectTimer) return;
  console.warn('viewer reconnect scheduled:', reason);
  statusEl.textContent = `reconnecting (${reason})`;
  viewerReconnectTimer = setTimeout(() => {
    viewerReconnectTimer = null;
    setupWebRTC().catch((err) => {
      console.error('viewer reconnect failed', err);
      scheduleViewerReconnect('retry', 1500);
    });
  }, delayMs);
}

async function fetchHostOffer() {
  try {
    const r = await fetch('/signal/host_offer', { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    if (j && j.type === 'offer' && j.sdp) return j;
    return null;
  } catch {
    return null;
  }
}

async function sendViewerAnswer(desc, offerId = null) {
  const payload = {
    type: desc?.type || 'answer',
    sdp: desc?.sdp || ''
  };
  if (offerId) payload.offerId = offerId;
  await fetch('/signal/viewer_answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

async function sendViewerCandidate(cand) {
  await fetch('/signal/viewer_candidates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate: cand })
  });
}

async function pollHostCandidates() {
  if (!pc) return;
  try {
    const r = await fetch('/signal/host_candidates', { cache: 'no-store' });
    if (!r.ok) return;
    const list = await r.json();
    if (!Array.isArray(list)) return;
    for (const cand of list) {
      if (cand) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(cand));
        } catch (e) {
          console.warn('addIceCandidate host->viewer failed', e);
        }
      }
    }
  } catch {
    // ignore
  }
}

/* ---------------- Eye rendering from remoteVideo ---------------- */
let eyeLoopRunning = false;

function resizeEyeCanvases() {
  const vw = remoteVideo.videoWidth || 0;
  const vh = remoteVideo.videoHeight || 0;
  if (!vw || !vh) return;
  const eyeWidth = Math.floor(vw / 2);
  eyeCanvasL.width = eyeWidth;
  eyeCanvasL.height = vh;
  eyeCanvasR.width = eyeWidth;
  eyeCanvasR.height = vh;
}

function drawEyes() {
  const vw = remoteVideo.videoWidth || 0;
  const vh = remoteVideo.videoHeight || 0;
  if (!vw || !vh) return;
  const ct = Number(remoteVideo.currentTime || 0);
  if (ct > (lastRemoteVideoTime + 0.002)) {
    lastRemoteVideoTime = ct;
    lastRemoteVideoProgressAt = Date.now();
  }

  const eyeWidth = Math.floor(vw / 2);

  const cxBase = vw / 2;
  const maxEyePx = 60;
  const frac = (settings.eyePx || 0) / (2 * maxEyePx);
  const shift = frac * eyeWidth; // in video pixels

  const cxL = cxBase - shift;
  const cxR = cxBase + shift;

  const sxL = Math.round(cxL - eyeWidth / 2);
  const sxR = Math.round(cxR - eyeWidth / 2);

  const clamp = (x, min, max) => Math.max(min, Math.min(max, x));
  const sxLclamp = clamp(sxL, 0, vw - eyeWidth);
  const sxRclamp = clamp(sxR, 0, vw - eyeWidth);

  eyeCtxL.drawImage(remoteVideo, sxLclamp, 0, eyeWidth, vh,
                    0, 0, eyeCanvasL.width, eyeCanvasL.height);
  eyeCtxR.drawImage(remoteVideo, sxRclamp, 0, eyeWidth, vh,
                    0, 0, eyeCanvasR.width, eyeCanvasR.height);

  // Compute world stereo shift in screen pixels for red dot
  const halfScreenW = window.innerWidth / 2;
  if (eyeWidth > 0 && halfScreenW > 0) {
    const norm = shift / eyeWidth; // ~[-0.5, +0.5]
    currentStereoShiftPx = norm * halfScreenW;
  } else {
    currentStereoShiftPx = 0;
  }

  // Update red dots + outside camera overlay stereo
  updateReticleAndCamTransforms();
}

function startEyeLoop() {
  if (eyeLoopRunning) return;
  eyeLoopRunning = true;
  const loop = () => {
    if (remoteVideo.readyState >= 2 && !remoteVideo.paused && !remoteVideo.ended) {
      drawEyes();
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

/* ---------------- WebRTC setup ---------------- */
async function setupWebRTC() {
  viewerSessionId += 1;
  const thisSession = viewerSessionId;
  closeViewerPeer();
  viewerConnectStartedAt = performance.now();
  lastRemoteVideoTime = 0;
  lastRemoteVideoProgressAt = Date.now();
  statusEl.textContent = 'connecting...';
  pc = new RTCPeerConnection({ iceServers: [] });

  pc.ontrack = (ev) => {
    if (!pc || thisSession !== viewerSessionId) return;
    const [stream] = ev.streams;
    if (stream) {
      remoteVideo.srcObject = stream;
      statusEl.textContent = 'video connected';
      remoteVideo.play().catch(() => {});
      remoteVideo.onloadedmetadata = () => {
        resizeEyeCanvases();
        lastRemoteVideoTime = Number(remoteVideo.currentTime || 0);
        lastRemoteVideoProgressAt = Date.now();
        startEyeLoop();
      };
    }
  };

  pc.ondatachannel = (ev) => {
    if (!pc || thisSession !== viewerSessionId) return;
    if (ev.channel.label === 'orient') {
      orientChannel = ev.channel;
      orientChannel.onopen = () => {
        if (!pc || thisSession !== viewerSessionId) return;
        statusEl.textContent = 'connected (orient channel)';
      };
      orientChannel.onclose = () => {
        if (!pc || thisSession !== viewerSessionId) return;
        statusEl.textContent = 'orient channel closed';
      };
    }
  };

  pc.onicecandidate = (ev) => {
    if (ev.candidate) {
      sendViewerCandidate(ev.candidate.toJSON ? ev.candidate.toJSON() : ev.candidate);
    }
  };

  pc.onconnectionstatechange = () => {
    if (!pc || thisSession !== viewerSessionId) return;
    const st = pc.connectionState;
    statusEl.textContent = 'pc: ' + st;
    if (st === 'failed' || st === 'closed') {
      scheduleViewerReconnect(st);
      return;
    }
    if (st === 'disconnected') {
      setTimeout(() => {
        if (!pc || thisSession !== viewerSessionId) return;
        if (pc.connectionState === 'disconnected') {
          scheduleViewerReconnect('disconnected');
        }
      }, 1400);
    }
  };

  let offer = null;
  while (!offer && thisSession === viewerSessionId) {
    offer = await fetchHostOffer();
    if (!offer) {
      statusEl.textContent = 'waiting for host...';
      await sleep(1000);
    }
  }
  if (!offer || !pc || thisSession !== viewerSessionId) return;
  activeOfferId = offer.offerId || null;

  await pc.setRemoteDescription(offer);
  const answer = await pc.createAnswer();
  await pc.setLocalDescription(answer);
  await sendViewerAnswer(answer, activeOfferId);

  statusEl.textContent = 'answer sent, waiting for ICE';

  clearViewerPollTimer();
  viewerCandPollTimer = setInterval(() => {
    if (!pc || thisSession !== viewerSessionId) return;
    pollHostCandidates();
  }, 1000);
}

/* ---------------- Init ---------------- */
function init() {
  setupWebRTC().catch(err => {
    console.error('viewer webrtc error', err);
    statusEl.textContent = 'viewer webrtc error';
    scheduleViewerReconnect('init_error', 1500);
  });
  startViewerWatchdog();
  window.addEventListener('online', () => scheduleViewerReconnect('network_online', 300));

  // Initial UI state
  sizeVal.textContent   = `${(+settings.screenScale).toFixed(2)}×`;
  distVal.textContent   = `${(+settings.screenDist).toFixed(2)} m`;
  eyePxVal.textContent  = `${Math.round(settings.eyePx)} px`;
  camOpacityVal.textContent = `${settings.camOpacity}%`;
  curveRadiusVal.textContent = `${(+settings.screenCurveRadius).toFixed(2)} m`;
  gestureInactiveMsVal.textContent = `${Math.round(settings.gestureInactiveMs)} ms`;
  gestureDoubleMsVal.textContent = `${Math.round(settings.gestureDoublePinchMs)} ms`;

  applyDotSize();
  applyScreenOpacity();
  applyCurveRadiusValue();
  applyGestureTimingLabels();
  if (mpOverlayEnabledEl) {
    mpOverlayEnabledEl.checked = mpOverlayEnabled;
  }
  applyCamStyle();
  applyMediapipeOverlayStyle();
  applyCamLensStyle();
  updateReticleAndCamTransforms();
  startGestureUploadLoop();

  // Pull server settings once at start to sync HUD
  pullSettings();
}

window.addEventListener('beforeunload', () => {
  closeViewerPeer();
});

init();
