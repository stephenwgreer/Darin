from dataclasses import dataclass, field
from typing import Literal

from .logic_templates import (
    FIRST_PRINCIPLES_PROMPT,
    HYPOTHESIS_DRIVEN_PROMPT,
    PROBLEM_SOLVING_PROMPT,
    REFRAMING_PROMPT,
    SCQA_PROMPT,
)

# Import all prompt templates
from .templates import (
    ACTION_ITEMS_PROMPT,
    ANALYZE_STATEMENT_PROMPT,
    ANSWER_QUESTION_PROMPT,
    BRAINSTORM_PROMPT,
    BUYING_SIGNALS_PROMPT,
    COMPANY_FIT_PROMPT,
    DEAL_RISK_PROMPT,
    FACT_CHECKING_PROMPT,
    FILL_IN_GAPS_PROMPT,
    FOLLOW_UP_QUESTIONS_PROMPT,
    KEY_DECISIONS_PROMPT,
    MEETING_SUMMARY_PROMPT,
    OBJECTION_HANDLING_PROMPT,
    PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)


BucketType = Literal["mid_meeting", "reasoning", "post_meeting", "sales"]


@dataclass
class PromptConfig:
    id: str  # Unique identifier
    button_text: str  # Text for the button in ControlsPanel
    template: str  # The actual prompt template string
    output_title: str  # Title displayed in the OutputPanel
    template_type: str  # Identifier used for stream handling / static HTML setup
    bucket: BucketType = field(default="mid_meeting")


# Define all prompts using the configuration structure
# This becomes the single source of truth for prompts
PROMPT_REGISTRY = [
    # --- Bucket 0: Sales (4 prompts) ---
    PromptConfig(
        id="sentiment_analysis",
        button_text="Sentiment Analysis",
        template=SENTIMENT_ANALYSIS_PROMPT,
        output_title="Sentiment Analysis",
        template_type="sentiment-analysis",
        bucket="sales",
    ),
    PromptConfig(
        id="buying_signals",
        button_text="Buying Signals",
        template=BUYING_SIGNALS_PROMPT,
        output_title="Buying Signals",
        template_type="buying-signals",
        bucket="sales",
    ),
    PromptConfig(
        id="objection_handling",
        button_text="Objections",
        template=OBJECTION_HANDLING_PROMPT,
        output_title="Objection Analysis",
        template_type="objection-handling",
        bucket="sales",
    ),
    PromptConfig(
        id="deal_risk",
        button_text="Deal Risk",
        template=DEAL_RISK_PROMPT,
        output_title="Deal Risk Assessment",
        template_type="deal-risk",
        bucket="sales",
    ),
    # --- Bucket 1: Mid-Meeting Analysis (8 prompts) ---
    PromptConfig(
        id="practitioner_insights",
        button_text="Practitioner Insights",
        template=PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
        output_title="Banking Practitioner Insights",
        template_type="practitioner-insights",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="follow_up_questions",
        button_text="Follow-up Questions",
        template=FOLLOW_UP_QUESTIONS_PROMPT,
        output_title="Follow-up Questions",
        template_type="follow-up-questions",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="gaps_reasoning",
        button_text="Gaps in Reasoning",
        template=FILL_IN_GAPS_PROMPT,
        output_title="Gaps in Reasoning",
        template_type="fill-gaps",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="brainstorming",
        button_text="Brainstorming",
        template=BRAINSTORM_PROMPT,
        output_title="Brainstorm Questions",
        template_type="brainstorm",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="company_fit",
        button_text="SAS Viya Alignment",
        template=COMPANY_FIT_PROMPT,
        output_title="SAS Viya Alignment",
        template_type="company-fit",
        bucket="sales",
    ),
    PromptConfig(
        id="fact_check",
        button_text="Fact Check",
        template=FACT_CHECKING_PROMPT,
        output_title="Fact Check Analysis",
        template_type="fact-check",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="answer_question",
        button_text="Answer Question",
        template=ANSWER_QUESTION_PROMPT,
        output_title="Answer Question",
        template_type="answer-question",
        bucket="mid_meeting",
    ),
    PromptConfig(
        id="analyze_statement",
        button_text="Analyze Statement",
        template=ANALYZE_STATEMENT_PROMPT,
        output_title="Statement Analysis",
        template_type="analyze-statement",
        bucket="mid_meeting",
    ),
    # --- Bucket 2: Reasoning Frameworks (5 prompts) ---
    PromptConfig(
        id="scqa",
        button_text="SCQA Framework",
        template=SCQA_PROMPT,
        output_title="SCQA Framework",
        template_type="scqa",
        bucket="reasoning",
    ),
    PromptConfig(
        id="issue_tree",
        button_text="Issue Tree Logic",
        template=PROBLEM_SOLVING_PROMPT,
        output_title="Issue Tree Logic",
        template_type="problem-solving",
        bucket="reasoning",
    ),
    PromptConfig(
        id="first_principles",
        button_text="First Principles",
        template=FIRST_PRINCIPLES_PROMPT,
        output_title="First Principles",
        template_type="first-principles",
        bucket="reasoning",
    ),
    PromptConfig(
        id="hypothesis_driven",
        button_text="Hypothesis Thinking",
        template=HYPOTHESIS_DRIVEN_PROMPT,
        output_title="Hypothesis Thinking",
        template_type="hypothesis-driven",
        bucket="reasoning",
    ),
    PromptConfig(
        id="reframing",
        button_text="Reframing",
        template=REFRAMING_PROMPT,
        output_title="Reframing",
        template_type="reframing",
        bucket="reasoning",
    ),
    # --- Bucket 3: Post-Meeting Analysis (4 prompts) ---
    PromptConfig(
        id="meeting_summary",
        button_text="Meeting Summary",
        template=MEETING_SUMMARY_PROMPT,
        output_title="Meeting Summary",
        template_type="meeting-summary",
        bucket="post_meeting",
    ),
    PromptConfig(
        id="topic_summary",
        button_text="Extract Topics",
        template=TOPIC_SUMMARY_PROMPT,
        output_title="Key Topics",
        template_type="topic-summary",
        bucket="post_meeting",
    ),
    PromptConfig(
        id="action_items",
        button_text="Action Items",
        template=ACTION_ITEMS_PROMPT,
        output_title="Action Items",
        template_type="action-items",
        bucket="post_meeting",
    ),
    PromptConfig(
        id="key_decisions",
        button_text="Key Decisions",
        template=KEY_DECISIONS_PROMPT,
        output_title="Key Decisions",
        template_type="key-decisions",
        bucket="post_meeting",
    ),
]


# Helper to get config by ID
def get_prompt_config_by_id(prompt_id: str) -> PromptConfig | None:
    for config in PROMPT_REGISTRY:
        if config.id == prompt_id:
            return config
    return None


# Helper to filter by bucket (DAR2-27)
def get_prompts_by_bucket(bucket: BucketType) -> list[PromptConfig]:
    """Return all prompts for a given bucket.

    Args:
        bucket: One of "mid_meeting", "reasoning", or "post_meeting".

    Returns:
        List of PromptConfig entries with matching bucket value.
    """
    return [cfg for cfg in PROMPT_REGISTRY if cfg.bucket == bucket]
