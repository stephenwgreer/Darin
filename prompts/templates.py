# Default topic extraction prompt - REMOVED

# Practitioner insights prompt - OLD VERSION REMOVED

# New Practitioner Insights Prompt (Streaming)
PRACTITIONER_INSIGHTS_STREAMING_PROMPT = """
Analyze the provided transcript, focusing on the most recent discussion if possible.
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
{transcript}
"""

# Meeting summary prompt
MEETING_SUMMARY_PROMPT = """
Create a concise summary of the following meeting transcript.
Include key decisions made, important discussion points, and overall meeting purpose.

Return ONLY the summary points as HTML list items, each formatted exactly as:
<li class="insight-item">[Summary point]</li>

Example Output:
<li class="insight-item">[Key decision 1]</li>
<li class="insight-item">[Important discussion point]</li>
...

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}
"""

# Fill in gaps in reasoning prompt
FILL_IN_GAPS_PROMPT = """
You are analyzing a transcript to identify thinking patterns and gaps in reasoning.
Task: Review the following transcript and identify:
1. Core thinking patterns present (as a single summary point).
2. Specific gaps in the reasoning (as bullet points).
3. Recommendations to make the analysis more complete (as bullet points).

Return ONLY the identified points as HTML list items, formatted exactly as follows:
- For Core Thinking: `<li class="core-thinking">[Single summary of core thinking]</li>`
- For Gaps: `<li class="gap-item">[Gap 1 description]</li>` (multiple items)
- For Recommendations: `<li class="recommendation-item">[Recommendation 1]</li>` (multiple items)

Example Output:
<li class="core-thinking">The core thinking focused heavily on feature conversion feasibility.</li>
<li class="gap-item">Gap 1: Consideration of data scaling issues was missing.</li>
<li class="gap-item">Gap 2: Alternative modeling approaches weren't explored.</li>
<li class="recommendation-item">Recommendation 1: Evaluate data volume impact.</li>
<li class="recommendation-item">Recommendation 2: Benchmark against simpler models.</li>

Do not include the headings (CORE_THINKING, GAPS, RECOMMENDATIONS) or any other text, wrappers, or formatting.

Transcript:
{transcript}
"""

# Challenge questions and thought provocation prompt
BRAINSTORM_PROMPT = """
Analyze the following transcript and generate thought-provoking questions that challenge assumptions and encourage new perspectives.
Task: Review the transcript and create:
1. Questions that challenge core assumptions.
2. Alternatives that reframe the problem.
3. Provocative ideas to expand thinking.

Return ONLY the generated points as HTML list items, formatted exactly as follows:
- For Challenge Questions: `<li class="challenge-question">[Specific question]</li>` (multiple items)
- For Alternative Frames: `<li class="alternative-frame">[Alternative view]</li>` (multiple items)
- For Provocative Ideas: `<li class="provocative-idea">[Unexpected approach]</li>` (multiple items)

Example Output:
<li class="challenge-question">What if the core assumption about X is wrong?</li>
<li class="challenge-question">How might Y be influencing this outcome?</li>
<li class="alternative-frame">Could we view this not as a problem, but an opportunity?</li>
<li class="provocative-idea">What if we applied principles from Z field here?</li>

Do not include the headings (CHALLENGE_QUESTIONS, ALTERNATIVE_FRAMES, PROVOCATIVE_IDEAS) or any other text, wrappers, or formatting.
Keep questions constructive and focused on generating new insights.

Transcript:
{transcript}
"""

