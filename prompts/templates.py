# Default topic extraction prompt
DEFAULT_TOPIC_EXTRACTION_PROMPT = """
Analyze the following transcript from a work call and summarize the topic three topics discussed in the transcription.

The first topic should be the strongest one, the second topic should be the second strongest, and the third topic should be the third strongest.

I want the topics to be relevant to a follow-up prompt which take each topic and then distill practitioner level insights.
Keep that in mind when deciding what the topics are.

Return the list of topics in JSON format which can be passed on to other applications where the keys are topic 1, topic 2, and topic 3.
And the values are each of the topics.

Return nothing other than this requested output. Return ONLY formatted JSON with no extra characters.

Text to analyze:
{transcript}
"""

# Topic summary prompt
TOPIC_SUMMARY_PROMPT = """
Analyze the following transcript from a work call and summarize the three main topics discussed.
Return the list of topics in JSON format with keys "topic1", "topic2", and "topic3".
Return nothing other than this requested output.

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
Return a JSON object with "overall_sentiment" and "key_moments" fields.

Text to analyze:
{transcript}
"""