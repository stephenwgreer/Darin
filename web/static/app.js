/**
 * Darin Audio Assistant — vanilla JS frontend.
 *
 * Architecture:
 *   EventSource /api/events  ← SSE push from server
 *   fetch() POST /api/*      → REST actions to server
 *
 * All fetch() and EventSource URLs append ?token=${APP_TOKEN}.
 * APP_TOKEN is injected by the inline bootstrap script in index.html.
 *
 * innerHTML usage note: This app is localhost-only with a single trusted
 * user. innerHTML is used exclusively with server-controlled HTML from:
 *   1. STATIC_TEMPLATES — hardcoded Python strings in ui/stream_handlers/
 *   2. Regex-extracted <li> elements from Claude API streaming responses
 *   3. marked.parse() output from Claude API Q&A responses
 * None of these sources accept arbitrary user input, so XSS risk is minimal.
 */

'use strict';

// ── Helpers ────────────────────────────────────────────────────────────────

function apiUrl(path) {
  return `${path}?token=${window.APP_TOKEN}`;
}

async function apiPost(path, body) {
  const opts = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined && body !== null) opts.body = JSON.stringify(body);
  const resp = await fetch(apiUrl(path), opts);
  if (!resp.ok) console.error(`POST ${path} failed:`, resp.status);
  return resp;
}

async function apiGet(path) {
  const resp = await fetch(apiUrl(path));
  if (!resp.ok) { console.error(`GET ${path} failed:`, resp.status); return null; }
  return resp.json();
}

// ── DOM refs ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const el = {
  stateBadge:        $('state-badge'),
  btnStart:          $('btn-start-meeting'),
  btnStop:           $('btn-stop-meeting'),
  btnNew:            $('btn-new-meeting'),
  timerRow:          $('timer-row'),
  timerLabel:        $('timer-label'),
  captureStatus:     $('capture-status'),
  btnLast30:         $('btn-last-30'),
  btnLast60:         $('btn-last-60'),
  outputTitle:       $('output-title'),
  outputPanel:       $('output-panel'),
  outputMarkdown:    $('output-markdown'),
  salesPrompts:      $('sales-prompts'),
  midPrompts:        $('mid-meeting-prompts'),
  postPrompts:       $('post-meeting-prompts'),
  bucketSales:       $('bucket-sales'),
  bucketAnalysis:    $('bucket-analysis'),
  bucketReasoning:   $('bucket-reasoning'),
  bucketPostMeeting: $('bucket-post-meeting'),
  progressBar:       $('progress-bar'),
  rangeInputs:       $('range-inputs'),
  fromMinute:        $('from-minute'),
  toMinute:          $('to-minute'),
  btnCopyTranscript: $('btn-copy-transcript'),
  qaInput:           $('qa-input'),
  btnAsk:            $('btn-ask'),
  btnHistory:        $('btn-history'),
  btnSettings:       $('btn-settings'),
  btnOpenPromptEditor: $('btn-open-prompt-editor'),
  btnAddPrompt:      $('btn-add-prompt'),
  bucketCustom:      $('bucket-custom'),
  customPrompts:     $('custom-prompts'),
};

// ── State ──────────────────────────────────────────────────────────────────

let currentState = 'idle';
let isProcessing = false;
let outputIsMarkdown = false;
let rawMarkdownText = '';

// ── Timer display ──────────────────────────────────────────────────────────

function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

// ── State machine ──────────────────────────────────────────────────────────

function applyState(state) {
  currentState = state;

  el.stateBadge.className = 'badge badge-' + (state === 'post_meeting' ? 'post-meeting' : state);
  el.stateBadge.textContent =
    { idle: 'Idle', active: 'Recording', post_meeting: 'Post-Meeting' }[state] || state;

  el.btnStart.hidden = state !== 'idle';
  el.btnStop.hidden  = state !== 'active';
  el.btnNew.hidden   = state !== 'post_meeting';
  el.timerRow.hidden = state !== 'active';
  if (state !== 'active') el.timerLabel.textContent = '00:00:00';

  // Prompt sections: always visible, disabled when unavailable
  const midActive  = state === 'active';
  const postActive = state === 'post_meeting';

  el.salesPrompts.classList.toggle('section-disabled', !midActive);
  el.midPrompts.classList.toggle('section-disabled',   !midActive);
  el.postPrompts.classList.toggle('section-disabled',  !postActive);
  if (el.customPrompts) {
    el.customPrompts.classList.toggle('section-disabled', !midActive);
  }

  // Q&A available whenever there is a transcript (active or post-meeting)
  const hasTranscript = state === 'active' || state === 'post_meeting';
  el.qaInput.disabled = !hasTranscript;
  el.btnAsk.disabled  = !hasTranscript;

  if (state !== 'active') setProcessing(false);
}

