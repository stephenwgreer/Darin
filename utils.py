import anthropic
import json

def get_anthropic_client(api_key):
    """Create and return an Anthropic client with the provided API key"""
    return anthropic.Anthropic(api_key=api_key)

def process_transcript(client, transcript, prompt_template, **kwargs):
    """Process transcript with a specific prompt template"""
    try:
        prompt = prompt_template.format(transcript=transcript, **kwargs)
        
        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            temperature=0,
            system="You analyze transcripts and extract key information.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
    except Exception as e:
        return {"error": str(e)}
        
def get_practitioner_insights(client, transcript):
    """Extract topics and get practitioner insights for each topic"""
    try:
        # First, extract the topics
        topics_result = process_transcript(client, transcript, TOPIC_SUMMARY_PROMPT)
        
        # Parse topics from JSON
        topics_data = json.loads(topics_result)
        
        # Prepare results container
        insights_results = {
            "topics": topics_data,
            "insights": {}
        }
        
        # For each topic, get practitioner insights
        for key, topic in topics_data.items():
            insight = process_transcript(
                client, 
                transcript, 
                PRACTITIONER_INSIGHTS_PROMPT, 
                topic=topic
            )
            insights_results["insights"][key] = insight
        
        return insights_results
    except Exception as e:
        return {"error": f"Error processing practitioner insights: {str(e)}"}

# Predefined prompt templates
TOPIC_SUMMARY_PROMPT = """
Analyze the following transcript from a work call and summarize the three main topics discussed.
Return the list of topics in JSON format with keys "topic1", "topic2", and "topic3".
Return nothing other than this requested output.

Text to analyze:
{transcript}
"""

PRACTITIONER_INSIGHTS_PROMPT = """
What are some things about {topic} in banking that only a practitioner would know? Give me some practitioner levels of insight. Provide 5 bullets.
"""

MEETING_SUMMARY_PROMPT = """
Create a concise summary of the following meeting transcript.
Include key decisions made, important discussion points, and overall meeting purpose.
Format as a readable meeting summary that could be shared with team members.

Text to analyze:
{transcript}
"""

FOLLOW_UP_QUESTIONS_PROMPT = """
Based on the following transcript, generate 5 insightful follow-up questions that would 
help clarify or expand on the topics discussed.
Return in JSON format with a "questions" array.

Text to analyze:
{transcript}
"""

SENTIMENT_ANALYSIS_PROMPT = """
Analyze the sentiment and emotional tone of this conversation transcript.
Identify any tensions, positive moments, or shifts in tone throughout the discussion.
Return a JSON object with "overall_sentiment" and "key_moments" fields.

Text to analyze:
{transcript}
"""