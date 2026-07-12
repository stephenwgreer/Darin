/**
 * Darin Audio Assistant — vanilla JS frontend (card-copilot UI).
 *
 * Architecture:
 *   EventSource /api/events  ← SSE push from server (multi-client fan-out)
 *   fetch() POST /api/*      → REST actions to server
 *
 * All fetch() and EventSource URLs append ?token=${APP_TOKEN}.
 * APP_TOKEN is set by /static/boot.js (no inline scripts — CSP-friendly).
 *
 * Two lanes render here:
 *   - live lanes (watcher + every reactive registry button + Ask): atomic
 *     'card' SSE events rendered into the card feed. The action bar renders
 *     ALL reactive prompts from /api/prompts — no hard-coded button count.
 *     Card content is inserted with
 *     textContent only — never innerHTML.
 *   - post-meeting lane: long-form streaming (template_setup / stream_item /
 *     stream_text / section_header) into the output panel. stream_text is
 *     accumulated raw and rendered as plain text per animation frame; the
 *     full markdown parse happens ONCE at processing_complete.
 *
 * All SSE-driven DOM writes go through a single requestAnimationFrame queue.
 */

'use strict';

// ── Helpers ────────────────────────────────────────────────────────────────

function apiUrl(path) {
  return `${path}?token=${window.APP_TOKEN}`;
}

async function apiFetch(path, method, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined && body !== null) opts.body = JSON.stringify(body);
  try {
    const resp = await fetch(apiUrl(path), opts);
    if (!resp.ok) console.error(`${method} ${path} failed:`, resp.status);
    return resp;
  } catch (e) {
    console.error(`${method} ${path} network error:`, e);
    return null;
  }
}

const apiPost = (path, body) => apiFetch(path, 'POST', body);
const apiPut = (path, body) => apiFetch(path, 'PUT', body);
const apiDelete = path => apiFetch(path, 'DELETE');

async function apiGet(path) {
  try {
    const resp = await fetch(apiUrl(path));
    if (!resp.ok) { console.error(`GET ${path} failed:`, resp.status); return null; }
    return await resp.json();
  } catch (e) {
    console.error(`GET ${path} network error:`, e);
    return null;
  }
}

// ── DOM refs ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const el = {
  stateBadge:        $('state-badge'),
  watcherDot:        $('watcher-dot'),
  personaToggle:     $('persona-toggle'),
  btnStart:          $('btn-start-meeting'),
  btnStop:           $('btn-stop-meeting'),
  btnNew:            $('btn-new-meeting'),
  recIndicator:      $('rec-indicator'),
  timerLabel:        $('timer-label'),
  captureStatus:     $('capture-status'),
  usageLine:         $('usage-line'),
  btnLast30:         $('btn-last-30'),
  btnLast60:         $('btn-last-60'),
  layout:            $('layout'),
  transcriptStrip:   $('transcript-strip'),
  transcriptScroll:  $('transcript-scroll'),
  stripFinals:       $('strip-finals'),
  stripInterims:     $('strip-interims'),
  actionButtons:     $('action-buttons'),
  customActions:     $('custom-actions'),
  qaInput:           $('qa-input'),
  btnAsk:            $('btn-ask'),
  cardFeed:          $('card-feed'),
  feedEmpty:         $('feed-empty'),
  postSection:       $('post-meeting-section'),
  bucketPostMeeting: $('bucket-post-meeting'),
  outputTitle:       $('output-title'),
  outputPanel:       $('output-panel'),
  outputMarkdown:    $('output-markdown'),
  rangeInputs:       $('range-inputs'),
  fromMinute:        $('from-minute'),
  toMinute:          $('to-minute'),
  btnCopyTranscript: $('btn-copy-transcript'),
  progressBar:       $('progress-bar'),
  toast:             $('toast'),
  btnHistory:        $('btn-history'),
  btnSettings:       $('btn-settings'),
};

// ── State ──────────────────────────────────────────────────────────────────

let currentState = 'idle';
let currentPersona = 'general';
// F4 retention: when false (default) expired proactive cards dim + collapse to
// a headline + cues (kept in the feed); when true they fade out and are removed.
let autoHideExpired = false;

// ── requestAnimationFrame render queue ─────────────────────────────────────
// Every SSE-driven DOM write is enqueued here and flushed once per frame.

const rafQueue = [];
let rafScheduled = false;

function enqueueRender(fn) {
  rafQueue.push(fn);
  if (!rafScheduled) {
    rafScheduled = true;
    requestAnimationFrame(flushRenders);
  }
}

function flushRenders() {
  rafScheduled = false;
  const batch = rafQueue.splice(0, rafQueue.length);
  for (const fn of batch) {
    try { fn(); } catch (e) { console.error('Render error:', e); }
  }
}

// ── Toast ──────────────────────────────────────────────────────────────────

let toastTimer = null;

function showToast(message) {
  el.toast.textContent = message;
  el.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.remove('show'), 4000);
}

// ── Timer display ──────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

// ── Per-button request tracking (per-lane concurrency, no global lock) ────
// Each interactive request disables ONLY its own button and shows a spinner.
// Prompt-lane entries are keyed 'prompt:<prompt_id>' and released by the
// prompt_id carried in processing_complete (exact match, with an oldest-
// 'prompt:'-entry fallback); transcribe entries are keyed 'transcribe' and
// released ONLY by transcription_complete. A safety timeout self-heals any
// mismatch so the UI can never wedge.

const pendingRequests = [];
const REQUEST_TIMEOUT_MS = 90000;

function setButtonBusy(btn, busy) {
  if (!btn) return;
  btn.dataset.busy = busy ? '1' : '';
  btn.disabled = busy || btn.dataset.unavailable === '1';
  let spinner = btn.querySelector('.spinner');
  if (busy && !spinner) {
    spinner = document.createElement('span');
    spinner.className = 'spinner';
    btn.appendChild(spinner);
  } else if (!busy && spinner) {
    spinner.remove();
  }
}

function beginRequest(key, btn) {
  const entry = { key, btn, timer: null };
  setButtonBusy(btn, true);
  entry.timer = setTimeout(() => {
    releaseRequest(entry);
    showToast('Request timed out — button re-enabled');
  }, REQUEST_TIMEOUT_MS);
  pendingRequests.push(entry);
  return entry;
}

function releaseRequest(entry) {
  const idx = pendingRequests.indexOf(entry);
  if (idx >= 0) pendingRequests.splice(idx, 1);
  clearTimeout(entry.timer);
  setButtonBusy(entry.btn, false);
  updateLongformLock();
}

function releaseOldestRequest(keyPrefix) {
  const entry = keyPrefix
    ? pendingRequests.find(e => e.key.startsWith(keyPrefix))
    : pendingRequests[0];
  if (entry) releaseRequest(entry);
}

// Release the exact entry for a backend prompt_id. Returns true if found.
function releasePromptRequest(promptId) {
  const entry = pendingRequests.find(e => e.key === `prompt:${promptId}`);
  if (entry) { releaseRequest(entry); return true; }
  return false;
}