// ── Processing guard ────────────────────────────────────────────────────────

function setProcessing(busy) {
  isProcessing = busy;
  document.querySelectorAll('.btn-prompt').forEach(b => { b.disabled = busy; });
  el.btnLast30.disabled = busy;
  el.btnLast60.disabled = busy;
}

// ── Prompt buttons ─────────────────────────────────────────────────────────

function buildPromptButton(cfg, isPost) {
  const btn = document.createElement('button');
  btn.className = 'btn btn-prompt';
  btn.dataset.promptId = cfg.id;

  const label = document.createTextNode(cfg.button_text);
  const check = document.createElement('span');
  check.className = 'badge-check';
  check.textContent = '✓';
  btn.appendChild(label);
  btn.appendChild(check);

  btn.addEventListener('click', async () => {
    if (isProcessing) return;
    setProcessing(true);
    el.outputTitle.textContent = cfg.output_title || 'Analysis Output';
    el.outputPanel.textContent = '';
    el.outputMarkdown.textContent = '';
    el.outputMarkdown.hidden = true;

    try {
      let resp;
      if (isPost) {
        const mode = document.querySelector('input[name="segment-mode"]:checked').value;
        const body = { prompt_id: cfg.id };
        if (mode === 'range') {
          const from = parseInt(el.fromMinute.value, 10);
          const to   = parseInt(el.toMinute.value, 10);
          if (!isNaN(from)) body.from_minute = from;
          if (!isNaN(to))   body.to_minute   = to;
        }
        resp = await apiPost('/api/run_post_meeting_prompt', body);
      } else {
        resp = await apiPost('/api/run_prompt', { prompt_id: cfg.id });
      }
      if (!resp.ok) setProcessing(false);
    } catch (e) {
      console.error('Prompt request failed:', e);
      setProcessing(false);
    }
  });

  return btn;
}

async function loadPrompts() {
  const data = await apiGet('/api/prompts');
  if (!data) return;

  (data.sales || []).forEach(cfg => {
    el.bucketSales.appendChild(buildPromptButton(cfg, false));
  });
  (data.mid_meeting || []).forEach(cfg => {
    el.bucketAnalysis.appendChild(buildPromptButton(cfg, false));
  });
  (data.reasoning || []).forEach(cfg => {
    el.bucketReasoning.appendChild(buildPromptButton(cfg, false));
  });
  (data.post_meeting || []).forEach(cfg => {
    el.bucketPostMeeting.appendChild(buildPromptButton(cfg, true));
  });
}

// ── SSE event handlers ─────────────────────────────────────────────────────

