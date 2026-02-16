# Prompts related to structured logic and problem solving frameworks

PROBLEM_SOLVING_PROMPT = """
**Act as a Management Consultant specializing in Structured Problem Solving.**

Your task is to rigorously analyze the following transcript. Your goal is to deconstruct the core topic or problem being discussed, challenge the underlying thinking, identify gaps, and reframe the issue to facilitate better problem-solving, 
using the principles of an Issue Tree / Logic Tree.

**Instructions & Output Format:**

Analyze the transcript and generate ONLY HTML list items (`<li>`) based on the sections below. Assign the specified CSS class to each list item.

1.  **Core Problem/Objective:**
    *   Read the transcript and determine the central question, problem, goal, or decision being discussed. State this clearly at the beginning.
    *   Format: `<li class="core-problem">[Your summary of the core problem/objective]</li>` (Should be just one item)

2.  **Logic Tree Components:**
    *   Break down the core problem into its primary components/drivers based *only* on the transcript.
    *   Format: `<li class="logic-tree-component">[Component/Driver Name/Sub-Question]</li>` (Generate multiple items as needed, use text indentation like '- ' or '  - ' within the item if hierarchy needs to be shown)

3.  **Evaluation:**
    *   Assess MECE (Mutually Exclusive, Collectively Exhaustive) based on transcript content. Note gaps/overlaps.
        *   Format: `<li class="evaluation-mece">[MECE Assessment point]</li>` (Multiple items possible)
    *   Identify key stated or unstated assumptions.
        *   Format: `<li class="evaluation-assumption">[Identified Assumption]</li>` (Multiple items possible)
    *   Assess logical connections discussed.
        *   Format: `<li class="evaluation-logic">[Assessment of logical link]</li>` (Multiple items possible)
    *   Note where claims lack supporting evidence in the transcript.
        *   Format: `<li class="evaluation-data">[Observation about missing data/evidence]</li>` (Multiple items possible)

4.  **Challenge & Reframe:**
    *   Highlight the weakest points in the logic or structure presented in the transcript.
        *   Format: `<li class="challenge-weakness">[Identified Weakness]</li>` (Multiple items possible)
    *  Identify 2-3 critical questions that were *not* asked or adequately addressed in the discussion but are essential for robust problem-solving.
        *   Format: `<li class="challenge-question">[Critical Unasked Question]</li>` (Generate 2-3 items)
    *   Suggest potential alternative ways to frame the core problem or structure the analysis that might lead to different insights or solutions..
        *   Format: `<li class="challenge-reframe">[Alternative Frame/Structure Suggestion]</li>` (Multiple items possible)

**Important:** Return *ONLY* the HTML `<li>` items with the specified classes. Do not include headings, explanations, wrappers (`<ul>`, `<div>`), or any other text outside the `<li>` tags.

**Transcript to Analyze:**

---
{transcript}
---

**Begin Analysis (Return only list items below):**
"""

# SCQA Framework Prompt (New)
SCQA_PROMPT = """
**Act as an elite management consultant analyzing a transcript using the SCQA framework.**

Your task is to analyze the transcript and restructure its core message according to the SCQA framework (Situation, Complication, Question, Answer). Additionally, provide a critical assessment and roadmap.

**Instructions & Output Format:**

Analyze the transcript and generate ONLY HTML list items (`<li>`) based on the sections below. Assign the specified CSS class to each list item.

1.  **SITUATION:**
    *   Identify the current context/background facts agreed upon.
    *   Format: `<li class="scqa-situation">[Summary of Situation]</li>` (Multiple items possible)

2.  **COMPLICATION:**
    *   Identify the key challenge/change/problem disrupting the situation.
    *   Format: `<li class="scqa-complication">[Summary of Complication]</li>` (Multiple items possible)

3.  **QUESTION:**
    *   Formulate the central question arising from the complication.
    *   Format: `<li class="scqa-question">[The single core Question]</li>` (Should typically be one item)

4.  **ANSWER:**
    *   Provide a clear, direct answer to the Question, potentially with supporting points.
    *   Format: `<li class="scqa-answer">[Answer point or Key Message]</li>` (Multiple items possible)

5.  **CRITICAL ASSESSMENT:**
    *   Evaluate how effectively the transcript addressed SCQA elements (completeness, logic).
    *   Format: `<li class="scqa-assessment">[Assessment point]</li>` (Multiple items possible)

6.  **IMPLEMENTATION ROADMAP:**
    *   Outline potential next steps or actions based on the analysis.
    *   Format: `<li class="scqa-roadmap">[Roadmap/Next Step item]</li>` (Multiple items possible)

**Important:** Return *ONLY* the HTML `<li>` items with the specified classes. Do not include headings, explanations, wrappers (`<ul>`, `<div>`), or any other text outside the `<li>` tags.

**Transcript to Analyze:**

---
{transcript}
---

**Begin Analysis (Return only list items below):**
"""