function releaseAllRequests() {
  while (pendingRequests.length) releaseRequest(pendingRequests[0]);
}

// Long-form streaming is single-flight server-side (one shared StreamBuffer):
// while a long-form request is pending, every other post-meeting button is
// disabled so the user cannot corrupt the in-flight stream.
function updateLongformLock() {
  const busy = pendingRequests.some(e => e.longform);
  document.querySelectorAll('#bucket-post-meeting .btn-prompt').forEach(btn => {
    if (btn.dataset.busy === '1') return; // the streaming button keeps its spinner
    btn.disabled = busy || btn.dataset.unavailable === '1';
  });
}

function isRequestPending(key) {
  return pendingRequests.some(e => e.key === key);
}

// ── State machine ──────────────────────────────────────────────────────────

function applyState(state) {
  const prev = currentState;
  currentState = state;

  if (state === 'active' && prev !== 'active') resetSessionUI();

  el.stateBadge.className = 'badge badge-' + (state === 'post_meeting' ? 'post-meeting' : state);
  el.stateBadge.textContent =
    { idle: 'Idle', active: 'In Session', post_meeting: 'Post-Meeting' }[state] || state;

  el.btnStart.hidden = state !== 'idle';
  el.btnStop.hidden  = state !== 'active';
  el.btnNew.hidden   = state !== 'post_meeting';
  el.btnStart.disabled = false;
  el.btnStop.disabled  = false;
  el.btnNew.disabled   = false;

  // Recording indicator + live strip exist ONLY while a session is active.
  el.recIndicator.hidden = state !== 'active';
  el.transcriptStrip.hidden = state !== 'active';
  // The transcript sidebar column only reserves grid space while it is shown,
  // so the main column spans full width when there is no live transcript.
  el.layout.classList.toggle('with-sidebar', state === 'active');
  if (state !== 'active') el.timerLabel.textContent = '00:00:00';

  el.btnLast30.disabled = state !== 'active';
  el.btnLast60.disabled = state !== 'active';

  el.postSection.hidden = state !== 'post_meeting';

  if (state !== 'active' && state !== 'post_meeting') {
    el.watcherDot.className = 'watcher-dot watcher-stopped';
    el.watcherDot.title = 'Watcher off';
  }

  // Reactive buttons + Ask need a transcript: active or post-meeting.
  const hasTranscript = state === 'active' || state === 'post_meeting';
  setLaneAvailability('.btn-action', hasTranscript);
  setLaneAvailability('#bucket-post-meeting .btn-prompt', state === 'post_meeting');
  el.qaInput.disabled = !hasTranscript;
  el.btnAsk.disabled = !hasTranscript || isRequestPending('prompt:ask');
}

function setLaneAvailability(selector, available) {
  document.querySelectorAll(selector).forEach(btn => {
    btn.dataset.unavailable = available ? '' : '1';
    btn.disabled = !available || btn.dataset.busy === '1';
  });
}

function resetSessionUI() {
  clearCardFeed();
  clearTranscriptStrip();
  el.outputTitle.textContent = 'Analysis Output';
  el.outputPanel.textContent = '';
  el.outputMarkdown.textContent = '';
  el.outputMarkdown.hidden = true;
  rawStreamText = '';
  el.captureStatus.textContent = '';
  el.usageLine.textContent = '';
  el.progressBar.hidden = true;
}

// ── Live transcript sidebar ─────────────────────────────────────────────────
// The transcript lives in a right-hand, viewport-bound sidebar (F1). Finals
// accumulate newest-at-bottom inside an internally-scrolling column; interim
// lines are muted and replaced in place (one per speaker) below the finals.
// The column auto-scrolls to the newest line UNLESS the user has scrolled up.

const MAX_STRIP_LINES = 300;
const interimBySpeaker = new Map();   // speakerKey → element
const pendingInterims = new Map();    // speakerKey → {text, speaker}
const pendingFinals = [];
let transcriptFlushQueued = false;
let transcriptAutoScroll = true;

function transcriptNearBottom() {
  const s = el.transcriptScroll;
  return s.scrollHeight - s.scrollTop - s.clientHeight < 48;
}

function maybeAutoScrollTranscript() {
  if (transcriptAutoScroll) el.transcriptScroll.scrollTop = el.transcriptScroll.scrollHeight;
}

el.transcriptScroll.addEventListener('scroll', () => {
  // Pause auto-scroll the moment the user scrolls up; resume once they return
  // to (near) the bottom.
  transcriptAutoScroll = transcriptNearBottom();
});

function speakerKey(speaker) {
  return speaker === 'ME' || speaker === 'THEM' ? speaker : 'UNK';
}

function buildStripLine(text, speaker, isInterim) {
  const line = document.createElement('div');
  line.className = 'strip-line' + (isInterim ? ' strip-interim' : '');
  if (speaker === 'ME' || speaker === 'THEM') {
    const tag = document.createElement('span');
    tag.className = 'spk ' + (speaker === 'ME' ? 'spk-me' : 'spk-them');
    tag.textContent = speaker;
    line.appendChild(tag);
  }
  const txt = document.createElement('span');
  txt.className = 'strip-text';
  txt.textContent = text;
  line.appendChild(txt);
  return line;
}

function queueTranscriptFlush() {
  if (transcriptFlushQueued) return;
  transcriptFlushQueued = true;
  enqueueRender(flushTranscript);
}

function flushTranscript() {
  transcriptFlushQueued = false;

  for (const { text, speaker } of pendingFinals.splice(0, pendingFinals.length)) {
    const key = speakerKey(speaker);
    const interim = interimBySpeaker.get(key);
    if (interim) { interim.remove(); interimBySpeaker.delete(key); }
    pendingInterims.delete(key);
    el.stripFinals.appendChild(buildStripLine(text, speaker, false));
    while (el.stripFinals.children.length > MAX_STRIP_LINES) {
      el.stripFinals.firstChild.remove();
    }
  }

  for (const [key, { text, speaker }] of pendingInterims) {
    let node = interimBySpeaker.get(key);
    if (!node) {
      node = buildStripLine(text, speaker, true);
      interimBySpeaker.set(key, node);
      el.stripInterims.appendChild(node);
    } else {
      node.querySelector('.strip-text').textContent = text;
    }
  }
  pendingInterims.clear();
  maybeAutoScrollTranscript();
}

function clearTranscriptStrip() {
  el.stripFinals.textContent = '';
  el.stripInterims.textContent = '';
  interimBySpeaker.clear();
  pendingInterims.clear();
  pendingFinals.length = 0;
  transcriptAutoScroll = true;
}

// ── Card feed ──────────────────────────────────────────────────────────────

const CARD_TYPE_LABELS = {
  answer: 'Answer',
  fact_check: 'Fact check',
  reframe: 'Reframe',
  status: 'Where we are',
  next_step: 'Next step',
  heads_up: 'Heads up',
};

