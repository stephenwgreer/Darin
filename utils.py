"""Utility functions for transcript processing and analysis."""

import json
from typing import Any

import anthropic
from loguru import logger

import config


def get_anthropic_client(api_key: str) -> anthropic.Anthropic:
    """
    Create and return an Anthropic client with the provided API key.

    Args:
        api_key: The Anthropic API key for authentication.

    Returns:
        An initialized Anthropic client instance.

    Raises:
        ValueError: If api_key is None or empty.
        AuthenticationError: If the API key is invalid.
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key cannot be empty or whitespace-only")

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
        Processed text from Claude API, or error dict if processing fails

    Raises:
        ValueError: If inputs are invalid or template formatting fails
        APIError: If Anthropic API returns an error
        APIConnectionError: If network connection fails
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

        # Extract text from first content block (type: TextBlock)
        first_block = message.content[0]
        if hasattr(first_block, "text"):
            result = first_block.text
            logger.info(f"Received response: {len(result)} characters")
            return result
        else:
            error_msg = f"Unexpected content block type: {type(first_block)}"
            logger.error(error_msg)
            return {"error": error_msg}
    except KeyError as e:
        logger.error(f"Template formatting failed - missing placeholder: {e}")
        return {"error": f"Invalid template placeholder: {e}"}
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return {"error": f"API error: {e}"}
    except anthropic.APIConnectionError as e:
        logger.error(f"API connection failed: {e}")
        return {"error": f"Connection error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing transcript: {e}")
        return {"error": f"Unexpected error: {e}"}


def get_practitioner_insights(client: anthropic.Anthropic, transcript: str) -> dict[str, Any]:
    """
    Extract topics and get practitioner insights for each topic.

    Args:
        client: Anthropic client instance
        transcript: Transcript text to analyze

    Returns:
        Dict with topics and insights for each topic, or error dict if processing fails

    Raises:
        ValueError: If transcript is empty or invalid
    """
    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty")

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
    except (anthropic.APIError, anthropic.APIConnectionError) as e:
        logger.error(f"API error while extracting insights: {e}")
        return {"error": f"API error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing practitioner insights: {e}")
        return {"error": f"Unexpected error: {e}"}