# Hypothesis-Driven Thinking Prompt (New)
HYPOTHESIS_DRIVEN_PROMPT = """
**Act as an analytical strategist specializing in hypothesis-driven problem solving.**

Your task is to analyze the transcript and reframe the discussion using hypothesis-driven thinking.

**Instructions & Output Format:**

Analyze the transcript and generate ONLY HTML list items (`<li>`) based on the sections below. Assign the specified CSS class to each list item.

1.  **PROBLEM STATEMENT:**
    *   Identify and clearly articulate the core problem/decision as a precise, answerable question.
    *   Format: `<li class="hypothesis-problem">[Refined Problem Statement/Question]</li>` (Should be one item)

2.  **HYPOTHESES (3-5):**
    *   Develop distinct, specific, testable hypotheses answering the core question.
    *   Format: `<li class="hypothesis-hypothesis">Hypothesis X: [Hypothesis statement]</li>` (Generate 3-5 items)

3.  **EVIDENCE ANALYSIS (For each Hypothesis):**
    *   Extract supporting evidence from transcript.
        *   Format: `<li class="hypothesis-evidence-support">[Hypothesis X] Supporting: [Evidence from transcript]</li>` (Multiple items possible per hypothesis)
    *   Extract contradicting evidence from transcript.
        *   Format: `<li class="hypothesis-evidence-contradict">[Hypothesis X] Contradicting: [Evidence from transcript]</li>` (Multiple items possible per hypothesis)
    *   Identify critical missing information.
        *   Format: `<li class="hypothesis-evidence-missing">[Hypothesis X] Missing Info: [Critical missing information]</li>` (Multiple items possible per hypothesis)

4.  **HYPOTHESIS PRIORITIZATION:**
    *   Assess and rank hypotheses (most to least promising) based on evidence, impact, testability.
    *   Format: `<li class="hypothesis-priority">[Rank]. [Hypothesis X]: [Brief rationale for rank]</li>` (Generate item for each hypothesis)

5.  **TESTING PLAN (Top 2-3 Hypotheses):**
    *   Outline validation approaches, required data, and analytical methods.
    *   Format: `<li class="hypothesis-testing">[Hypothesis X] Test: [Approach, Data, Method]</li>` (Generate items for top hypotheses)

6.  **DECISION FRAMEWORK:**
    *   Create a structured framework linking findings to decisions (criteria, thresholds).
    *   Format: `<li class="hypothesis-decision">[Decision criterion/threshold and related action]</li>` (Multiple items possible)

7.  **TRANSCRIPT ASSESSMENT:**
    *   Evaluate original discussion vs. hypothesis approach (biases, gaps, assumptions).
    *   Format: `<li class="hypothesis-assessment">[Assessment point]</li>` (Multiple items possible)

**Important:** Return *ONLY* the HTML `<li>` items with the specified classes. Do not include headings, explanations, wrappers (`<ul>`, `<div>`), or any other text outside the `<li>` tags.

**Transcript to Analyze:**

---
{transcript}
---

**Begin Analysis (Return only list items below):**
"""