const cardExpiryTimers = new Map(); // card id → [timeout ids]

function updateFeedEmpty() {
  el.feedEmpty.hidden = el.cardFeed.children.length > 0;
}

function buildCardCues(cues) {
  const row = document.createElement('div');
  row.className = 'card-cues';
  for (const cue of cues.slice(0, 3)) {
    if (!cue) continue;
    const badge = document.createElement('span');
    badge.className = 'card-cue';
    badge.textContent = cue;
    row.appendChild(badge);
  }
  return row.children.length ? row : null;
}

function buildCardElement(card) {
  const article = document.createElement('article');
  article.className = `copilot-card lane-${card.lane} urgency-${card.urgency}`;
  article.dataset.cardId = card.id;

  // Aged cards collapse to headline + cues; clicking the card (outside its
  // buttons) re-expands the full body.
  article.addEventListener('click', e => {
    if (!article.classList.contains('aged')) return;
    if (e.target.closest('button')) return;
    article.classList.toggle('aged-expanded');
  });

  const top = document.createElement('div');
  top.className = 'card-top';

  const chip = document.createElement('span');
  chip.className = `card-chip chip-${card.type}`;
  chip.textContent = CARD_TYPE_LABELS[card.type] || card.type;
  top.appendChild(chip);

  if (card.urgency === 'now') {
    const urgent = document.createElement('span');
    urgent.className = 'card-urgent-chip';
    urgent.textContent = 'NOW';
    top.appendChild(urgent);
  }

  if (card.lane === 'proactive') {
    const lane = document.createElement('span');
    lane.className = 'card-lane-chip';
    lane.textContent = 'watcher';
    top.appendChild(lane);
  }

  const dismiss = document.createElement('button');
  dismiss.className = 'card-dismiss';
  dismiss.title = 'Dismiss (suppresses this topic for the meeting)';
  dismiss.textContent = '✕';
  dismiss.addEventListener('click', () => dismissCard(card.id));
  top.appendChild(dismiss);

  article.appendChild(top);

  const headline = document.createElement('h3');
  headline.className = 'card-headline';
  headline.textContent = card.headline;
  article.appendChild(headline);

  if (Array.isArray(card.bullets) && card.bullets.length > 0) {
    const ul = document.createElement('ul');
    ul.className = 'card-bullets';
    for (const bullet of card.bullets.slice(0, 3)) {
      const li = document.createElement('li');
      li.textContent = bullet;
      ul.appendChild(li);
    }
    article.appendChild(ul);
  }

  // F4: instant-glance cue badges between bullets and say_this.
  if (Array.isArray(card.cues) && card.cues.length > 0) {
    const cueRow = buildCardCues(card.cues);
    if (cueRow) article.appendChild(cueRow);
  }

  if (card.say_this) {
    const say = document.createElement('div');
    say.className = 'say-this';
    const label = document.createElement('span');
    label.className = 'say-this-label';
    label.textContent = 'SAY';
    const text = document.createElement('span');
    text.className = 'say-this-text';
    text.textContent = card.say_this;
    const copyBtn = document.createElement('button');
    copyBtn.className = 'say-this-copy';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(card.say_this);
        copyBtn.textContent = 'Copied';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
      } catch (e) {
        console.error('Clipboard write failed:', e);
        showToast('Copy failed');
      }
    });
    say.appendChild(label);
    say.appendChild(text);
    say.appendChild(copyBtn);
    article.appendChild(say);
  }

  const meta = document.createElement('div');
  meta.className = 'card-meta';
  const parts = [`${card.confidence} confidence`, card.source];
  if (card.trigger) parts.push(card.trigger);
  meta.textContent = parts.join(' · ');
  article.appendChild(meta);

  return article;
}

function renderCard(card) {
  if (!card || !card.id) return;
  if (el.cardFeed.querySelector(`[data-card-id="${CSS.escape(card.id)}"]`)) return;

  const node = buildCardElement(card);
  el.cardFeed.prepend(node);
  updateFeedEmpty();

  // Proactive cards transition at expires_in_s: by default they age (dim +
  // collapse, kept below the fresh cards); with auto_hide_expired on they fade
  // out and are removed (old behavior). Reactive cards stay pinned until
  // dismissed.
  if (card.lane === 'proactive') {
    const expireMs = Math.max(5, Number(card.expires_in_s) || 45) * 1000;
    const t1 = setTimeout(() => {
      if (autoHideExpired) {
        node.classList.add('expiring');
        const t2 = setTimeout(() => removeCard(card.id), 700);
        cardExpiryTimers.set(card.id, [t2]);
      } else {
        ageCard(card.id);
      }
    }, expireMs);
    cardExpiryTimers.set(card.id, [t1]);
  }
}

// Move a card to its aged/compact state: dimmed, collapsed to headline + cues,
// sunk below the fresh cards. Idempotent.
function ageCard(cardId) {
  const timers = cardExpiryTimers.get(cardId);
  if (timers) { timers.forEach(clearTimeout); cardExpiryTimers.delete(cardId); }
  const node = el.cardFeed.querySelector(`[data-card-id="${CSS.escape(cardId)}"]`);
  if (!node || node.classList.contains('aged')) return;
  node.classList.remove('expiring', 'aged-expanded');
  node.classList.add('aged');
  el.cardFeed.appendChild(node); // sink beneath the fresh cards
  updateFeedEmpty();
}

function removeCard(cardId) {
  const timers = cardExpiryTimers.get(cardId);
  if (timers) { timers.forEach(clearTimeout); cardExpiryTimers.delete(cardId); }
  const node = el.cardFeed.querySelector(`[data-card-id="${CSS.escape(cardId)}"]`);
  if (node) node.remove();
  updateFeedEmpty();
}

function clearCardFeed() {
  for (const timers of cardExpiryTimers.values()) timers.forEach(clearTimeout);
  cardExpiryTimers.clear();
  el.cardFeed.textContent = '';
  updateFeedEmpty();
}

async function dismissCard(cardId) {
  const resp = await apiPost(`/api/cards/${encodeURIComponent(cardId)}/dismiss`);
  if (resp && resp.ok) {
    // Compact into history instead of vanishing; the dismiss endpoint still
    // ran so watcher topic-suppression keeps working. The card_dismissed SSE
    // also fires; ageCard is idempotent.
    ageCard(cardId);
  } else {
    showToast('Dismiss failed');
  }
}

// ── Action bar (all reactive registry prompts + custom prompts) ────────────
// Every reactive prompt returned by /api/prompts becomes a button — the count
// is whatever the backend registry defines (no hard-coded button count).