const handlers = {
  state_change(data) {
    applyState(data.state);
  },

  timer_tick(data) {
    el.timerLabel.textContent = formatElapsed(data.elapsed);
  },

  template_setup(data) {
    rawMarkdownText = '';
    outputIsMarkdown = false;
    el.outputTitle.textContent = data.output_title || 'Analysis Output';
    // scaffold_html is server-controlled HTML from STATIC_TEMPLATES (Python constants)
    el.outputPanel.innerHTML = data.scaffold_html || ''; // safe: server-only source
    el.outputMarkdown.textContent = '';
    el.outputMarkdown.hidden = true;
  },

  stream_item(data) {
    const list = document.getElementById(data.list_id);
    if (list) {
      // item_html is a regex-extracted <li> from Claude API — server-controlled
      const tmp = document.createElement('div');
      tmp.innerHTML = data.item_html; // safe: server-only source
      while (tmp.firstChild) list.appendChild(tmp.firstChild);
    }
  },

  stream_text(data) {
    el.outputMarkdown.hidden = false;
    if (outputIsMarkdown) {
      rawMarkdownText += data.chunk;
      el.outputMarkdown.innerHTML = marked.parse(rawMarkdownText); // safe: Claude API response via marked.parse()
    } else {
      el.outputMarkdown.textContent += data.chunk;
    }
  },

  first_line_value(data) {
    if (data.callback_method === 'set_overall_sentiment') {
      const sentEl = document.getElementById('overall-sentiment-value');
      if (sentEl) {
        sentEl.textContent = data.value;
        const colors = { Positive: '#22c55e', Negative: '#ef4444', Neutral: '#f59e0b' };
        sentEl.style.color = colors[data.value] || '';
      }
    }
  },

  section_header(data) {
    el.outputTitle.textContent = data.text;
  },

  processing_complete(data) {
    outputIsMarkdown = false;
    rawMarkdownText = '';
    setProcessing(false);
    if (data.error) {
      el.progressBar.textContent = `Error: ${data.error}`;
      el.progressBar.hidden = false;
    } else {
      el.progressBar.hidden = true;
    }
  },

  progress(data) {
    el.progressBar.textContent = data.message || '';
    el.progressBar.hidden = !data.message;
  },

  transcription_complete(data) {
    const wordCount = data.transcript ? data.transcript.split(/\s+/).filter(Boolean).length : 0;
    el.captureStatus.textContent = wordCount > 0
      ? `Transcribed (${wordCount} words)`
      : 'Transcription complete';
    setProcessing(false);
  },

  // Live transcript events — not displayed per design spec
  // ("Raw Deepgram transcript NEVER displayed")
  interim_transcript(_data) {},
  final_transcript(_data) {},

  saved_analyses(data) {
    const analyses = data.analyses || {};
    document.querySelectorAll('.btn-prompt[data-prompt-id]').forEach(btn => {
      btn.classList.toggle('done', !!analyses[btn.dataset.promptId]);
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

  es.onerror = () => {
    console.warn('SSE connection lost — retrying in 3 s');
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

// ── Capture buttons ────────────────────────────────────────────────────────

el.btnLast30.addEventListener('click', async () => {
  if (isProcessing) return;
  setProcessing(true);
  el.captureStatus.textContent = 'Capturing last 30 s…';
  await apiPost('/api/transcribe_last_n', { seconds: 30 });
});

el.btnLast60.addEventListener('click', async () => {
  if (isProcessing) return;
  setProcessing(true);
  el.captureStatus.textContent = 'Capturing last 60 s…';
  await apiPost('/api/transcribe_last_n', { seconds: 60 });
});

// ── Meeting control buttons ────────────────────────────────────────────────

el.btnStart.addEventListener('click', () => apiPost('/api/start_meeting'));
el.btnStop.addEventListener('click',  () => apiPost('/api/stop_meeting'));
el.btnNew.addEventListener('click',   () => apiPost('/api/reset'));

// ── Segment mode selector ──────────────────────────────────────────────────

document.querySelectorAll('input[name="segment-mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    el.rangeInputs.hidden = radio.value !== 'range';
  });
});

// ── Q&A ────────────────────────────────────────────────────────────────

async function submitQuestion() {
  const question = el.qaInput.value.trim();
  if (!question || isProcessing) return;
  el.qaInput.value = '';
  rawMarkdownText = '';
  outputIsMarkdown = true;
  setProcessing(true);
  el.outputTitle.textContent = 'Answer';
  el.outputPanel.textContent = '';
  el.outputMarkdown.textContent = '';
  el.outputMarkdown.hidden = false;
  try {
    const resp = await apiPost('/api/ask', { question });
    if (!resp.ok) setProcessing(false);
  } catch (e) {
    console.error('Ask failed:', e);
    setProcessing(false);
  }
}

el.btnAsk.addEventListener('click', submitQuestion);
el.qaInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitQuestion(); });

// ── Copy transcript ────────────────────────────────────────────────────────

el.btnCopyTranscript.addEventListener('click', async () => {
  const data = await apiGet('/api/transcript');
  if (data && data.transcript) {
    await navigator.clipboard.writeText(data.transcript);
    el.btnCopyTranscript.textContent = 'Copied!';
    setTimeout(() => { el.btnCopyTranscript.textContent = 'Copy Transcript'; }, 2000);
  }
});

// ── Modal helpers ──────────────────────────────────────────────────────────

function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// Wire all [data-close] buttons
document.querySelectorAll('[data-close]').forEach(btn => {
  btn.addEventListener('click', () => closeModal(btn.dataset.close));
});

// Close on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeModal(overlay.id);
  });
});

// ── Settings dialog ────────────────────────────────────────────────────────

