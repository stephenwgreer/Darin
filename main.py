import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

import config
from ui.main_window import MainWindow


if __name__ == "__main__":
    # Validate API keys before starting application
    try:
        config.validate_api_keys()
    except OSError as e:
        # Show error dialog before GUI starts
        app = QApplication(sys.argv)
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle("Missing API Keys")
        error_dialog.setText(str(e))
        error_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_dialog.exec()
        sys.exit(1)

    # Start application
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