function buildReactiveButton(cfg, extraClass) {
  const btn = document.createElement('button');
  btn.className = 'btn btn-action' + (extraClass ? ` ${extraClass}` : '');
  btn.dataset.promptId = cfg.id;
  btn.dataset.unavailable = currentState === 'active' || currentState === 'post_meeting' ? '' : '1';
  btn.disabled = btn.dataset.unavailable === '1';
  const label = document.createElement('span');
  label.textContent = cfg.button_text;
  btn.appendChild(label);

  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    const entry = beginRequest(`prompt:${cfg.id}`, btn);
    const resp = await apiPost('/api/run_prompt', { prompt_id: cfg.id });
    if (!resp || !resp.ok) {
      releaseRequest(entry);
      showToast(resp && resp.status === 409
        ? `"${cfg.button_text}" is already running`
        : `"${cfg.button_text}" failed${resp ? ` (${resp.status})` : ''}`);
    }
  });

  return btn;
}

function buildPostMeetingButton(cfg) {
  const btn = document.createElement('button');
  btn.className = 'btn btn-prompt';
  btn.dataset.promptId = cfg.id;
  btn.dataset.unavailable = currentState === 'post_meeting' ? '' : '1';
  btn.disabled = btn.dataset.unavailable === '1';

  const label = document.createTextNode(cfg.button_text);
  const check = document.createElement('span');
  check.className = 'badge-check';
  check.textContent = '✓';
  btn.appendChild(label);
  btn.appendChild(check);

  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    el.outputTitle.textContent = cfg.output_title || 'Analysis Output';
    el.outputPanel.textContent = '';
    el.outputMarkdown.textContent = '';
    el.outputMarkdown.hidden = true;
    rawStreamText = '';

    const body = { prompt_id: cfg.id };
    const mode = document.querySelector('input[name="segment-mode"]:checked').value;
    if (mode === 'range') {
      const from = parseInt(el.fromMinute.value, 10);
      const to = parseInt(el.toMinute.value, 10);
      if (!isNaN(from)) body.from_minute = from;
      if (!isNaN(to)) body.to_minute = to;
    }

    const entry = beginRequest(`prompt:${cfg.id}`, btn);
    entry.longform = true;
    updateLongformLock();
    const resp = await apiPost('/api/run_post_meeting_prompt', body);
    if (!resp || !resp.ok) {
      releaseRequest(entry);
      showToast(resp && resp.status === 409
        ? 'Another analysis is already running'
        : `"${cfg.button_text}" failed${resp ? ` (${resp.status})` : ''}`);
    }
  });

  return btn;
}

async function loadPrompts() {
  const data = await apiGet('/api/prompts');
  if (!data) { showToast('Failed to load prompts'); return; }

  el.actionButtons.textContent = '';
  (data.reactive || []).forEach(cfg => {
    el.actionButtons.appendChild(buildReactiveButton(cfg));
  });

  rebuildCustomActions(data.custom || []);

  el.bucketPostMeeting.textContent = '';
  (data.post_meeting || []).forEach(cfg => {
    el.bucketPostMeeting.appendChild(buildPostMeetingButton(cfg));
  });
}

function rebuildCustomActions(customConfigs) {
  // The prompt-editor entry point now lives as a gear in the nav (F6); this
  // row holds only the custom reactive buttons.
  el.customActions.textContent = '';
  customConfigs.forEach(cfg => {
    el.customActions.appendChild(buildReactiveButton(cfg, 'btn-action-custom'));
  });
}

async function reloadCustomBucket() {
  const data = await apiGet('/api/prompts');
  if (data) rebuildCustomActions(data.custom || []);
}

// ── Post-meeting streaming output ──────────────────────────────────────────

let rawStreamText = '';
let streamRenderQueued = false;

function queueStreamRender() {
  if (streamRenderQueued) return;
  streamRenderQueued = true;
  enqueueRender(() => {
    streamRenderQueued = false;
    // Plain text while streaming — the markdown parse happens once, at
    // processing_complete (never a full reparse per chunk).
    el.outputMarkdown.hidden = false;
    el.outputMarkdown.classList.add('streaming');
    el.outputMarkdown.textContent = rawStreamText;
  });
}

// ── SSE event handlers ─────────────────────────────────────────────────────

const handlers = {
  state_change(data) {
    enqueueRender(() => applyState(data.state));
  },

  timer_tick(data) {
    enqueueRender(() => { el.timerLabel.textContent = formatElapsed(data.elapsed); });
  },

  card(data) {
    enqueueRender(() => renderCard(data));
  },

  card_dismissed(data) {
    // Dismissed cards compact into history rather than disappearing (F4).
    enqueueRender(() => ageCard(data.id));
  },

  watcher_status(data) {
    enqueueRender(() => {
      const state = data.state || 'stopped';
      el.watcherDot.className = 'watcher-dot watcher-' +
        (state === 'watching' ? 'watching' : state === 'thinking' ? 'thinking' : 'stopped');
      el.watcherDot.title = 'Watcher: ' + state;
    });
  },

  usage(data) {
    enqueueRender(() => {
      const cost = Number(data.meeting_cost_usd);
      el.usageLine.textContent = isNaN(cost) ? '' : `this meeting ~$${cost.toFixed(2)}`;
    });
  },

  error(data) {
    enqueueRender(() => {
      showToast(`Error: ${(data && data.message) || 'Something went wrong'}`);
    });
  },

  interim_transcript(data) {
    if (!data || !data.text) return;
    pendingInterims.set(speakerKey(data.speaker), { text: data.text, speaker: data.speaker });
    queueTranscriptFlush();
  },

  final_transcript(data) {
    if (!data || !data.text) return;
    pendingFinals.push({ text: data.text, speaker: data.speaker });
    queueTranscriptFlush();
  },

  template_setup(data) {
    enqueueRender(() => {
      rawStreamText = '';
      el.outputTitle.textContent = data.output_title || 'Analysis Output';
      // scaffold_html is server-controlled HTML from STATIC_TEMPLATES (Python constants)
      el.outputPanel.innerHTML = data.scaffold_html || ''; // safe: server-only source
      el.outputMarkdown.textContent = '';
      el.outputMarkdown.hidden = true;
    });
  },

  stream_item(data) {
    enqueueRender(() => {
      const list = document.getElementById(data.list_id);
      if (list) {
        // item_html is a regex-extracted <li> from Claude API — server-controlled
        const tmp = document.createElement('div');
        tmp.innerHTML = data.item_html; // safe: server-only source
        while (tmp.firstChild) list.appendChild(tmp.firstChild);
      }
    });
  },

  stream_text(data) {
    rawStreamText += data.chunk;
    queueStreamRender();
  },

  section_header(data) {
    enqueueRender(() => { el.outputTitle.textContent = data.text; });
  },

  processing_complete(data) {
    enqueueRender(() => {
      const promptId = data && data.prompt_id;
      if (data && data.error) {
        // Release the exact request when the backend tells us which one
        // failed; otherwise release everything so the UI can never wedge.
        if (!(promptId && releasePromptRequest(promptId))) releaseAllRequests();
        showToast(`Error: ${data.error}`);
        el.progressBar.hidden = true;
        return;
      }
      // Exact release by prompt_id; fall back to the oldest PROMPT-lane entry.
      // Never touch 'transcribe' entries — those are released only by
      // transcription_complete (they complete via a different event).
      if (!(promptId && releasePromptRequest(promptId))) releaseOldestRequest('prompt:');
      el.progressBar.hidden = true;
      if (data && Array.isArray(data.cards) && data.cards.length === 0) {
        showToast('Nothing to add on that.');
      }
      if (rawStreamText) {
        // Single full markdown parse at completion.
        el.outputMarkdown.classList.remove('streaming');
        el.outputMarkdown.innerHTML = marked.parse(rawStreamText); // safe: Claude API response via marked.parse()
        rawStreamText = '';
      }
    });
  },

  progress(data) {
    enqueueRender(() => {
      el.progressBar.textContent = data.message || '';
      el.progressBar.hidden = !data.message;
    });
  },

  transcription_complete(data) {
    enqueueRender(() => {
      const wordCount = data.transcript
        ? data.transcript.split(/\s+/).filter(Boolean).length : 0;
      el.captureStatus.textContent = wordCount > 0
        ? `Transcribed (${wordCount} words)`
        : 'Transcription complete';
      releaseOldestRequest('transcribe');
    });
  },

  saved_analyses(data) {
    enqueueRender(() => {
      const analyses = data.analyses || {};
      document.querySelectorAll('.btn-prompt[data-prompt-id]').forEach(btn => {
        btn.classList.toggle('done', !!analyses[btn.dataset.promptId]);
      });
    });
  },
};

