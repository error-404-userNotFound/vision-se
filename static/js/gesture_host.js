const feedImg = document.getElementById('feed');
const statusEl = document.getElementById('status');
const gestureRows = document.getElementById('gestureRows');
const statsRows = document.getElementById('statsRows');
const logsEl = document.getElementById('logs');
let feedBusy = false;
let feedSeq = 0;
let feedPendingSince = 0;
let statusStateText = 'status connecting…';
let feedStateText = 'feed connecting…';

function refreshHeaderStatus() {
  statusEl.textContent = `${feedStateText} | ${statusStateText}`;
}

function yn(flag) {
  return `<span class="${flag ? 'yes' : 'no'}">${flag ? 'YES' : 'NO'}</span>`;
}

function row(label, valueHtml) {
  return `<div class="row"><span class="label">${label}</span><span>${valueHtml}</span></div>`;
}

function safeNum(v, fallback = 0) {
  return Number.isFinite(Number(v)) ? Number(v) : fallback;
}

function renderStatus(s) {
  const cooldown = Math.max(0, safeNum(s.cooldownRemainingMs));
  const frameAge = Math.max(0, safeNum(s.lastFrameAgeMs));
  const holdMs = Math.max(0, safeNum(s.pinchHoldMs));
  const holdThresh = Math.max(0, safeNum(s.pinchHoldThresholdMs));

  gestureRows.innerHTML = [
    row('pinch_active', yn(!!s.pinchActive)),
    row('tracking_enabled', yn(!!s.trackingEnabled)),
    row('drag_hand_spread', yn(!!s.dragHandSpread)),
    row('drag_hand_detected', yn(!!s.dragHandDetected)),
    row('cooldown_active', yn(cooldown > 0)),
    row('two_finger_recent', yn((Date.now() / 1000 - safeNum(s.lastTwoFingerAt)) <= 0.9))
  ].join('');

  statsRows.innerHTML = [
    row('hands_detected', String(s.handsDetected ?? 0)),
    row('pinch_ratio', typeof s.lastPinchRatio === 'number' ? s.lastPinchRatio.toFixed(4) : 'n/a'),
    row('pinch_threshold', `${safeNum(s.pinchOnRatio, 0).toFixed(3)} / ${safeNum(s.pinchOffRatio, 0).toFixed(3)}`),
    row('hold_ms', `${Math.round(holdMs)} / ${Math.round(holdThresh)}`),
    row('tracking_center_px', `(${Math.round(safeNum(s.trackingX, 0))}, ${Math.round(safeNum(s.trackingY, 0))})`),
    row('tracking_center_norm', `(${safeNum(s.trackingCenterNormX, 0.5).toFixed(3)}, ${safeNum(s.trackingCenterNormY, 0.5).toFixed(3)})`),
    row('drag_center_norm', `(${safeNum(s.dragHandCenterNormX, 0.5).toFixed(3)}, ${safeNum(s.dragHandCenterNormY, 0.5).toFixed(3)})`),
    row('drag_span_px', `${safeNum(s.dragHandSpanPx, 0).toFixed(1)} px`),
    row('drag_box_px', `${safeNum(s.dragHandBoxWpx, 0).toFixed(1)} x ${safeNum(s.dragHandBoxHpx, 0).toFixed(1)}`),
    row('drag_scale_gain', `${safeNum(s.dragScaleGain, 1.0).toFixed(2)}x`),
    row('tracking_reason', String(s.trackingDisableReason || s.trackingReason || 'n/a')),
    row('keypoint_stream', yn(!!s.gestureKeypointStreamEnabled)),
    row('keypoint_seq', String(Math.round(safeNum(s.keypointsSeq, 0)))),
    row('keypoint_age', `${Math.round(safeNum(s.keypointsAgeMs, 0))} ms`),
    row('phone_connected', yn(!!s.phoneConnected)),
    row('heartbeat_age', `${Math.round(safeNum(s.heartbeatAgeMs, 0))} ms`),
    row('cursor_auto_supp', yn(!!s.cursorAutoSuppressed)),
    row('cooldown_ms', String(cooldown)),
    row('frames_recv/proc', `${s.framesReceived ?? 0} / ${s.framesProcessed ?? 0}`),
    row('last_frame_age', `${frameAge} ms`),
    row('last_action', String(s.lastAction || 'none'))
  ].join('');
}

async function pollStatus() {
  try {
    const r = await fetch('/gesture_status', { cache: 'no-store' });
    if (!r.ok) throw new Error(`status ${r.status}`);
    const s = await r.json();
    renderStatus(s);
    statusStateText = 'status live';
    refreshHeaderStatus();
  } catch {
    statusStateText = 'status offline';
    refreshHeaderStatus();
  }
}

async function pollLogs() {
  try {
    const r = await fetch('/gesture_logs?n=28', { cache: 'no-store' });
    if (!r.ok) return;
    const data = await r.json();
    const lines = Array.isArray(data.lines) ? data.lines : [];
    logsEl.innerHTML = lines.map((x) => `<li>${String(x)}</li>`).join('');
    logsEl.scrollTop = logsEl.scrollHeight;
  } catch {
    // ignore
  }
}

function initFeed() {
  const requestFrame = () => {
    const now = Date.now();
    if (feedBusy) {
      if ((now - feedPendingSince) < 1500) return;
      feedBusy = false;
    }
    feedBusy = true;
    feedPendingSince = now;
    const seq = ++feedSeq;
    feedImg.onload = () => {
      if (seq !== feedSeq) return;
      feedBusy = false;
      feedStateText = 'feed live';
      refreshHeaderStatus();
    };
    feedImg.onerror = () => {
      if (seq !== feedSeq) return;
      feedBusy = false;
      feedStateText = 'feed reconnecting…';
      refreshHeaderStatus();
    };
    feedImg.src = `/overlay.jpg?ts=${now}&n=${seq}`;
  };
  requestFrame();
  setInterval(requestFrame, 85);
}

function init() {
  refreshHeaderStatus();
  initFeed();
  pollStatus();
  pollLogs();
  setInterval(pollStatus, 220);
  setInterval(pollLogs, 700);
}

init();
