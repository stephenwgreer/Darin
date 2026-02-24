"""
SessionHistoryDialog — modal dialog for browsing saved sessions.

Shows a list of past sessions on the left and a tabbed detail view on the
right.  Each tab contains either the raw transcript or the plain-text output
of one analysis prompt.

Usage:
    dialog = SessionHistoryDialog(session_store, parent=main_window)
    dialog.exec()
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from storage.models import SessionData
from storage.session_store import SessionStore

# Human-readable labels for known prompt IDs shown as tab titles
_PROMPT_LABEL: dict[str, str] = {
    "topic_summary": "Topic Summary",
    "meeting_summary": "Meeting Summary",
    "sentiment_analysis": "Sentiment Analysis",
    "practitioner_insights": "Practitioner Insights",
    "follow_up_questions": "Follow-up Questions",
    "first_principles": "First Principles",
    "reframing": "Reframing",
    "scqa": "SCQA",
    "hypothesis_driven": "Hypothesis Thinking",
    "gaps_reasoning": "Gaps in Reasoning",
    "brainstorming": "Brainstorming",
    "issue_tree": "Issue Tree",
    "company_fit": "Company Fit",
    "fact_check": "Fact Check",
    "answer_question": "Answer Question",
}


def _prompt_label(prompt_id: str) -> str:
    """Return a human-readable label for a prompt ID."""
    return _PROMPT_LABEL.get(prompt_id, prompt_id.replace("_", " ").title())


def _format_duration(duration_s: int) -> str:
    """Format duration in seconds to a human-readable string."""
    minutes = duration_s // 60
    if minutes < 1:
        return f"{duration_s}s"
    return f"{minutes} min"


class SessionHistoryDialog(QDialog):
    """Modal dialog listing saved sessions with a tabbed detail view."""

    def __init__(self, session_store: SessionStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = session_store
        # Maps list row index → session id (int)
        self._session_ids: list[int] = []

        self.setWindowTitle("Session History")
        self.resize(900, 600)
        self._build_ui()
        self._load_sessions()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct all widgets and layouts."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        # ---- Left panel: session list + delete button ----
        left_panel = QWidget()
        left_panel.setMinimumWidth(280)
        left_panel.setMaximumWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)

        sessions_label = QLabel("Sessions")
        sessions_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        left_layout.addWidget(sessions_label)

        self._list_widget = QListWidget()
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self._list_widget)

        self._delete_button = QPushButton("Delete Session")
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        left_layout.addWidget(self._delete_button)

        splitter.addWidget(left_panel)

        # ---- Right panel: detail view ----
        self._right_panel = QWidget()
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self._title_label = QLabel("")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(self._title_label)

        self._duration_label = QLabel("")
        self._duration_label.setStyleSheet("color: #888; font-size: 12px;")
        right_layout.addWidget(self._duration_label)

        self._tab_widget = QTabWidget()
        right_layout.addWidget(self._tab_widget)

        # Placeholder shown when no session is selected
        self._empty_label = QLabel("No sessions saved yet.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-size: 13px;")
        right_layout.addWidget(self._empty_label)

        self._tab_widget.hide()
        self._title_label.hide()
        self._duration_label.hide()

        splitter.addWidget(self._right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        """Populate the session list from the store."""
        try:
            sessions = self._store.list_sessions()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load history:\n{e}")
            return

        self._list_widget.clear()
        self._session_ids = []

        if not sessions:
            self._empty_label.show()
            self._tab_widget.hide()
            self._title_label.hide()
            self._duration_label.hide()
            return

        for session in sessions:
            assert session.id is not None
            self._session_ids.append(session.id)
            duration_str = _format_duration(session.duration_s)
            count = session.analysis_count
            analyses_str = f"{count} {'analysis' if count == 1 else 'analyses'}"
            item = QListWidgetItem(f"{session.title}\n{duration_str} · {analyses_str}")
            self._list_widget.addItem(item)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_session_selected(self, row: int) -> None:
        """Load and display a session when its list item is clicked."""
        if row < 0 or row >= len(self._session_ids):
            return

        session_id = self._session_ids[row]
        try:
            session = self._store.get_session(session_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load session:\n{e}")
            return

        if session is None:
            return

        self._populate_detail(session)
        self._delete_button.setEnabled(True)

    def _populate_detail(self, session: SessionData) -> None:
        """Fill the right panel with session detail."""
        self._title_label.setText(session.title)
        self._title_label.show()

        duration_str = _format_duration(session.duration_s)
        self._duration_label.setText(f"Duration: {duration_str}")
        self._duration_label.show()

        self._tab_widget.clear()
        self._empty_label.hide()
        self._tab_widget.show()

        # Transcript tab
        transcript_edit = QTextEdit()
        transcript_edit.setReadOnly(True)
        transcript_edit.setPlainText(session.transcript or "(no transcript)")
        self._tab_widget.addTab(transcript_edit, "Transcript")

        # One tab per analysis output
        for analysis in session.analyses:
            tab_edit = QTextEdit()
            tab_edit.setReadOnly(True)
            tab_edit.setPlainText(analysis.output_text)
            label = _prompt_label(analysis.prompt_id)
            self._tab_widget.addTab(tab_edit, label)

    def _on_delete_clicked(self) -> None:
        """Confirm and delete the currently selected session."""
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._session_ids):
            return

        session_id = self._session_ids[row]
        item = self._list_widget.item(row)
        title = item.text().splitlines()[0] if item else "this session"

        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete '{title}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._store.delete_session(session_id)
        except Exception as e:
            QMessageBox.warning(self, "Delete Failed", f"Could not delete session:\n{e}")
            return

        # Refresh the list and clear the right panel
        self._tab_widget.clear()
        self._tab_widget.hide()
        self._title_label.hide()
        self._duration_label.hide()
        self._delete_button.setEnabled(False)
        self._load_sessions()