// ── SSE connection ─────────────────────────────────────────────────────────

function connectSSE() {
  const es = new EventSource(apiUrl('/api/events'));

  Object.keys(handlers).forEach(eventType => {
    es.addEventListener(eventType, evt => {
      try {
        handlers[eventType](JSON.parse(evt.data));
      } catch (e) {
        console.error('SSE parse error for', eventType, e);
      }
    });
  });

  es.onopen = () => { syncState(); };

  es.onerror = () => {
    console.warn('SSE connection lost — retrying in 3 s');
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

async function syncState() {
  const state = await apiGet('/api/state');
  if (state) {
    applyState(state.state);
    if (state.elapsed) el.timerLabel.textContent = formatElapsed(state.elapsed);
  }
}

// ── Session controls ───────────────────────────────────────────────────────
// Capture is session-scoped: nothing records until Start Session, and the
// state_change SSE event drives every visibility change.

el.btnStart.addEventListener('click', async () => {
  el.btnStart.disabled = true;
  const resp = await apiPost('/api/start_meeting');
  if (!resp || !resp.ok) {
    el.btnStart.disabled = false;
    showToast('Failed to start session');
  }
});

el.btnStop.addEventListener('click', async () => {
  el.btnStop.disabled = true;
  const resp = await apiPost('/api/stop_meeting');
  if (!resp || !resp.ok) {
    el.btnStop.disabled = false;
    showToast('Failed to end session');
  }
});

el.btnNew.addEventListener('click', async () => {
  el.btnNew.disabled = true;
  const resp = await apiPost('/api/reset');
  if (!resp || !resp.ok) {
    el.btnNew.disabled = false;
    showToast('Failed to reset');
  }
});

// ── Buffer capture buttons (session-scoped rolling buffer) ─────────────────

async function transcribeLastN(seconds, btn) {
  if (btn.disabled) return;
  const entry = beginRequest('transcribe', btn);
  el.captureStatus.textContent = `Capturing last ${seconds} s…`;
  const resp = await apiPost('/api/transcribe_last_n', { seconds });
  if (!resp || !resp.ok) {
    releaseRequest(entry);
    el.captureStatus.textContent = '';
    showToast('Capture failed');
  }
}

el.btnLast30.addEventListener('click', () => transcribeLastN(30, el.btnLast30));
el.btnLast60.addEventListener('click', () => transcribeLastN(60, el.btnLast60));

// ── Segment mode selector ──────────────────────────────────────────────────

document.querySelectorAll('input[name="segment-mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    el.rangeInputs.hidden = radio.value !== 'range';
  });
});

// ── Ask box (freeform reactive lane — answer arrives as a card) ────────────

async function submitQuestion() {
  const question = el.qaInput.value.trim();
  if (!question || isRequestPending('prompt:ask')) return;
  el.qaInput.value = '';
  const entry = beginRequest('prompt:ask', el.btnAsk);
  const resp = await apiPost('/api/ask', { question });
  if (!resp || !resp.ok) {
    releaseRequest(entry);
    showToast(resp && resp.status === 409 ? 'A question is already running' : 'Ask failed');
  }
}

el.btnAsk.addEventListener('click', submitQuestion);
el.qaInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitQuestion(); });

// ── Persona toggle ─────────────────────────────────────────────────────────

function setPersonaUI(persona) {
  currentPersona = persona;
  el.personaToggle.querySelectorAll('.persona-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.persona === persona);
  });
}

async function loadPersona() {
  const data = await apiGet('/api/persona');
  if (data && data.persona) setPersonaUI(data.persona);
}

el.personaToggle.querySelectorAll('.persona-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const persona = btn.dataset.persona;
    if (persona === currentPersona) return;
    const previous = currentPersona;
    setPersonaUI(persona); // optimistic
    const resp = await apiPost('/api/persona', { persona });
    if (!resp || !resp.ok) {
      setPersonaUI(previous);
      showToast('Failed to change persona');
    }
  });
});

// ── Copy transcript ────────────────────────────────────────────────────────

el.btnCopyTranscript.addEventListener('click', async () => {
  const data = await apiGet('/api/transcript');
  if (data && data.transcript) {
    try {
      await navigator.clipboard.writeText(data.transcript);
      el.btnCopyTranscript.textContent = 'Copied!';
      setTimeout(() => { el.btnCopyTranscript.textContent = 'Copy Transcript'; }, 2000);
    } catch (e) {
      console.error('Clipboard write failed:', e);
      showToast('Copy failed');
    }
  } else {
    showToast('No transcript available');
  }
});

// ── Modal helpers ──────────────────────────────────────────────────────────

function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

document.querySelectorAll('[data-close]').forEach(btn => {
  btn.addEventListener('click', () => closeModal(btn.dataset.close));
});

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeModal(overlay.id);
  });
});

// ── Settings dialog (storage + appearance + Context Pack) ──────────────────

const CTX_DOCS = ['profile', 'products', 'known_issues'];
const CTX_TOKEN_BUDGET = 20000;
let contextData = { profile: '', products: '', known_issues: '' };
let currentCtxTab = 'profile';

function applyBackground(style) {
  document.documentElement.classList.toggle('bg-darin', style === 'darin');
}

function estimateContextTokens() {
  let words = 0;
  for (const doc of CTX_DOCS) {
    words += (contextData[doc] || '').split(/\s+/).filter(Boolean).length;
  }
  return Math.round(words * 1.3);
}

function syncCtxTextarea() {
  contextData[currentCtxTab] = $('ctx-textarea').value;
}

