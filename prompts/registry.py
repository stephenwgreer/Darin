from dataclasses import dataclass

from .logic_templates import (
    FIRST_PRINCIPLES_PROMPT,
    HYPOTHESIS_DRIVEN_PROMPT,
    PROBLEM_SOLVING_PROMPT,
    REFRAMING_PROMPT,
    SCQA_PROMPT,
)

# Import all prompt templates
from .templates import (
    ANSWER_QUESTION_PROMPT,
    BRAINSTORM_PROMPT,
    COMPANY_FIT_PROMPT,
    FACT_CHECKING_PROMPT,
    FILL_IN_GAPS_PROMPT,
    FOLLOW_UP_QUESTIONS_PROMPT,
    MEETING_SUMMARY_PROMPT,
    PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)


@dataclass
class PromptConfig:
    id: str  # Unique identifier
    button_text: str  # Text for the button in ControlsPanel
    template: str  # The actual prompt template string
    output_title: str  # Title displayed in the OutputPanel
    template_type: str  # Identifier used for stream handling / static HTML setup
    # signal_name: str  # Optional: Map to original ControlsPanel signal name (for refactoring help)
    # group: str = "Default" # Optional: For grouping buttons later


# Define all prompts using the configuration structure
# This becomes the single source of truth for prompts
PROMPT_REGISTRY = [
    # --- Transcript Processing Group ---
    PromptConfig(
        id="topic_summary",
        button_text="Extract Topics",
        template=TOPIC_SUMMARY_PROMPT,
        output_title="Key Topics",
        template_type="topic-summary",
    ),
    PromptConfig(
        id="meeting_summary",
        button_text="Meeting Summary",
        template=MEETING_SUMMARY_PROMPT,
        output_title="Meeting Summary",
        template_type="meeting-summary",
    ),
    PromptConfig(
        id="sentiment_analysis",
        button_text="Sentiment Analysis",
        template=SENTIMENT_ANALYSIS_PROMPT,
        output_title="Sentiment Analysis",
        template_type="sentiment-analysis",
    ),
    # --- Standalone Prompts ---
    PromptConfig(
        id="practitioner_insights",
        button_text="Practitioner Insights",
        template=PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
        output_title="Banking Practitioner Insights",
        template_type="practitioner-insights",
    ),
    PromptConfig(
        id="follow_up_questions",
        button_text="Follow-up Questions",
        template=FOLLOW_UP_QUESTIONS_PROMPT,
        output_title="Follow-up Questions",
        template_type="follow-up-questions",
    ),
    PromptConfig(
        id="first_principles",
        button_text="First Principles",
        template=FIRST_PRINCIPLES_PROMPT,
        output_title="First Principles",
        template_type="first-principles",
    ),
    PromptConfig(
        id="reframing",
        button_text="Reframing",
        template=REFRAMING_PROMPT,
        output_title="Reframing",
        template_type="reframing",
    ),
    PromptConfig(
        id="scqa",
        button_text="SCQA Framework",
        template=SCQA_PROMPT,
        output_title="SCQA Framework",
        template_type="scqa",
    ),
    PromptConfig(
        id="hypothesis_driven",
        button_text="Hypothesis Thinking",
        template=HYPOTHESIS_DRIVEN_PROMPT,
        output_title="Hypothesis Thinking",
        template_type="hypothesis-driven",
    ),
    PromptConfig(
        id="gaps_reasoning",
        button_text="Gaps in Reasoning",
        template=FILL_IN_GAPS_PROMPT,
        output_title="Gaps in Reasoning",
        template_type="fill-gaps",
    ),
    PromptConfig(
        id="brainstorming",
        button_text="Brainstorming",
        template=BRAINSTORM_PROMPT,
        output_title="Brainstorm Questions",
        template_type="brainstorm",
    ),
    PromptConfig(
        id="issue_tree",
        button_text="Issue Tree Logic",
        template=PROBLEM_SOLVING_PROMPT,
        output_title="Issue Tree Logic",
        template_type="problem-solving",
    ),
    PromptConfig(
        id="company_fit",
        button_text="SAS Viya Alignment",
        template=COMPANY_FIT_PROMPT,
        output_title="SAS Viya Alignment",
        template_type="company-fit",
    ),
    PromptConfig(
        id="fact_check",
        button_text="Fact Check",
        template=FACT_CHECKING_PROMPT,
        output_title="Fact Check Analysis",
        template_type="fact-check",
    ),
    PromptConfig(
        id="answer_question",
        button_text="Answer Question",
        template=ANSWER_QUESTION_PROMPT,
        output_title="Answer Question",
        template_type="answer-question",
    ),
]


# Helper to get config by ID
def get_prompt_config_by_id(prompt_id: str) -> PromptConfig | None:
    for config in PROMPT_REGISTRY:
        if config.id == prompt_id:
            return config
    return None