async function openSettings() {
  const data = await apiGet('/api/settings');
  if (data) {
    document.getElementById('settings-path-input').value = data.storage_path || '';
  }
  openModal('modal-settings');
}

document.getElementById('btn-settings').addEventListener('click', openSettings);

document.getElementById('btn-browse-folder').addEventListener('click', async () => {
  const resp = await apiPost('/api/pick_folder', {});
  if (resp && resp.ok) {
    const data = await resp.json();
    if (data && data.path) {
      document.getElementById('settings-path-input').value = data.path;
    }
  }
});

document.getElementById('btn-save-settings').addEventListener('click', async () => {
  const path = document.getElementById('settings-path-input').value.trim();
  if (!path) return;
  await apiPost('/api/settings', { storage_path: path });
  closeModal('modal-settings');
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
  document.getElementById('history-list-view').style.display = '';
  document.getElementById('history-transcript-view').style.display = 'none';
  openModal('modal-history');
  await refreshMeetingList();
}

async function refreshMeetingList() {
  const data = await apiGet('/api/meetings');
  const container = document.getElementById('meeting-list');
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
    arrow.style.color = 'var(--text-muted)';

    row.appendChild(info);
    row.appendChild(dur);
    row.appendChild(arrow);

    row.addEventListener('click', () => openMeetingTranscript(m.id));
    container.appendChild(row);
  });
}

async function openMeetingTranscript(meetingId) {
  historyCurrentMeetingId = meetingId;
  const data = await apiGet('/api/meetings/' + meetingId + '/transcript');
  if (!data) return;

  document.getElementById('history-list-view').style.display = 'none';
  document.getElementById('history-transcript-view').style.display = '';

  document.getElementById('tx-title').textContent = data.title
    ? formatMeetingDate(data.start_time) + ' — ' + data.title
    : formatMeetingDate(data.start_time);

  const dur = data.end_time
    ? formatDuration(Math.floor((new Date(data.end_time) - new Date(data.start_time)) / 1000))
    : '';
  document.getElementById('tx-meta').textContent = dur;

  const body = document.getElementById('tx-body');
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

document.getElementById('tx-back-btn').addEventListener('click', () => {
  historyCurrentMeetingId = null;
  document.getElementById('history-list-view').style.display = '';
  document.getElementById('history-transcript-view').style.display = 'none';
});

document.getElementById('btn-history').addEventListener('click', openHistory);

// Historical Q&A
async function submitHistoricalQuestion() {
  const question = document.getElementById('tx-ask-input').value.trim();
  if (!question || !historyCurrentMeetingId) return;
  document.getElementById('tx-ask-input').value = '';
  closeModal('modal-history');
  try {
    await apiPost('/api/meetings/' + historyCurrentMeetingId + '/ask', { question });
  } catch (e) {
    console.error('Historical ask failed:', e);
  }
}

document.getElementById('tx-ask-btn').addEventListener('click', submitHistoricalQuestion);
document.getElementById('tx-ask-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitHistoricalQuestion();
});

// ── Prompt editor ──────────────────────────────────────────────────────────

const BUCKET_LABELS = {
  sales: 'Sales',
  mid_meeting: 'Meeting Analysis',
  reasoning: 'Reasoning',
  post_meeting: 'Post-Meeting',
  custom: 'Custom',
};
const BUCKET_ORDER = ['sales', 'mid_meeting', 'reasoning', 'post_meeting', 'custom'];

let allPromptsCache = [];
let promptEditorCurrentTab = 'sales';
let promptEditorEditingId = null;

async function openPromptEditor(defaultTab) {
  promptEditorCurrentTab = defaultTab || 'sales';
  promptEditorEditingId = null;
  await refreshPromptEditor();
  document.getElementById('prompt-list-view').style.display = '';
  document.getElementById('prompt-edit-form').classList.remove('open');
  openModal('modal-prompts');
}

async function refreshPromptEditor() {
  const data = await apiGet('/api/custom_prompts');
  if (!data) return;
  allPromptsCache = data.prompts || [];
  renderPromptTabs();
  renderPromptList(promptEditorCurrentTab);
}