function updateCtxTokenCount() {
  const tokens = estimateContextTokens();
  $('ctx-token-count').textContent = `≈ ${tokens.toLocaleString()} tokens total`;
  const over = tokens > CTX_TOKEN_BUDGET;
  $('ctx-token-warning').hidden = !over;
  $('ctx-token-count').classList.toggle('over-budget', over);
}

function showCtxTab(doc) {
  syncCtxTextarea();
  currentCtxTab = doc;
  document.querySelectorAll('#ctx-tabs .ptab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.ctx === doc);
  });
  $('ctx-textarea').value = contextData[doc] || '';
}

document.querySelectorAll('#ctx-tabs .ptab').forEach(tab => {
  tab.addEventListener('click', () => showCtxTab(tab.dataset.ctx));
});

$('ctx-textarea').addEventListener('input', () => {
  syncCtxTextarea();
  updateCtxTokenCount();
});

// ── Custom model endpoints (Settings) ───────────────────────────────────────
// GET /api/settings returns api_key masked to its last 4 chars; on save we send
// the full value if the user typed one, or the "__unchanged__" sentinel to keep
// the stored key untouched.

const UNCHANGED_SENTINEL = '__unchanged__';

function slugifyEndpointId(label) {
  const base = (label || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return `ep-${base || 'endpoint'}-${Date.now().toString(36)}`;
}

function buildEndpointRow(ep) {
  ep = ep || {};
  const row = document.createElement('div');
  row.className = 'endpoint-row';
  row.dataset.endpointId = ep.id || slugifyEndpointId(ep.label);

  const grid = document.createElement('div');
  grid.className = 'endpoint-fields';

  const mkInput = (cls, placeholder, value) => {
    const input = document.createElement('input');
    input.className = 'form-input ' + cls;
    input.placeholder = placeholder;
    input.value = value || '';
    return input;
  };

  const labelInput = mkInput('ep-label', 'Label (e.g. Groq Llama)', ep.label);
  const urlInput = mkInput('ep-url', 'https://api.example.com/v1', ep.base_url);
  const modelInput = mkInput('ep-model', 'Model name (e.g. llama-3.3-70b)', ep.model_name);

  const keyInput = document.createElement('input');
  keyInput.className = 'form-input ep-key';
  keyInput.type = 'password';
  const hasKey = !!ep.api_key; // masked, non-empty ⇒ a key is stored
  keyInput.dataset.hadKey = hasKey ? '1' : '0';
  keyInput.value = '';
  keyInput.placeholder = hasKey
    ? `API key (stored ${ep.api_key} — type to replace)`
    : 'API key (optional)';

  grid.appendChild(labelInput);
  grid.appendChild(urlInput);
  grid.appendChild(modelInput);
  grid.appendChild(keyInput);

  const del = document.createElement('button');
  del.type = 'button';
  del.className = 'pact-btn pact-btn-delete ep-delete';
  del.textContent = 'Remove';
  del.addEventListener('click', () => row.remove());

  row.appendChild(grid);
  row.appendChild(del);
  return row;
}

function renderEndpointList(endpoints) {
  const list = $('endpoint-list');
  list.textContent = '';
  endpoints.forEach(ep => list.appendChild(buildEndpointRow(ep)));
}

// Returns {endpoints, error}. Empty rows (no base_url) are dropped; a row with a
// base_url that is not http(s) is a hard error surfaced to the user.
function collectEndpoints() {
  const rows = $('endpoint-list').querySelectorAll('.endpoint-row');
  const endpoints = [];
  for (const row of rows) {
    const label = row.querySelector('.ep-label').value.trim();
    const baseUrl = row.querySelector('.ep-url').value.trim();
    const modelName = row.querySelector('.ep-model').value.trim();
    const keyInput = row.querySelector('.ep-key');
    const typedKey = keyInput.value.trim();

    if (!baseUrl && !label && !modelName && !typedKey) continue; // blank row
    if (!/^https?:\/\//i.test(baseUrl)) {
      return { error: `Endpoint "${label || row.dataset.endpointId}" needs an http(s) base URL.` };
    }
    let apiKey;
    if (typedKey) apiKey = typedKey;
    else apiKey = keyInput.dataset.hadKey === '1' ? UNCHANGED_SENTINEL : '';

    endpoints.push({
      id: row.dataset.endpointId,
      label,
      base_url: baseUrl,
      model_name: modelName,
      api_key: apiKey,
    });
  }
  return { endpoints };
}

$('btn-add-endpoint').addEventListener('click', () => {
  $('endpoint-list').appendChild(buildEndpointRow(null));
});

async function openSettings() {
  const [settings, context] = await Promise.all([
    apiGet('/api/settings'),
    apiGet('/api/context'),
  ]);
  if (settings) {
    $('settings-path-input').value = settings.storage_path || '';
    const radio = document.querySelector(
      `input[name="bg-style"][value="${settings.background_style || 'default'}"]`);
    if (radio) radio.checked = true;
    autoHideExpired = !!settings.auto_hide_expired;
    $('auto-hide-expired').checked = autoHideExpired;
    renderEndpointList(settings.custom_endpoints || []);
  }
  contextData = {
    profile: (context && context.profile) || '',
    products: (context && context.products) || '',
    known_issues: (context && context.known_issues) || '',
  };
  currentCtxTab = 'profile';
  document.querySelectorAll('#ctx-tabs .ptab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.ctx === 'profile');
  });
  $('ctx-textarea').value = contextData.profile;
  updateCtxTokenCount();
  openModal('modal-settings');
}

el.btnSettings.addEventListener('click', openSettings);

$('btn-browse-folder').addEventListener('click', async () => {
  const resp = await apiPost('/api/pick_folder', {});
  if (resp && resp.ok) {
    const data = await resp.json();
    if (data && data.path) $('settings-path-input').value = data.path;
  } else {
    showToast('Folder picker failed');
  }
});

$('btn-save-settings').addEventListener('click', async () => {
  syncCtxTextarea();
  const path = $('settings-path-input').value.trim();
  const bgRadio = document.querySelector('input[name="bg-style"]:checked');
  const bgStyle = bgRadio ? bgRadio.value : 'default';
  const autoHide = $('auto-hide-expired').checked;

  const { endpoints, error } = collectEndpoints();
  if (error) { showToast(error); return; }

  // Always persist the non-path settings (background, Cards retention toggle,
  // custom endpoints). storage_path is only included when the field is
  // non-empty so clearing it can't silently drop the rest of the save.
  const settingsBody = {
    background_style: bgStyle,
    auto_hide_expired: autoHide,
    custom_endpoints: endpoints,
  };
  if (path) settingsBody.storage_path = path;
  const requests = [
    apiPut('/api/context', contextData),
    apiPost('/api/settings', settingsBody),
  ];
  const responses = await Promise.all(requests);
  if (responses.some(r => !r || !r.ok)) {
    showToast('Failed to save settings');
    return;
  }
  autoHideExpired = autoHide;
  applyBackground(bgStyle);
  closeModal('modal-settings');
  showToast('Settings saved');
});

