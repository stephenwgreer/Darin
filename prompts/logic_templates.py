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