function renderPromptTabs() {
  const tabs = document.getElementById('ptabs');
  while (tabs.firstChild) tabs.removeChild(tabs.firstChild);
  const bucketsInUse = new Set(allPromptsCache.map(p => p.bucket));
  BUCKET_ORDER.forEach(bucket => {
    if (!bucketsInUse.has(bucket) && bucket !== 'custom') return;
    const btn = document.createElement('button');
    btn.className = 'ptab' + (bucket === promptEditorCurrentTab ? ' active' : '');
    btn.textContent = BUCKET_LABELS[bucket] || bucket;
    btn.addEventListener('click', () => {
      promptEditorCurrentTab = bucket;
      document.querySelectorAll('.ptab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      renderPromptList(bucket);
    });
    tabs.appendChild(btn);
  });
}

function renderPromptList(bucket) {
  const container = document.getElementById('prompt-list-items');
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
    const delBtn = document.createElement('button');
    delBtn.className = 'pact-btn pact-btn-delete';
    delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', () => deletePromptById(p.id));
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    row.appendChild(name);
    row.appendChild(actions);
    container.appendChild(row);
  });
}

function openPromptEditForm(prompt) {
  promptEditorEditingId = prompt ? prompt.id : null;
  document.getElementById('form-btn-label').value = prompt ? prompt.button_text : '';
  document.getElementById('form-out-title').value = prompt ? prompt.output_title : '';
  document.getElementById('form-template').value = prompt ? prompt.template : '';
  document.getElementById('btn-delete-prompt').style.display = prompt ? 'inline-flex' : 'none';
  document.getElementById('prompt-list-view').style.display = 'none';
  document.getElementById('prompt-edit-form').classList.add('open');
}

function backToPromptList() {
  document.getElementById('prompt-list-view').style.display = '';
  document.getElementById('prompt-edit-form').classList.remove('open');
}

async function savePrompt() {
  const buttonText = document.getElementById('form-btn-label').value.trim();
  const outputTitle = document.getElementById('form-out-title').value.trim() || buttonText;
  const template = document.getElementById('form-template').value.trim();
  if (!buttonText || !template) return;

  if (promptEditorEditingId) {
    await fetch(apiUrl('/api/custom_prompts/' + promptEditorEditingId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ button_text: buttonText, output_title: outputTitle, template }),
    });
  } else {
    await apiPost('/api/custom_prompts', {
      button_text: buttonText, output_title: outputTitle, template
    });
  }

  backToPromptList();
  await refreshPromptEditor();
  await reloadCustomBucket();
}

async function deletePromptById(promptId) {
  await fetch(apiUrl('/api/custom_prompts/' + promptId), { method: 'DELETE' });
  await refreshPromptEditor();
  await reloadCustomBucket();
}

document.getElementById('btn-open-prompt-editor').addEventListener('click', () => openPromptEditor('custom'));
document.getElementById('btn-add-prompt').addEventListener('click', () => {
  openPromptEditor('custom');
  openPromptEditForm(null);
});
document.getElementById('btn-new-prompt').addEventListener('click', () => openPromptEditForm(null));
document.getElementById('prompt-form-back').addEventListener('click', backToPromptList);
document.getElementById('prompt-form-cancel').addEventListener('click', backToPromptList);
document.getElementById('btn-save-prompt').addEventListener('click', savePrompt);
document.getElementById('btn-delete-prompt').addEventListener('click', () => {
  if (promptEditorEditingId) deletePromptById(promptEditorEditingId);
  backToPromptList();
});

// Wire bucket header edit icons (if any have data-bucket attribute)
document.querySelectorAll('.bucket-edit-icon').forEach(btn => {
  btn.addEventListener('click', () => {
    const bucket = btn.dataset.bucket || 'custom';
    openPromptEditor(bucket);
  });
});

// ── Custom bucket prompt buttons ───────────────────────────────────────────

async function reloadCustomBucket() {
  const data = await apiGet('/api/prompts');
  if (!data) return;

  const bucket = document.getElementById('bucket-custom');
  const addBtn = document.getElementById('btn-add-prompt');
  while (bucket.firstChild) bucket.removeChild(bucket.firstChild);

  (data.custom || []).forEach(cfg => {
    bucket.appendChild(buildPromptButton(cfg, false));
  });

  bucket.appendChild(addBtn);
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  await loadPrompts();
  await reloadCustomBucket();
  connectSSE();
  const state = await apiGet('/api/state');
  if (state) {
    applyState(state.state);
    if (state.elapsed) el.timerLabel.textContent = formatElapsed(state.elapsed);
  }
}

init();
