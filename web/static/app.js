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
 * Neither source accepts arbitrary user input, so XSS risk is minimal.
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
};

// ── State ──────────────────────────────────────────────────────────────────

let currentState = 'idle';
let isProcessing = false;

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
    el.outputMarkdown.textContent += data.chunk;
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

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  await loadPrompts();
  connectSSE();
  const state = await apiGet('/api/state');
  if (state) {
    applyState(state.state);
    if (state.elapsed) el.timerLabel.textContent = formatElapsed(state.elapsed);
  }
}

init();
