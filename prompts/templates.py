# Default topic extraction prompt
DEFAULT_TOPIC_EXTRACTION_PROMPT = """
Analyze the following transcript from a work call and summarize the topic three topics discussed 
in the transcription.

Read the transcript carefully and decide what is the most relevent topic being discussed that is relevent to banking. That will be topic 1.
Then create two more sub-topics related to the main topic and based on what was discussed in the transcript.

Return the list of topics in JSON format which can be passed on to other applications where the 
keys are topic 1, topic 2, and topic 3.
And the values are each of the topics.

Return nothing other than this requested output. 
Return ONLY formatted JSON with no extra characters.

Text to analyze:
{transcript}
"""

# Practitioner insights prompt
PRACTITIONER_INSIGHTS_PROMPT = """
What are some things about {topic} in banking that only a practitioner would know? Give me some practitioner levels of insight. 
Provide 5 bullets. Respond as if you are the practitioner making a declaritive and explanatory statement. 

The format for the response should be exactly as shown below. Use HTML tags as specified:

<div class="topic-section">
    <h2 class="topic-title">{topic}</h2>
    <div class="insight-block">
        <ul class="insight-list">
            <li class="insight-item">Insight 1</li>
            <li class="insight-item">Insight 2</li>
            <li class="insight-item">Insight 3</li>
            <li class="insight-item">Insight 4</li>
            <li class="insight-item">Insight 5</li>
        </ul>
    </div>
</div>

Return ONLY this HTML structure with your insights. Do not include any other text or formatting.
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

Core thinking patterns present
Specific gaps in the reasoning
Recommendations to make the analysis more complete

Respond with the following sections:
CORE_THINKING:

Brief summary of primary thought processes demonstrated

GAPS:

Gap 1: [Brief description of missing consideration]
Gap 2: [Brief description of missing consideration]
Gap 3: [Brief description of missing consideration]

RECOMMENDATIONS:

[Concise recommendation 1]
[Concise recommendation 2]
[Concise recommendation 3]

Keep your analysis objective, concise, and focused on improving the thinking rather than criticizing it.
Return in markdown syntax to make it pretty formatting.

Transcript:
{transcript}
"""

# Challenge questions and thought provocation prompt
BRAINSTORM_PROMPT = """
Analyze the following transcript and generate thought-provoking questions that challenge assumptions and encourage new perspectives.
Task: Review the transcript and create:

Questions that challenge core assumptions
Alternatives that reframe the problem
Provocative ideas to expand thinking

Respond with the following sections:
CHALLENGE_QUESTIONS:

[Specific question that challenges a key assumption]
[Question exploring an unconsidered angle]
[Question addressing potential blind spots]

ALTERNATIVE_FRAMES:

[Alternative way to view the problem]
[Different perspective that shifts the paradigm]
[Reframing that questions fundamental assumptions]

PROVOCATIVE_IDEAS:

[Unexpected approach or solution]
[Counterintuitive concept worth exploring]
[Novel connection or insight]

Keep questions constructive, focused on generating new insights rather than criticism. Phrase questions to invite collaborative brainstorming.
Return in markdown syntax to make it pretty formatting.

Transcript:
{transcript}
"""

# Related a transcript back to SAS Viya capabilities prompt
COMPANY_FIT_PROMPT = """
Analyze the following call transcript and identify opportunities to position SAS Viya capabilities as solutions.
Task: Extract key topics from the conversation and connect them to relevant SAS Viya features and capabilities.
Respond with the following sections:
KEY_TOPICS:

[Topic 1 from conversation]
[Topic 2 from conversation]
[Topic 3 from conversation]

SAS_VIYA_CONNECTIONS:

Topic 1: [How SAS Viya addresses this specific need/challenge]
Topic 2: [How SAS Viya addresses this specific need/challenge]
Topic 3: [How SAS Viya addresses this specific need/challenge]

MISSING_CONSIDERATIONS:

[Additional capability/feature not mentioned that would benefit this customer]
[Potential integration opportunity not discussed]
[Business value proposition that wasn't highlighted]

Be specific about how SAS Viya's analytics, AI, data management, and visualization capabilities directly address the customer's expressed needs and challenges.
Return in markdown syntax to make it pretty formatting.

Transcript:
{transcript}
"""

# Fact checking prompt:
FACT_CHECKING_PROMPT = """
Identify and evaluate factual claims in the following transcript.
Rate each claim's accuracy on a scale of 1-5 where:
1 = Not accurate (completely false)
2 = Mostly inaccurate (contains some truth but is misleading)
3 = Partially accurate (mix of accurate and inaccurate elements)
4 = Mostly accurate (generally true with minor errors or omissions)
5 = Totally accurate (completely true and precise)

The format for the response should be exactly as shown below. Use HTML tags as specified:

<div class="topic-section">
    <h2 class="topic-title">Fact Check Analysis</h2>
    <div class="insight-block">
        <ul class="insight-list">
            <li class="insight-item">
                <strong>Claim 1:</strong> "[Direct quote]"<br>
                <strong>Accuracy:</strong> [1-5]/5<br>
                <strong>Correction:</strong> [Accurate information if score < 5]
            </li>
            <li class="insight-item">
                <strong>Claim 2:</strong> "[Direct quote]"<br>
                <strong>Accuracy:</strong> [1-5]/5<br>
                <strong>Correction:</strong> [Accurate information if score < 5]
            </li>
            <li class="insight-item">
                <strong>Claim 3:</strong> "[Direct quote]"<br>
                <strong>Accuracy:</strong> [1-5]/5<br>
                <strong>Correction:</strong> [Accurate information if score < 5]
            </li>
            <li class="insight-item">
                <strong>Claim 4:</strong> "[Direct quote]"<br>
                <strong>Accuracy:</strong> [1-5]/5<br>
                <strong>Correction:</strong> [Accurate information if score < 5]
            </li>
            <li class="insight-item">
                <strong>Claim 5:</strong> "[Direct quote]"<br>
                <strong>Accuracy:</strong> [1-5]/5<br>
                <strong>Correction:</strong> [Accurate information if score < 5]
            </li>
        </ul>
    </div>
</div>

Return ONLY this HTML structure with your analysis. Do not include any other text or formatting.

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

##############################
## Extra prompts
##############################

# Topic summary prompt
TOPIC_SUMMARY_PROMPT = """
Analyze the following transcript from a work call and identify the three main topics discussed.
Focus on topics that are most relevant to banking and financial services.

The format for the response should be exactly as shown below. Use HTML tags as specified:

<div class="topic-section">
    <h2 class="topic-title">Key Topics</h2>
    <div class="insight-block">
        <ul class="insight-list">
            <li class="insight-item">[Primary banking/financial topic]</li>
            <li class="insight-item">[Secondary related topic]</li>
            <li class="insight-item">[Third related topic]</li>
        </ul>
    </div>
</div>

Return ONLY this HTML structure with your analysis. Do not include any other text or formatting.

Text to analyze:
{transcript}
"""