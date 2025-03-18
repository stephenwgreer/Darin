# Default topic extraction prompt
DEFAULT_TOPIC_EXTRACTION_PROMPT = """
Analyze the following transcript from a work call and summarize the topic three topics discussed 
in the transcription.

The first topic should be the MOST RECENT topic discussed (since this is a transcript, this is the 
last few setences of the transcript), the second topic should be the second strongest of the entire transcript, 
and the third topic should be the third strongest.

I want the topics to be relevant to a follow-up prompt which take each topic and then distill 
practitioner level insights.
Keep that in mind when deciding what the topics are.

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
What are some things about {topic} in banking that only a practitioner would know? Give me some practitioner levels of insight. Provide 5 bullets.
"""

# Meeting summary prompt
MEETING_SUMMARY_PROMPT = """
Create a concise summary of the following meeting transcript.
Include key decisions made, important discussion points, and overall meeting purpose.
Format as a readable meeting summary that could be shared with team members.

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
Transcript:
{transcript}
"""

# Fact checking prompt:
FACT_CHECKING_PROMPT = """
Identify and evaluate factual claims in the following transcript.
Task: Extract specific factual statements and rate their accuracy on a scale of 1-5.
Respond with the following:
FACTUAL_CLAIMS:

"[Direct quote of factual claim from transcript]"

Accuracy Score: [1-5]
Explanation: [Brief explanation of why this score was assigned]
Correct Information: [The accurate information, if score is <5]


"[Direct quote of factual claim from transcript]"

Accuracy Score: [1-5]
Explanation: [Brief explanation of why this score was assigned]
Correct Information: [The accurate information, if score is <5]


"[Direct quote of factual claim from transcript]"

Accuracy Score: [1-5]
Explanation: [Brief explanation of why this score was assigned]
Correct Information: [The accurate information, if score is <5]



SCORING GUIDE:
1 = Not accurate (completely false)
2 = Mostly inaccurate (contains some truth but is misleading)
3 = Partially accurate (mix of accurate and inaccurate elements)
4 = Mostly accurate (generally true with minor errors or omissions)
5 = Totally accurate (completely true and precise)
Transcript:
{transcript}
"""

# Follow-up questions prompt
FOLLOW_UP_QUESTIONS_PROMPT = """
Based on the following transcript, generate 5 insightful follow-up questions that would 
help clarify or expand on the topics discussed.
Return in JSON format with a "questions" array.

Text to analyze:
{transcript}
"""

# Sentiment analysis prompt
SENTIMENT_ANALYSIS_PROMPT = """
Analyze the sentiment and emotional tone of this conversation transcript.
Identify any tensions, positive moments, or shifts in tone throughout the discussion.
Return bullet points with "overall_sentiment" and "key_moments" sub-bullets.
Overall sentiment: [Positive/Negative/Neutral]
Key moments:
- [Brief description]

Text to analyze:
{transcript}
"""

##############################
## Extra prompts
##############################

# Topic summary prompt
TOPIC_SUMMARY_PROMPT = """
Summarize the following transcript from a work call.

Text to Summarize:
{transcript}
"""