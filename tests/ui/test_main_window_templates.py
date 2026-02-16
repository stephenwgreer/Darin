"""
MainWindow Template Setup Tests

Tests all 15 template types in _setup_static_template():
1. follow-up-questions
2. meeting-summary
3. topic-summary
4. sentiment-analysis
5. practitioner-insights
6. fill-gaps
7. brainstorm
8. company-fit
9. fact-check
10. answer-question
11. problem-solving
12. scqa
13. hypothesis-driven
14. first-principles
15. reframing
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ui.main_window import MainWindow
from prompts.templates import (
    FOLLOW_UP_QUESTIONS_PROMPT,
    MEETING_SUMMARY_PROMPT,
    TOPIC_SUMMARY_PROMPT,
    SENTIMENT_ANALYSIS_PROMPT,
    PRACTITIONER_INSIGHTS_STREAMING_PROMPT,
    FILL_IN_GAPS_PROMPT,
    BRAINSTORM_PROMPT,
    COMPANY_FIT_PROMPT,
    FACT_CHECKING_PROMPT,
    ANSWER_QUESTION_PROMPT,
)
from prompts.logic_templates import (
    PROBLEM_SOLVING_PROMPT,
    SCQA_PROMPT,
    HYPOTHESIS_DRIVEN_PROMPT,
    FIRST_PRINCIPLES_PROMPT,
    REFRAMING_PROMPT,
)


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for PyQt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    """Create MainWindow instance for testing."""
    with patch('ui.main_window.ContinuousRecorder'), \
         patch('ui.main_window.ApiClient'), \
         patch('ui.main_window.FontManager'), \
         patch('ui.main_window.logger'):
        window = MainWindow()
        yield window
        window.close()


class TestFollowUpQuestionsTemplate:
    """Test follow-up questions template setup."""

    def test_template_type(self, main_window):
        """Test follow-up questions returns correct template type."""
        result = main_window._setup_static_template(FOLLOW_UP_QUESTIONS_PROMPT)
        assert result == "follow-up-questions"

    def test_template_html_structure(self, main_window):
        """Test follow-up questions template has correct HTML structure."""
        main_window._setup_static_template(FOLLOW_UP_QUESTIONS_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'class="insight-block"' in html
        assert 'id="dynamic-content"' in html
        assert 'style="list-style-type: disc;' in html


class TestMeetingSummaryTemplate:
    """Test meeting summary template setup."""

    def test_template_type(self, main_window):
        """Test meeting summary returns correct template type."""
        result = main_window._setup_static_template(MEETING_SUMMARY_PROMPT)
        assert result == "meeting-summary"

    def test_template_html_structure(self, main_window):
        """Test meeting summary template has correct HTML structure."""
        main_window._setup_static_template(MEETING_SUMMARY_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'class="insight-block"' in html
        assert 'id="dynamic-content"' in html


class TestTopicSummaryTemplate:
    """Test topic summary template setup."""

    def test_template_type(self, main_window):
        """Test topic summary returns correct template type."""
        result = main_window._setup_static_template(TOPIC_SUMMARY_PROMPT)
        assert result == "topic-summary"

    def test_template_html_structure(self, main_window):
        """Test topic summary template has correct HTML structure."""
        main_window._setup_static_template(TOPIC_SUMMARY_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'class="insight-block"' in html
        assert 'id="dynamic-content"' in html


class TestSentimentAnalysisTemplate:
    """Test sentiment analysis template setup."""

    def test_template_type(self, main_window):
        """Test sentiment analysis returns correct template type."""
        result = main_window._setup_static_template(SENTIMENT_ANALYSIS_PROMPT)
        assert result == "sentiment-analysis"

    def test_template_html_structure(self, main_window):
        """Test sentiment analysis template has correct HTML structure."""
        main_window._setup_static_template(SENTIMENT_ANALYSIS_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'Overall Sentiment' in html
        assert 'id="overall-sentiment-value"' in html
        assert 'Key Emotional Moments' in html
        assert 'id="dynamic-content"' in html


class TestPractitionerInsightsTemplate:
    """Test practitioner insights template setup."""

    def test_template_type(self, main_window):
        """Test practitioner insights returns correct template type."""
        result = main_window._setup_static_template(PRACTITIONER_INSIGHTS_STREAMING_PROMPT)
        assert result == "practitioner-insights"

    def test_template_html_structure(self, main_window):
        """Test practitioner insights template has correct HTML structure."""
        main_window._setup_static_template(PRACTITIONER_INSIGHTS_STREAMING_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'class="insight-block"' in html
        assert 'id="dynamic-content"' in html


class TestFillGapsTemplate:
    """Test fill gaps template setup."""

    def test_template_type(self, main_window):
        """Test fill gaps returns correct template type."""
        result = main_window._setup_static_template(FILL_IN_GAPS_PROMPT)
        assert result == "fill-gaps"

    def test_template_html_structure(self, main_window):
        """Test fill gaps template has correct HTML structure with all sections."""
        main_window._setup_static_template(FILL_IN_GAPS_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'CORE THINKING' in html
        assert 'id="core-thinking-list"' in html
        assert 'GAPS' in html
        assert 'id="gaps-list"' in html
        assert 'RECOMMENDATIONS' in html
        assert 'id="recommendations-list"' in html


class TestBrainstormTemplate:
    """Test brainstorm template setup."""

    def test_template_type(self, main_window):
        """Test brainstorm returns correct template type."""
        result = main_window._setup_static_template(BRAINSTORM_PROMPT)
        assert result == "brainstorm"

    def test_template_html_structure(self, main_window):
        """Test brainstorm template has correct HTML structure with all sections."""
        main_window._setup_static_template(BRAINSTORM_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'CHALLENGE QUESTIONS' in html
        assert 'id="challenge-questions-list"' in html
        assert 'ALTERNATIVE FRAMES' in html
        assert 'id="alternative-frames-list"' in html
        assert 'PROVOCATIVE IDEAS' in html
        assert 'id="provocative-ideas-list"' in html


class TestCompanyFitTemplate:
    """Test company fit template setup."""

    def test_template_type(self, main_window):
        """Test company fit returns correct template type."""
        result = main_window._setup_static_template(COMPANY_FIT_PROMPT)
        assert result == "company-fit"

    def test_template_html_structure(self, main_window):
        """Test company fit template has correct HTML structure with all sections."""
        main_window._setup_static_template(COMPANY_FIT_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'KEY TOPICS' in html
        assert 'id="key-topics-list"' in html
        assert 'SAS VIYA CONNECTIONS' in html
        assert 'id="viya-connections-list"' in html
        assert 'MISSING CONSIDERATIONS' in html
        assert 'id="missing-considerations-list"' in html


class TestFactCheckTemplate:
    """Test fact check template setup."""

    def test_template_type(self, main_window):
        """Test fact check returns correct template type."""
        result = main_window._setup_static_template(FACT_CHECKING_PROMPT)
        assert result == "fact-check"

    def test_template_html_structure(self, main_window):
        """Test fact check template has correct HTML structure."""
        main_window._setup_static_template(FACT_CHECKING_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'Fact Check Analysis' in html
        assert 'id="fact-check-list"' in html
        assert 'list-style-type: none' in html


class TestAnswerQuestionTemplate:
    """Test answer question template setup."""

    def test_template_type(self, main_window):
        """Test answer question returns correct template type."""
        result = main_window._setup_static_template(ANSWER_QUESTION_PROMPT)
        assert result == "answer-question"

    def test_template_html_structure(self, main_window):
        """Test answer question template has correct HTML structure with all sections."""
        main_window._setup_static_template(ANSWER_QUESTION_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'ANSWER' in html
        assert 'id="answer-list"' in html
        assert 'RATIONALE' in html
        assert 'id="rationale-list"' in html
        assert 'EXAMPLES' in html
        assert 'id="examples-list"' in html


class TestProblemSolvingTemplate:
    """Test problem solving template setup."""

    def test_template_type(self, main_window):
        """Test problem solving returns correct template type."""
        result = main_window._setup_static_template(PROBLEM_SOLVING_PROMPT)
        assert result == "problem-solving"

    def test_template_html_structure(self, main_window):
        """Test problem solving template has correct HTML structure with all sections."""
        main_window._setup_static_template(PROBLEM_SOLVING_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'CORE PROBLEM/OBJECTIVE' in html
        assert 'id="core-problem-list"' in html
        assert 'LOGIC TREE COMPONENTS' in html
        assert 'id="logic-tree-list"' in html
        assert 'EVALUATION' in html
        assert 'id="evaluation-list"' in html
        assert 'CHALLENGE &amp; REFRAME' in html or 'CHALLENGE & REFRAME' in html
        assert 'id="challenge-list"' in html


class TestSCQATemplate:
    """Test SCQA framework template setup."""

    def test_template_type(self, main_window):
        """Test SCQA returns correct template type."""
        result = main_window._setup_static_template(SCQA_PROMPT)
        assert result == "scqa"

    def test_template_html_structure(self, main_window):
        """Test SCQA template has correct HTML structure with all sections."""
        main_window._setup_static_template(SCQA_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'SITUATION' in html
        assert 'id="scqa-situation-list"' in html
        assert 'COMPLICATION' in html
        assert 'id="scqa-complication-list"' in html
        assert 'QUESTION' in html
        assert 'id="scqa-question-list"' in html
        assert 'ANSWER' in html
        assert 'id="scqa-answer-list"' in html
        assert 'CRITICAL ASSESSMENT' in html
        assert 'id="scqa-assessment-list"' in html
        assert 'IMPLEMENTATION ROADMAP' in html
        assert 'id="scqa-roadmap-list"' in html


class TestHypothesisDrivenTemplate:
    """Test hypothesis driven template setup."""

    def test_template_type(self, main_window):
        """Test hypothesis driven returns correct template type."""
        result = main_window._setup_static_template(HYPOTHESIS_DRIVEN_PROMPT)
        assert result == "hypothesis-driven"

    def test_template_html_structure(self, main_window):
        """Test hypothesis driven template has correct HTML structure with all sections."""
        main_window._setup_static_template(HYPOTHESIS_DRIVEN_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'PROBLEM STATEMENT' in html
        assert 'id="hypothesis-problem-list"' in html
        assert 'HYPOTHESES' in html
        assert 'id="hypothesis-hypothesis-list"' in html
        assert 'EVIDENCE ANALYSIS' in html
        assert 'id="hypothesis-evidence-list"' in html
        assert 'HYPOTHESIS PRIORITIZATION' in html
        assert 'id="hypothesis-priority-list"' in html
        assert 'TESTING PLAN' in html
        assert 'id="hypothesis-testing-list"' in html
        assert 'DECISION FRAMEWORK' in html
        assert 'id="hypothesis-decision-list"' in html
        assert 'TRANSCRIPT ASSESSMENT' in html
        assert 'id="hypothesis-assessment-list"' in html


class TestFirstPrinciplesTemplate:
    """Test first principles template setup."""

    def test_template_type(self, main_window):
        """Test first principles returns correct template type."""
        result = main_window._setup_static_template(FIRST_PRINCIPLES_PROMPT)
        assert result == "first-principles"

    def test_template_html_structure(self, main_window):
        """Test first principles template has correct HTML structure with all sections."""
        main_window._setup_static_template(FIRST_PRINCIPLES_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'CONVENTIONAL THINKING' in html
        assert 'id="fp-conventional-list"' in html
        assert 'FUNDAMENTALS' in html
        assert 'id="fp-fundamental-list"' in html
        assert 'ASSUMPTION CHALLENGES' in html
        assert 'id="fp-assumption-list"' in html
        assert 'REBUILD FROM FIRST PRINCIPLES' in html
        assert 'id="fp-rebuild-list"' in html
        assert 'NOVEL INSIGHTS' in html
        assert 'id="fp-insight-list"' in html
        assert 'IMPLEMENTATION FRAMEWORK' in html
        assert 'id="fp-implementation-list"' in html
        assert 'METACOGNITIVE ASSESSMENT' in html
        assert 'id="fp-metacognitive-list"' in html


class TestReframingTemplate:
    """Test reframing template setup."""

    def test_template_type(self, main_window):
        """Test reframing returns correct template type."""
        result = main_window._setup_static_template(REFRAMING_PROMPT)
        assert result == "reframing"

    def test_template_html_structure(self, main_window):
        """Test reframing template has correct HTML structure with all sections."""
        main_window._setup_static_template(REFRAMING_PROMPT)
        html = main_window.output_panel.output_area.toHtml()
        assert 'REFRAMED STATEMENT' in html
        assert 'id="reframing-statement-list"' in html
        assert 'SUPPORTING POINTS' in html
        assert 'id="reframing-point-list"' in html


class TestGenericTemplate:
    """Test generic template fallback."""

    def test_template_type_unknown(self, main_window):
        """Test unknown prompt returns generic template type."""
        result = main_window._setup_static_template("UNKNOWN_PROMPT")
        assert result == "generic"

    def test_template_html_structure_unknown(self, main_window):
        """Test unknown prompt template has correct HTML structure."""
        main_window._setup_static_template("UNKNOWN_PROMPT")
        html = main_window.output_panel.output_area.toHtml()
        assert 'class="topic-section"' in html
        assert 'class="topic-title"' in html
        assert 'Results' in html
        assert 'id="dynamic-content"' in html