// ── History dialog ─────────────────────────────────────────────────────────

let historyCurrentMeetingId = null;

function formatMeetingDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    + ' · ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function formatDuration(seconds) {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  return m + ' min';
}

async function openHistory() {
  $('history-list-view').style.display = 'block';
  $('history-transcript-view').style.display = 'none';
  openModal('modal-history');
  await refreshMeetingList();
}

async function refreshMeetingList() {
  const data = await apiGet('/api/meetings');
  const container = $('meeting-list');
  while (container.firstChild) container.removeChild(container.firstChild);

  if (!data || !data.meetings || data.meetings.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'meeting-empty';
    empty.textContent = 'No meetings recorded yet.';
    container.appendChild(empty);
    return;
  }

  data.meetings.forEach(m => {
    const row = document.createElement('div');
    row.className = 'meeting-row';

    const info = document.createElement('div');
    info.className = 'meeting-info';

    const dateEl = document.createElement('div');
    dateEl.className = 'meeting-date';
    dateEl.textContent = formatMeetingDate(m.start_time);

    const titleEl = document.createElement('div');
    titleEl.className = 'meeting-title';
    titleEl.textContent = m.title
      ? formatMeetingDate(m.start_time) + ' — ' + m.title
      : formatMeetingDate(m.start_time);

    info.appendChild(dateEl);
    info.appendChild(titleEl);

    const dur = document.createElement('div');
    dur.className = 'meeting-duration';
    dur.textContent = formatDuration(m.duration_seconds);

    const arrow = document.createElement('span');
    arrow.textContent = '›';
    arrow.className = 'meeting-arrow';

    row.appendChild(info);
    row.appendChild(dur);
    row.appendChild(arrow);

    row.addEventListener('click', () => openMeetingTranscript(m.id));
    container.appendChild(row);
  });
}

function showHistoryTab(tab) {
  const onTranscript = tab !== 'cards';
  $('history-tab-transcript').classList.toggle('active', onTranscript);
  $('history-tab-cards').classList.toggle('active', !onTranscript);
  $('tx-transcript-pane').hidden = !onTranscript;
  $('tx-cards-pane').hidden = onTranscript;
}

async function loadMeetingCards() {
  const body = $('tx-cards-body');
  body.textContent = '';
  if (!historyCurrentMeetingId) return;
  const data = await apiGet(
    '/api/meetings/' + encodeURIComponent(historyCurrentMeetingId) + '/cards');
  const cards = (data && data.cards) || [];
  if (cards.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'tx-empty';
    empty.textContent = 'No cards recorded for this meeting.';
    body.appendChild(empty);
    return;
  }
  cards.forEach(c => {
    const row = document.createElement('div');
    row.className = 'tx-card-row';

    const headline = document.createElement('div');
    headline.className = 'tx-card-headline';
    headline.textContent = c.headline || '';
    row.appendChild(headline);

    if (Array.isArray(c.cues) && c.cues.length > 0) {
      const cueRow = buildCardCues(c.cues);
      if (cueRow) row.appendChild(cueRow);
    }

    if (c.say_this) {
      const say = document.createElement('div');
      say.className = 'tx-card-say';
      const label = document.createElement('span');
      label.className = 'say-this-label';
      label.textContent = 'SAY';
      const text = document.createElement('span');
      text.className = 'say-this-text';
      text.textContent = c.say_this;
      say.appendChild(label);
      say.appendChild(text);
      row.appendChild(say);
    }

    body.appendChild(row);
  });
}

$('history-tab-transcript').addEventListener('click', () => showHistoryTab('transcript'));
$('history-tab-cards').addEventListener('click', () => {
  showHistoryTab('cards');
  loadMeetingCards();
});

async function openMeetingTranscript(meetingId) {
  historyCurrentMeetingId = meetingId;
  const data = await apiGet('/api/meetings/' + encodeURIComponent(meetingId) + '/transcript');
  if (!data) return;

  $('history-list-view').style.display = 'none';
  $('history-transcript-view').style.display = 'block';
  showHistoryTab('transcript');

  $('tx-title').textContent = data.title
    ? formatMeetingDate(data.start_time) + ' — ' + data.title
    : formatMeetingDate(data.start_time);

  const dur = data.end_time
    ? formatDuration(Math.floor((new Date(data.end_time) - new Date(data.start_time)) / 1000))
    : '';
  $('tx-meta').textContent = dur;

  const body = $('tx-body');
  while (body.firstChild) body.removeChild(body.firstChild);

  if (!data.segments || data.segments.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'tx-empty';
    empty.textContent = 'No transcript available.';
    body.appendChild(empty);
    return;
  }

  const startTime = new Date(data.start_time);
  data.segments.forEach(seg => {
    const row = document.createElement('div');
    const ts = document.createElement('span');
    ts.className = 'tx-timestamp';
    const offsetSec = Math.floor((new Date(seg.timestamp) - startTime) / 1000);
    const mm = Math.floor(offsetSec / 60).toString().padStart(2, '0');
    const ss = (offsetSec % 60).toString().padStart(2, '0');
    ts.textContent = '[' + mm + ':' + ss + ']';
    const txt = document.createTextNode(seg.text);
    row.appendChild(ts);
    row.appendChild(txt);
    body.appendChild(row);
  });
}

$('tx-back-btn').addEventListener('click', () => {
  historyCurrentMeetingId = null;
  $('history-list-view').style.display = 'block';
  $('history-transcript-view').style.display = 'none';
});

el.btnHistory.addEventListener('click', openHistory);

// Historical Q&A — routed through the reactive card lane server-side; the
// answer arrives as a card in the main feed. Guarded per-request so a second
// ask can't stack while one is in flight.
async function submitHistoricalQuestion() {
  const question = $('tx-ask-input').value.trim();
  if (!question || !historyCurrentMeetingId || isRequestPending('prompt:ask')) return;
  $('tx-ask-input').value = '';
  const entry = beginRequest('prompt:ask', $('tx-ask-btn'));
  const resp = await apiPost(
    '/api/meetings/' + encodeURIComponent(historyCurrentMeetingId) + '/ask', { question });
  if (!resp || !resp.ok) {
    releaseRequest(entry);
    showToast('Ask failed');
    return;
  }
  closeModal('modal-history');
  showToast('Thinking — the answer will appear as a card');
}

$('tx-ask-btn').addEventListener('click', submitHistoricalQuestion);
$('tx-ask-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitHistoricalQuestion();
});

// ── Prompt editor ──────────────────────────────────────────────────────────

const BUCKET_LABELS = {
  reactive: 'Reactive',
  post_meeting: 'Post-Meeting',
  custom: 'Custom',
};
const BUCKET_ORDER = ['reactive', 'post_meeting', 'custom'];

let allPromptsCache = [];
let modelsCache = [];   // [{id,label,provider,model_name,available,supports_web_search}]
let promptEditorCurrentTab = 'reactive';
let promptEditorEditingId = null;

