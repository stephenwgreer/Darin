"""Utility functions for transcript processing and analysis."""

import json
from typing import Any

import anthropic
from loguru import logger

import config


def get_anthropic_client(api_key: str) -> anthropic.Anthropic:
    """Create and return an Anthropic client with the provided API key."""
    return anthropic.Anthropic(api_key=api_key)


def process_transcript(
    client: anthropic.Anthropic, transcript: str, prompt_template: str, **kwargs: Any
) -> str | dict[str, str]:
    """
    Process transcript with a specific prompt template.

    Args:
        client: Anthropic client instance
        transcript: Transcript text to process
        prompt_template: Template string with placeholders
        **kwargs: Additional template variables

    Returns:
        Processed text or error dict

    Raises:
        ValueError: If inputs are invalid
    """
    try:
        prompt = prompt_template.format(transcript=transcript, **kwargs)

        logger.info("Processing transcript with Claude API")
        logger.debug(f"Prompt length: {len(prompt)} characters")

        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
            system="You analyze transcripts and extract key information.",
            messages=[{"role": "user", "content": prompt}],
        )

        result = message.content[0].text
        logger.info(f"Received response: {len(result)} characters")
        return result
    except Exception as e:
        logger.error(f"Error processing transcript: {e}")
        return {"error": str(e)}


def get_practitioner_insights(client: anthropic.Anthropic, transcript: str) -> dict[str, Any]:
    """
    Extract topics and get practitioner insights for each topic.

    Args:
        client: Anthropic client instance
        transcript: Transcript text to analyze

    Returns:
        Dict with topics and insights for each topic
    """
    try:
        logger.info("Extracting practitioner insights from transcript")

        # First, extract the topics
        topics_result = process_transcript(client, transcript, TOPIC_SUMMARY_PROMPT)

        # Parse topics from JSON
        if isinstance(topics_result, dict) and "error" in topics_result:
            return topics_result

        topics_data = json.loads(str(topics_result))

        # Prepare results container
        insights_results: dict[str, Any] = {"topics": topics_data, "insights": {}}

        # For each topic, get practitioner insights
        for key, topic in topics_data.items():
            insight = process_transcript(
                client, transcript, PRACTITIONER_INSIGHTS_PROMPT, topic=topic
            )
            insights_results["insights"][key] = insight

        logger.info(f"Extracted insights for {len(topics_data)} topics")
        return insights_results
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse topics JSON: {e}")
        return {"error": f"Invalid JSON in topics response: {e}"}
    except Exception as e:
        logger.error(f"Error processing practitioner insights: {e}")
        return {"error": f"Error processing practitioner insights: {e}"}


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