# Related a transcript back to SAS Viya capabilities prompt
COMPANY_FIT_PROMPT = """
Analyze the following call transcript and identify opportunities to position SAS Viya capabilities as solutions.
Task: Extract key topics, connect them to relevant SAS Viya features, and identify missing considerations.

Return ONLY the generated points as HTML list items, formatted exactly as follows:
- For Key Topics: `<li class="key-topic">[Topic 1 from conversation]</li>` (multiple items)
- For SAS Viya Connections: `<li class="viya-connection">[Topic X]: [How SAS Viya addresses this]</li>` (multiple items, associate with a topic)
- For Missing Considerations: `<li class="missing-consideration">[Additional capability/opportunity]</li>` (multiple items)

Example Output:
<li class="key-topic">Risk Modeling Accuracy</li>
<li class="key-topic">Data Integration Challenges</li>
<li class="viya-connection">Risk Modeling Accuracy: SAS Viya's Model Studio offers automated ML...</li>
<li class="viya-connection">Data Integration Challenges: SAS Studio Flow provides visual ETL...</li>
<li class="missing-consideration">Consider Viya's forecasting capabilities for scenario planning.</li>
<li class="missing-consideration">Explore integration with existing visualization tools via APIs.</li>

Do not include the headings (KEY_TOPICS, SAS_VIYA_CONNECTIONS, MISSING_CONSIDERATIONS) or any other text, wrappers, or formatting.
Be specific about how SAS Viya's capabilities address expressed needs.

Transcript:
{transcript}
"""

# Fact checking prompt:
FACT_CHECKING_PROMPT = """
Identify factual claims in the following transcript and evaluate their accuracy.
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

Example Output:
<li class="fact-check-item">
    <strong>Claim 1:</strong> "The sky is green."<br>
    <strong>Accuracy:</strong> 1/5<br>
    <strong>Correction:</strong> The sky is typically blue due to Rayleigh scattering.
</li>
<li class="fact-check-item">
    <strong>Claim 2:</strong> "Water boils at 100C at sea level."<br>
    <strong>Accuracy:</strong> 5/5<br>
    <strong>Correction:</strong> N/A
</li>

Do not include any other text, wrappers (like <ul> or <div>), headers, or formatting.

Text to analyze:
{transcript}
"""

# Follow-up questions prompt
FOLLOW_UP_QUESTIONS_PROMPT = """
Based on the following transcript, generate 5 insightful follow-up questions that would 
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
{transcript}
"""

# Sentiment analysis prompt
SENTIMENT_ANALYSIS_PROMPT = """
Analyze the sentiment and emotional tone of this conversation transcript.

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
{transcript}
"""

# Answer Question Prompt (New)
ANSWER_QUESTION_PROMPT = """
Analyze the provided transcript, paying close attention to the END of the text.
Identify the single LAST question asked by any speaker in the transcript.

If a question is found, generate:
1.  3-5 concise, relevant points for the ANSWER.
2.  Exactly 2 points explaining the RATIONALE behind the answer.
3.  2-3 concrete EXAMPLES illustrating the answer, if applicable. If examples are not applicable, provide ONE item stating that.

Return ONLY the generated points as HTML list items, formatted exactly as follows:
-   For Answer points: `<li class="answer-item">[Suggested answer point]</li>`
-   For Rationale points: `<li class="rationale-item">[Rationale point]</li>`
-   For Example points: `<li class="example-item">[Concrete example or 'N/A']</li>`

If no question is found near the end, return ONLY ONE list item: `<li class="answer-item">No clear question identified at the end of the transcript.</li>`

Example Output (if question found):
<li class="answer-item">Start by acknowledging the core concern about X.</li>
<li class="answer-item">Mention the mitigation strategy Y.</li>
<li class="rationale-item">This addresses the user's primary worry directly.</li>
<li class="rationale-item">It demonstrates proactive problem-solving.</li>
<li class="example-item">For instance, in project Z, we used Y to reduce risk by 20%.</li>
<li class="example-item">Another case is client A, where Y improved stability significantly.</li>

Do not include the identified question itself, any headers, wrappers, or other text.

Transcript:
{transcript}
"""

# PROBLEM_SOLVING_PROMPT - MOVED TO logic_templates.py

# SCQA_PROMPT - MOVED TO logic_templates.py

##############################
## Extra prompts
##############################

# Topic summary prompt
TOPIC_SUMMARY_PROMPT = """
Analyze the following transcript from a work call and identify the three main topics discussed.
Focus on topics that are most relevant to banking and financial services.

Return ONLY the 3 topics as HTML list items, each formatted exactly as:
<li class="insight-item">[Topic name]</li>

Example Output:
<li class="insight-item">[Primary banking/financial topic]</li>
<li class="insight-item">[Secondary related topic]</li>
<li class="insight-item">[Third related topic]</li>

Do not include any other text, wrappers, headers, or formatting.

Text to analyze:
{transcript}
"""