async function ensureModelsLoaded() {
  if (modelsCache.length) return;
  const data = await apiGet('/api/models');
  modelsCache = (data && data.models) || [];
}

async function openPromptEditor(defaultTab) {
  promptEditorCurrentTab = defaultTab || 'reactive';
  promptEditorEditingId = null;
  await ensureModelsLoaded();
  await refreshPromptEditor();
  $('prompt-list-view').style.display = '';
  $('prompt-edit-form').classList.remove('open');
  openModal('modal-prompts');
}

// Populate the per-prompt model dropdown (F6). Unavailable models are disabled;
// each option records whether its model supports web search.
function populateModelDropdown(selectedId) {
  const sel = $('form-model');
  sel.textContent = '';
  let matched = false;
  modelsCache.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    const providerLabel = m.provider === 'anthropic' ? 'Anthropic' : 'Custom';
    opt.textContent = `${m.label} · ${providerLabel}` + (m.available ? '' : ' (unavailable)');
    opt.disabled = !m.available;
    opt.dataset.webSearch = m.supports_web_search ? '1' : '';
    if (m.id === selectedId && m.available) { opt.selected = true; matched = true; }
    sel.appendChild(opt);
  });
  // If the stored model is unknown/unavailable, fall back to the first
  // available option so the control is never left on a disabled entry.
  if (!matched) {
    const firstAvail = modelsCache.find(m => m.available);
    if (firstAvail) sel.value = firstAvail.id;
  }
  updateWebSearchState();
}

function updateWebSearchState() {
  const sel = $('form-model');
  const opt = sel.selectedOptions[0];
  const supports = !!(opt && opt.dataset.webSearch === '1');
  const cb = $('form-web-search');
  cb.disabled = !supports;
  if (!supports) cb.checked = false;
  const hint = $('form-web-search-hint');
  hint.textContent = supports
    ? 'Attach the server-side web search tool to this prompt.'
    : 'Web search is only available on Anthropic models.';
}

$('form-model').addEventListener('change', updateWebSearchState);

async function refreshPromptEditor() {
  const data = await apiGet('/api/custom_prompts');
  if (!data) return;
  allPromptsCache = data.prompts || [];
  renderPromptTabs();
  renderPromptList(promptEditorCurrentTab);
}

function renderPromptTabs() {
  const tabs = $('ptabs');
  while (tabs.firstChild) tabs.removeChild(tabs.firstChild);
  const bucketsInUse = new Set(allPromptsCache.map(p => p.bucket));
  BUCKET_ORDER.forEach(bucket => {
    if (!bucketsInUse.has(bucket) && bucket !== 'custom') return;
    const btn = document.createElement('button');
    btn.className = 'ptab' + (bucket === promptEditorCurrentTab ? ' active' : '');
    btn.textContent = BUCKET_LABELS[bucket] || bucket;
    btn.addEventListener('click', () => {
      promptEditorCurrentTab = bucket;
      document.querySelectorAll('#ptabs .ptab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      renderPromptList(bucket);
    });
    tabs.appendChild(btn);
  });
}

function renderPromptList(bucket) {
  const container = $('prompt-list-items');
  while (container.firstChild) container.removeChild(container.firstChild);
  const prompts = allPromptsCache.filter(p => p.bucket === bucket);
  prompts.forEach(p => {
    const row = document.createElement('div');
    row.className = 'prompt-editor-row';
    const name = document.createElement('span');
    name.className = 'prompt-editor-row-name';
    name.textContent = p.button_text;
    const actions = document.createElement('div');
    const editBtn = document.createElement('button');
    editBtn.className = 'pact-btn';
    editBtn.textContent = 'Edit';
    editBtn.addEventListener('click', () => openPromptEditForm(p));
    actions.appendChild(editBtn);
    if (p.is_custom) {
      const delBtn = document.createElement('button');
      delBtn.className = 'pact-btn pact-btn-delete';
      delBtn.textContent = 'Delete';
      delBtn.addEventListener('click', () => deletePromptById(p.id));
      actions.appendChild(delBtn);
    }
    row.appendChild(name);
    row.appendChild(actions);
    container.appendChild(row);
  });
}

function openPromptEditForm(prompt) {
  promptEditorEditingId = prompt ? prompt.id : null;
  $('form-btn-label').value = prompt ? prompt.button_text : '';
  $('form-out-title').value = prompt ? prompt.output_title : '';
  $('form-template').value = prompt ? prompt.template : '';
  populateModelDropdown(prompt ? prompt.model : undefined);
  $('form-web-search').checked = !!(prompt && prompt.web_search);
  updateWebSearchState();
  $('btn-delete-prompt').style.display = prompt && prompt.is_custom ? 'inline-flex' : 'none';
  $('prompt-list-view').style.display = 'none';
  $('prompt-edit-form').classList.add('open');
}

function backToPromptList() {
  $('prompt-list-view').style.display = '';
  $('prompt-edit-form').classList.remove('open');
}

async function savePrompt() {
  const buttonText = $('form-btn-label').value.trim();
  const outputTitle = $('form-out-title').value.trim() || buttonText;
  const template = $('form-template').value.trim();
  if (!buttonText || !template) return;

  const model = $('form-model').value;
  const webSearch = $('form-web-search').checked;
  const payload = {
    button_text: buttonText,
    output_title: outputTitle,
    template,
    model,
    web_search: webSearch,
  };

  let resp;
  if (promptEditorEditingId) {
    resp = await apiPut('/api/custom_prompts/' + encodeURIComponent(promptEditorEditingId),
      payload);
  } else {
    resp = await apiPost('/api/custom_prompts', payload);
  }
  if (!resp || !resp.ok) { showToast('Failed to save prompt'); return; }

  backToPromptList();
  await refreshPromptEditor();
  await loadPrompts();
}

async function deletePromptById(promptId) {
  const resp = await apiDelete('/api/custom_prompts/' + encodeURIComponent(promptId));
  if (!resp || !resp.ok) { showToast('Failed to delete prompt'); return; }
  await refreshPromptEditor();
  await reloadCustomBucket();
}

$('btn-open-prompt-editor').addEventListener('click', () => openPromptEditor('custom'));
$('btn-new-prompt').addEventListener('click', () => openPromptEditForm(null));
$('prompt-form-back').addEventListener('click', backToPromptList);
$('prompt-form-cancel').addEventListener('click', backToPromptList);
$('btn-save-prompt').addEventListener('click', savePrompt);
$('btn-delete-prompt').addEventListener('click', () => {
  if (promptEditorEditingId) deletePromptById(promptEditorEditingId);
  backToPromptList();
});

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  const savedSettings = await apiGet('/api/settings');
  if (savedSettings) {
    applyBackground(savedSettings.background_style || 'default');
    autoHideExpired = !!savedSettings.auto_hide_expired;
  }
  await loadPrompts();
  loadPersona();
  connectSSE();
  await syncState();
  const saved = await apiGet('/api/saved_analyses');
  if (saved) handlers.saved_analyses(saved);
  updateFeedEmpty();
}

init();