# First Principles Thinking Prompt (New)
FIRST_PRINCIPLES_PROMPT = """
**Act as a strategic advisor skilled in First Principles Thinking.**

Your task is to analyze the transcript by breaking down the discussion into its fundamental truths and rebuilding from there, challenging assumptions along the way.

**Instructions & Output Format:**

Analyze the transcript and generate ONLY HTML list items (`<li>`) based on the sections below. Assign the specified CSS class to each list item.

1.  **IDENTIFY CONVENTIONAL THINKING:**
    *   Outline key assumptions, mental models, or established approaches in the transcript.
    *   Format: `<li class="fp-conventional">[Conventional Thinking/Assumption Point]</li>` (Multiple items possible)

2.  **BREAK DOWN TO FUNDAMENTALS:**
    *   Identify the most basic, indisputable elements or truths related to the central issue.
    *   Format: `<li class="fp-fundamental">[Fundamental Truth/First Principle]</li>` (Multiple items possible)

3.  **QUESTION ALL ASSUMPTIONS:**
    *   Challenge significant assumptions identified. Note evidence/lack thereof.
    *   Format: `<li class="fp-assumption">[Assumption Challenged]: How do we know this is true? / Evidence: [Present/Absent]</li>` (Multiple items possible)

4.  **REBUILD FROM FIRST PRINCIPLES:**
    *   Construct potential solution pathways using only validated first principles.
    *   Format: `<li class="fp-rebuild">[Rebuilt Approach/Solution Point]</li>` (Multiple items possible)

5.  **IDENTIFY NOVEL INSIGHTS:**
    *   Highlight different conclusions or non-obvious solutions derived from first principles.
    *   Format: `<li class="fp-insight">[Novel Insight/Different Conclusion]</li>` (Multiple items possible)

6.  **IMPLEMENTATION FRAMEWORK:**
    *   Develop practical steps or experiments to apply/validate first principles insights.
    *   Format: `<li class="fp-implementation">[Implementation Step/Experiment]</li>` (Multiple items possible)

7.  **METACOGNITIVE ASSESSMENT:**
    *   Analyze thinking patterns (biases, fallacies) in the transcript that hindered first principles thinking.
    *   Format: `<li class="fp-metacognitive">[Metacognitive Observation/Bias Identified]</li>` (Multiple items possible)

**Important:** Return *ONLY* the HTML `<li>` items with the specified classes. Do not include headings, explanations, wrappers (`<ul>`, `<div>`), or any other text outside the `<li>` tags.

**Transcript to Analyze:**

---
{transcript}
---

**Begin Analysis (Return only list items below):**
"""

# Reframing Prompt (New)
REFRAMING_PROMPT = """
**Act as an expert in clear, structured communication and strategic thinking.**

Your task is to analyze the core topic, problem, or idea discussed in the provided transcript. Identify the essence of the discussion and then reframe it in a clearer, more focused, or more actionable way. Your goal is to enhance understanding and facilitate progress.

**Instructions & Output Format:**

1.  Analyze the transcript to understand the central theme.
2.  Develop a reframed perspective or statement of the theme.
3.  Provide 3-5 supporting bullet points that elaborate on or justify this reframed perspective.

Return ONLY the reframed points as HTML list items (`<li>`) based on the sections below. Assign the specified CSS class to each list item.

*   **Reframed Statement:** Format the main reframed idea as: `<li class="reframing-statement">[Your clear, reframed statement of the core issue/idea]</li>` (Should typically be one item).
*   **Supporting Points:** Format the elaborating points as: `<li class="reframing-point">[Supporting point for the reframed idea]</li>` (Generate 3-5 items).

Example Output:
<li class="reframing-statement">The core challenge isn't *if* we can migrate the feature, but *how* to do so while minimizing user disruption during Q3.</li>
<li class="reframing-point">Focus on identifying the critical user paths affected.</li>
<li class="reframing-point">Prioritize a phased rollout strategy.</li>
<li class="reframing-point">Define clear communication plans for each phase.</li>

**Important:** Return *ONLY* the HTML `<li>` items with the specified classes. Do not include headings, explanations, wrappers (`<ul>`, `<div>`), or any other text outside the `<li>` tags.

**Transcript to Analyze:**

---
{transcript}
---

**Begin Analysis (Return only list items below):**
"""
