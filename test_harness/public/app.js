/**
 * Darin Test Harness — client-side logic
 * All 18 prompts embedded; no Python import needed.
 * Uses DOM construction (no innerHTML) to avoid XSS surface.
 */

// ─── Prompt registry (mirrors prompts/registry.py + templates) ──────────────

const PROMPTS = [
  // ── Bucket 1: Mid-Meeting Analysis (9 prompts) ──────────────────────────
  {
    id: "sentiment_analysis",
    label: "Sentiment Analysis",
    output_title: "Sentiment Analysis",
    bucket: "mid_meeting",
    template: `Analyze the sentiment and emotional tone of this conversation transcript.

First, return ONLY the overall sentiment value (Positive, Negative, or Neutral) on a single line.
Then, on subsequent lines, return ONLY the 5 key emotional moments as HTML list items, each formatted exactly as:
<li class="insight-item">[Key moment description with emotional context]</li>

Example Output:
Neutral
<li class="insight-item">[First key moment with emotional context]</li>
<li class="insight-item">[Second key moment with emotional context]</li>
... (up to 5 items)

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}`,
  },
  {
    id: "practitioner_insights",
    label: "Practitioner Insights",
    output_title: "Banking Practitioner Insights",
    bucket: "mid_meeting",
    template: `Analyze the provided transcript, focusing on the most recent discussion if possible.
Identify the single most relevant banking or financial services topic being discussed.
Then, provide 5 practitioner-level insights related to that specific topic.

Return ONLY the 5 insights as HTML list items, each formatted exactly as:
<li class="insight-item">[Insight about the identified topic]</li>

Example Output:
<li class="insight-item">[Insight 1 about the topic]</li>
<li class="insight-item">[Insight 2 about the topic]</li>
...

Do not include the topic itself, any headers, wrappers, or other text.

Transcript to analyze:
{transcript}`,
  },
  {
    id: "follow_up_questions",
    label: "Follow-up Questions",
    output_title: "Follow-up Questions",
    bucket: "mid_meeting",
    template: `Based on the following transcript, generate 5 insightful follow-up questions that would
help clarify or expand on the topics discussed.

The format for the response should be exactly as shown below. ONLY include the list items
with the proper HTML tags. DO NOT include any outer divs, headers, or wrappers:

<li class="insight-item">Question 1 about a specific topic from the transcript</li>
<li class="insight-item">Question 2 about another topic from the transcript</li>
<li class="insight-item">Question 3 about an important detail that needs clarification</li>
<li class="insight-item">Question 4 about implications or next steps</li>
<li class="insight-item">Question 5 about relevant context or background information</li>

Each question should be specific, thoughtful, and directly related to the content of the transcript.
Generate the questions one at a time, and make sure each one addresses a different aspect of the conversation.

Transcript:
{transcript}`,
  },
  {
    id: "gaps_reasoning",
    label: "Gaps in Reasoning",
    output_title: "Gaps in Reasoning",
    bucket: "mid_meeting",
    template: `You are analyzing a transcript to identify thinking patterns and gaps in reasoning.
Task: Review the following transcript and identify:
1. Core thinking patterns present (as a single summary point).
2. Specific gaps in the reasoning (as bullet points).
3. Recommendations to make the analysis more complete (as bullet points).

Return ONLY the identified points as HTML list items, formatted exactly as follows:
- For Core Thinking: <li class="core-thinking">[Single summary of core thinking]</li>
- For Gaps: <li class="gap-item">[Gap 1 description]</li> (multiple items)
- For Recommendations: <li class="recommendation-item">[Recommendation 1]</li> (multiple items)

Example Output:
<li class="core-thinking">The core thinking focused heavily on feature conversion feasibility.</li>
<li class="gap-item">Gap 1: Consideration of data scaling issues was missing.</li>
<li class="gap-item">Gap 2: Alternative modeling approaches weren't explored.</li>
<li class="recommendation-item">Recommendation 1: Evaluate data volume impact.</li>
<li class="recommendation-item">Recommendation 2: Benchmark against simpler models.</li>

Do not include the headings (CORE_THINKING, GAPS, RECOMMENDATIONS) or any other text, wrappers, or formatting.

Transcript:
{transcript}`,
  },
  {
    id: "brainstorming",
    label: "Brainstorming",
    output_title: "Brainstorm Questions",
    bucket: "mid_meeting",
    template: `Analyze the following transcript and generate thought-provoking questions that challenge assumptions and encourage new perspectives.
Task: Review the transcript and create:
1. Questions that challenge core assumptions.
2. Alternatives that reframe the problem.
3. Provocative ideas to expand thinking.

Return ONLY the generated points as HTML list items, formatted exactly as follows:
- For Challenge Questions: <li class="challenge-question">[Specific question]</li> (multiple items)
- For Alternative Frames: <li class="alternative-frame">[Alternative view]</li> (multiple items)
- For Provocative Ideas: <li class="provocative-idea">[Unexpected approach]</li> (multiple items)

Example Output:
<li class="challenge-question">What if the core assumption about X is wrong?</li>
<li class="challenge-question">How might Y be influencing this outcome?</li>
<li class="alternative-frame">Could we view this not as a problem, but an opportunity?</li>
<li class="provocative-idea">What if we applied principles from Z field here?</li>

Do not include the headings or any other text, wrappers, or formatting.
Keep questions constructive and focused on generating new insights.

Transcript:
{transcript}`,
  },
  {
    id: "company_fit",
    label: "SAS Viya Alignment",
    output_title: "SAS Viya Alignment",
    bucket: "mid_meeting",
    template: `Analyze the following call transcript and identify opportunities to position SAS Viya capabilities as solutions.
Task: Extract key topics, connect them to relevant SAS Viya features, and identify missing considerations.

Return ONLY the generated points as HTML list items, formatted exactly as follows:
- For Key Topics: <li class="key-topic">[Topic 1 from conversation]</li> (multiple items)
- For SAS Viya Connections: <li class="viya-connection">[Topic X]: [How SAS Viya addresses this]</li> (multiple items)
- For Missing Considerations: <li class="missing-consideration">[Additional capability/opportunity]</li> (multiple items)

Do not include the headings or any other text, wrappers, or formatting.
Be specific about how SAS Viya's capabilities address expressed needs.

Transcript:
{transcript}`,
  },
  {
    id: "fact_check",
    label: "Fact Check",
    output_title: "Fact Check Analysis",
    bucket: "mid_meeting",
    template: `Identify factual claims in the following transcript and evaluate their accuracy.
Rate each claim's accuracy on a scale of 1-5 where:
1 = Not accurate
2 = Mostly inaccurate
3 = Partially accurate
4 = Mostly accurate
5 = Totally accurate

Return ONLY the analysis for each claim (up to 5) as HTML list items, formatted exactly as:
<li class="fact-check-item">
    <strong>Claim X:</strong> "[Direct quote]"<br>
    <strong>Accuracy:</strong> [1-5]/5<br>
    <strong>Correction:</strong> [Accurate information if score < 5, otherwise "N/A"]
</li>

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}`,
  },
  {
    id: "answer_question",
    label: "Answer Question",
    output_title: "Answer Question",
    bucket: "mid_meeting",
    template: `Analyze the provided transcript, paying close attention to the END of the text.
Identify the single LAST question asked by any speaker in the transcript.

If a question is found, generate:
1. 3-5 concise, relevant points for the ANSWER.
2. Exactly 2 points explaining the RATIONALE behind the answer.
3. 2-3 concrete EXAMPLES illustrating the answer, if applicable.

Return ONLY the generated points as HTML list items:
- For Answer points: <li class="answer-item">[Suggested answer point]</li>
- For Rationale points: <li class="rationale-item">[Rationale point]</li>
- For Example points: <li class="example-item">[Concrete example or 'N/A']</li>

If no question is found near the end, return ONLY:
<li class="answer-item">No clear question identified at the end of the transcript.</li>

Do not include the identified question itself, any headers, wrappers, or other text.

Transcript:
{transcript}`,
  },
  {
    id: "analyze_statement",
    label: "Analyze Statement",
    output_title: "Statement Analysis",
    bucket: "mid_meeting",
    template: `Analyze the key claim or statement in the following transcript.

Return ONLY the analysis as HTML list items:
- For the main claim: <li class="statement-claim">[The core claim or statement being analyzed]</li>
- For strengths: <li class="statement-strength">[Strength of the claim]</li>
- For weaknesses: <li class="statement-weakness">[Weakness or vulnerability in the claim]</li>
- For assumptions: <li class="statement-assumption">[Underlying assumption being made]</li>
- For what is unsaid: <li class="statement-unsaid">[What is being omitted or left unstated]</li>

Generate 1 claim item, 2-3 strength items, 2-3 weakness items, 2-3 assumption items, and 1-2 unsaid items.

Do not include headings, wrappers, or any other text outside the list items.

Transcript:
{transcript}`,
  },

  // ── Bucket 2: Reasoning Frameworks (5 prompts) ──────────────────────────
  {
    id: "scqa",
    label: "SCQA Framework",
    output_title: "SCQA Framework",
    bucket: "reasoning",
    template: `Act as an elite management consultant analyzing a transcript using the SCQA framework.

Analyze the transcript and generate ONLY HTML list items based on the sections below:

1. SITUATION: <li class="scqa-situation">[Summary of Situation]</li>
2. COMPLICATION: <li class="scqa-complication">[Summary of Complication]</li>
3. QUESTION: <li class="scqa-question">[The single core Question]</li>
4. ANSWER: <li class="scqa-answer">[Answer point or Key Message]</li>
5. CRITICAL ASSESSMENT: <li class="scqa-assessment">[Assessment point]</li>
6. IMPLEMENTATION ROADMAP: <li class="scqa-roadmap">[Roadmap/Next Step item]</li>

Important: Return ONLY the HTML list items. Do not include headings, wrappers, or any other text outside the list items.

Transcript to Analyze:

---
{transcript}
---

Begin Analysis (Return only list items below):`,
  },
  {
    id: "issue_tree",
    label: "Issue Tree Logic",
    output_title: "Issue Tree Logic",
    bucket: "reasoning",
    template: `Act as a Management Consultant specializing in Structured Problem Solving.

Analyze the following transcript using Issue Tree / Logic Tree principles.

Generate ONLY HTML list items based on the sections below:

1. Core Problem: <li class="core-problem">[Your summary of the core problem/objective]</li> (one item)
2. Logic Tree Components: <li class="logic-tree-component">[Component/Driver Name/Sub-Question]</li> (multiple)
3. Evaluation:
   - MECE: <li class="evaluation-mece">[MECE Assessment point]</li>
   - Assumptions: <li class="evaluation-assumption">[Identified Assumption]</li>
   - Logic: <li class="evaluation-logic">[Assessment of logical link]</li>
   - Missing data: <li class="evaluation-data">[Observation about missing data/evidence]</li>
4. Challenge and Reframe:
   - Weaknesses: <li class="challenge-weakness">[Identified Weakness]</li>
   - Critical questions (2-3): <li class="challenge-question">[Critical Unasked Question]</li>
   - Alternative frames: <li class="challenge-reframe">[Alternative Frame/Structure Suggestion]</li>

Important: Return ONLY the HTML list items. Do not include headings, wrappers, or any other text outside the list items.

Transcript to Analyze:

---
{transcript}
---

Begin Analysis (Return only list items below):`,
  },
  {
    id: "first_principles",
    label: "First Principles",
    output_title: "First Principles",
    bucket: "reasoning",
    template: `Act as a strategic advisor skilled in First Principles Thinking.

Analyze the transcript and generate ONLY HTML list items:

1. Conventional thinking: <li class="fp-conventional">[Conventional Thinking/Assumption Point]</li>
2. Fundamentals: <li class="fp-fundamental">[Fundamental Truth/First Principle]</li>
3. Assumptions challenged: <li class="fp-assumption">[Assumption Challenged]: How do we know this is true? / Evidence: [Present/Absent]</li>
4. Rebuilt approaches: <li class="fp-rebuild">[Rebuilt Approach/Solution Point]</li>
5. Novel insights: <li class="fp-insight">[Novel Insight/Different Conclusion]</li>
6. Implementation: <li class="fp-implementation">[Implementation Step/Experiment]</li>
7. Metacognitive: <li class="fp-metacognitive">[Metacognitive Observation/Bias Identified]</li>

Important: Return ONLY the HTML list items. Do not include headings, wrappers, or any other text.

Transcript to Analyze:

---
{transcript}
---

Begin Analysis (Return only list items below):`,
  },
  {
    id: "hypothesis_driven",
    label: "Hypothesis Thinking",
    output_title: "Hypothesis Thinking",
    bucket: "reasoning",
    template: `Act as an analytical strategist specializing in hypothesis-driven problem solving.

Analyze the transcript and generate ONLY HTML list items:

1. Problem statement (one item): <li class="hypothesis-problem">[Refined Problem Statement/Question]</li>
2. Hypotheses (3-5): <li class="hypothesis-hypothesis">Hypothesis X: [Hypothesis statement]</li>
3. Evidence:
   - Supporting: <li class="hypothesis-evidence-support">[Hypothesis X] Supporting: [Evidence]</li>
   - Contradicting: <li class="hypothesis-evidence-contradict">[Hypothesis X] Contradicting: [Evidence]</li>
   - Missing: <li class="hypothesis-evidence-missing">[Hypothesis X] Missing Info: [Critical missing information]</li>
4. Prioritization: <li class="hypothesis-priority">[Rank]. [Hypothesis X]: [Brief rationale]</li>
5. Testing plan: <li class="hypothesis-testing">[Hypothesis X] Test: [Approach, Data, Method]</li>
6. Decision framework: <li class="hypothesis-decision">[Decision criterion/threshold and related action]</li>
7. Assessment: <li class="hypothesis-assessment">[Assessment point]</li>

Important: Return ONLY the HTML list items. Do not include headings, wrappers, or any other text.

Transcript to Analyze:

---
{transcript}
---

Begin Analysis (Return only list items below):`,
  },
  {
    id: "reframing",
    label: "Reframing",
    output_title: "Reframing",
    bucket: "reasoning",
    template: `Act as an expert in clear, structured communication and strategic thinking.

Analyze the core topic or problem discussed in the transcript and reframe it in a clearer, more actionable way.

Return ONLY HTML list items:
- Reframed statement (one item): <li class="reframing-statement">[Your clear, reframed statement of the core issue/idea]</li>
- Supporting points (3-5 items): <li class="reframing-point">[Supporting point for the reframed idea]</li>

Example Output:
<li class="reframing-statement">The core challenge isn't if we can migrate the feature, but how to do so while minimizing user disruption during Q3.</li>
<li class="reframing-point">Focus on identifying the critical user paths affected.</li>
<li class="reframing-point">Prioritize a phased rollout strategy.</li>
<li class="reframing-point">Define clear communication plans for each phase.</li>

Important: Return ONLY the HTML list items. Do not include headings, wrappers, or any other text.

Transcript to Analyze:

---
{transcript}
---

Begin Analysis (Return only list items below):`,
  },

  // ── Bucket 3: Post-Meeting Analysis (4 prompts) ──────────────────────────
  {
    id: "meeting_summary",
    label: "Meeting Summary",
    output_title: "Meeting Summary",
    bucket: "post_meeting",
    template: `Create a concise summary of the following meeting transcript.
Include key decisions made, important discussion points, and overall meeting purpose.

Return ONLY the summary points as HTML list items, each formatted exactly as:
<li class="insight-item">[Summary point]</li>

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}`,
  },
  {
    id: "topic_summary",
    label: "Extract Topics",
    output_title: "Key Topics",
    bucket: "post_meeting",
    template: `Analyze the following transcript from a work call and identify the three main topics discussed.
Focus on topics that are most relevant to banking and financial services.

Return ONLY the 3 topics as HTML list items, each formatted exactly as:
<li class="insight-item">[Topic name]</li>

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}`,
  },
  {
    id: "action_items",
    label: "Action Items",
    output_title: "Action Items",
    bucket: "post_meeting",
    template: `Extract all action items, commitments, and next steps from the following meeting transcript.

Return ONLY the action items as HTML list items:
<li class="action-item"><strong>[Owner if stated, otherwise "Unassigned"]:</strong> [Task description] [Due date if mentioned]</li>

If no clear action items are present, return:
<li class="action-item">No explicit action items identified in this transcript.</li>

Do not include any other text, wrappers, headers, or formatting.

Meeting transcript:
{transcript}`,
  },
  {
    id: "key_decisions",
    label: "Key Decisions",
    output_title: "Key Decisions",
    bucket: "post_meeting",
    template: `Extract all decisions from the following meeting transcript — made and still needed.

Return ONLY the decisions as HTML list items:
- Decision made: <li class="decision-made"><strong>Decided:</strong> [Decision summary] — [Brief context]</li>
- Decision needed: <li class="decision-needed"><strong>Open:</strong> [What needs to be decided] — [Key open questions]</li>

If no decisions are found, return:
<li class="decision-made">No explicit decisions identified in this transcript.</li>

Do not include any other text, wrappers, headers, or formatting.

Meeting transcript:
{transcript}`,
  },
];

// ─── State ───────────────────────────────────────────────────────────────────

let activePromptId = null;
let abortController = null;

// ─── Init ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  renderBuckets();
});

function renderBuckets() {
  const buckets = ["mid_meeting", "reasoning", "post_meeting"];
  for (const bucket of buckets) {
    const container = document.getElementById("bucket-" + bucket);
    if (!container) continue;
    const prompts = PROMPTS.filter(function(p) { return p.bucket === bucket; });
    // Build buttons via DOM — no innerHTML
    container.textContent = "";
    for (const p of prompts) {
      const btn = document.createElement("button");
      btn.className = "test-btn btn-" + p.bucket;
      btn.id = "btn-" + p.id;
      btn.title = p.output_title;
      btn.textContent = p.label;
      btn.addEventListener("click", function() { runPrompt(p.id); });
      container.appendChild(btn);
    }
  }
}

// ─── Load transcript ──────────────────────────────────────────────────────────

async function loadTranscript() {
  const btn = document.getElementById("load-btn");
  btn.disabled = true;
  btn.textContent = "Loading\u2026";
  try {
    const res = await fetch("/api/transcript");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const ta = document.getElementById("transcript-area");
    ta.value = data.transcript;
    updateCharCount();
    setStatus("connected", "transcript loaded");
  } catch (err) {
    setStatus("error", "load failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Load Transcript";
  }
}

function updateCharCount() {
  const ta = document.getElementById("transcript-area");
  document.getElementById("transcript-chars").textContent =
    ta.value.length.toLocaleString() + " chars";
}

// ─── Run prompt ───────────────────────────────────────────────────────────────

async function runPrompt(promptId) {
  const prompt = PROMPTS.find(function(p) { return p.id === promptId; });
  if (!prompt) return;

  const transcript = document.getElementById("transcript-area").value.trim();
  if (!transcript) {
    setStatus("error", "no transcript");
    const outputEl = document.getElementById("output-area");
    outputEl.className = "test-output error";
    outputEl.textContent = "No transcript loaded. Click \u2018Load Transcript\u2019 first.";
    document.getElementById("output-status").textContent = "";
    return;
  }

  // Cancel any in-flight request
  if (abortController) {
    abortController.abort();
  }
  abortController = new AbortController();

  // Update UI state
  setActiveButton(promptId);
  document.getElementById("output-title").textContent = prompt.output_title;
  document.getElementById("copy-btn").style.display = "none";
  setStatus("analyzing", "analyzing\u2026");

  const outputEl = document.getElementById("output-area");
  outputEl.className = "test-output loading";
  outputEl.textContent = "Analyzing\u2026";

  const startMs = Date.now();
  let fullText = "";
  let inputTokens = 0;
  let outputTokens = 0;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript: transcript,
        prompt_template: prompt.template,
      }),
      signal: abortController.signal,
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(err);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    outputEl.className = "test-output";
    outputEl.textContent = "";

    let buffer = "";

    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;

      buffer += decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") continue;
        try {
          const event = JSON.parse(data);
          if (event.type === "content_block_delta" && event.delta && event.delta.type === "text_delta") {
            fullText += event.delta.text;
            outputEl.textContent = fullText;
            outputEl.scrollTop = outputEl.scrollHeight;
            const elapsed = Date.now() - startMs;
            document.getElementById("output-status").textContent = "Analyzing\u2026 (" + elapsed + "ms)";
          } else if (event.type === "message_delta" && event.usage) {
            outputTokens = event.usage.output_tokens || outputTokens;
          } else if (event.type === "message_start" && event.message && event.message.usage) {
            inputTokens = event.message.usage.input_tokens || inputTokens;
          }
        } catch (e) {
          // non-JSON SSE line — skip
        }
      }
    }

    const elapsed = Date.now() - startMs;
    let statusText = "Done \u2014 " + elapsed + "ms";
    if (inputTokens || outputTokens) {
      statusText += " \u00b7 " + inputTokens.toLocaleString() + " in / " + outputTokens.toLocaleString() + " out";
    }
    document.getElementById("output-status").textContent = statusText;
    document.getElementById("copy-btn").style.display = "";
    setStatus("connected", "done");
  } catch (err) {
    if (err.name === "AbortError") {
      setStatus("connected", "cancelled");
      document.getElementById("output-status").textContent = "Cancelled";
      return;
    }
    outputEl.className = "test-output error";
    outputEl.textContent = "Error: " + err.message;
    document.getElementById("output-status").textContent = "Error";
    setStatus("error", err.message);
  }
}

// ─── Copy output ──────────────────────────────────────────────────────────────

function copyOutput() {
  const text = document.getElementById("output-area").textContent;
  navigator.clipboard.writeText(text).then(function() {
    const btn = document.getElementById("copy-btn");
    const prev = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(function() { btn.textContent = prev; }, 1500);
  });
}

// ─── UI helpers ───────────────────────────────────────────────────────────────

function setStatus(state, text) {
  const dot = document.getElementById("status-dot");
  dot.className = "status-dot " + state;
  document.getElementById("status-text").textContent = text;
}

function setActiveButton(promptId) {
  document.querySelectorAll(".test-btn[id^='btn-']").forEach(function(b) {
    b.classList.remove("active");
  });
  const btn = document.getElementById("btn-" + promptId);
  if (btn) btn.classList.add("active");
  activePromptId = promptId;
}
