import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout

from config import CFG
from models.timecode import Timecode
from models.stats import Stats
from modes.preroll import GameMode, PrerollExactMode


class Trainer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timecode Input Trainer")
        self.setFocusPolicy(Qt.StrongFocus)

        # Core state
        self.mode: GameMode = PrerollExactMode(CFG.preroll_seconds, CFG.fps, CFG.hours_wrap)
        self.continuous: bool = CFG.continuous_default

        self.target: Timecode = Timecode.random_target()
        self.input_tc: Timecode = Timecode(0, 0, 0, 0)
        self.active_field: int = 0  # 0=H,1=M,2=S,3=F

        # Flow state
        self.edit_mode: bool = False
        self.last_result_pending: bool = False
        self.last_was_success: bool = False
        self.start_time: float | None = None
        self.feedback_text: str = ""

        # Stats
        self.stats = Stats()

        self._build_ui()
        self._update_display()
        self.setFocus()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Target display
        self.target_label = QLabel()
        self.target_label.setStyleSheet("font-size: 64px; font-weight: bold;")
        self.target_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(QLabel("Target Timecode:"), alignment=Qt.AlignCenter)
        layout.addWidget(self.target_label)

        # Input display
        self.input_label = QLabel()
        self.input_label.setStyleSheet("font-size: 64px; font-weight: bold;")
        self.input_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(QLabel("Your Input: (press '*' to start editing)"), alignment=Qt.AlignCenter)
        layout.addWidget(self.input_label)

        # Feedback label
        self.feedback_label = QLabel("")
        self.feedback_label.setStyleSheet("font-size: 20px;")
        self.feedback_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.feedback_label)

        # Stats row
        stats_layout = QHBoxLayout()
        self.attempts_label = QLabel("Attempts: 0")
        self.average_time_label = QLabel("Average time: --")
        self.best_time_label = QLabel("Best time: --")
        stats_layout.addWidget(self.attempts_label)
        stats_layout.addWidget(self.average_time_label)
        stats_layout.addWidget(self.best_time_label)
        stats_layout.setAlignment(Qt.AlignCenter)
        layout.addLayout(stats_layout)

        # Instructions
        instructions_text = (
            "Space resets progress;\n\n"
            f"Mode: {self.mode.name}. {self.mode.description}"
        )
        instructions = QLabel(instructions_text)
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)

        self.setLayout(layout)

    # ---------- Resets ----------
    def _advance_after_success(self) -> None:
        if self.last_was_success and self.continuous:
            self.target = Timecode.random_target()
        # prepare for next entry
        self.input_tc = Timecode(0, 0, 0, 0)
        self.edit_mode = True
        self.active_field = 0
        self.start_time = time.time()
        self.last_result_pending = False
        self.feedback_text = ""
        self.feedback_label.setStyleSheet("font-size: 20px;")
        self._update_display()

    def _reset_input_only(self) -> None:
        self.input_tc = Timecode(0, 0, 0, 0)
        self.edit_mode = False
        self.active_field = 0
        self.start_time = None
        self.last_result_pending = False
        self.feedback_text = ""
        self.feedback_label.setStyleSheet("font-size: 20px;")
        self._update_display()

    def _reset_progress(self) -> None:
        self.stats = Stats()
        self.attempts_label.setText("Attempts: 0")
        self.average_time_label.setText("Average time: --")
        self.best_time_label.setText("Best time: --")
        self.feedback_text = "Progress reset. Press * to start."
        self.input_tc = Timecode(0, 0, 0, 0)
        self.edit_mode = False
        self.active_field = 0
        self.start_time = None
        self.last_result_pending = False
        self.feedback_label.setStyleSheet("font-size: 20px;")
        self._update_display()

    # ---------- Events ----------
    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        text = event.text()

        # Space: full progress reset
        if key == Qt.Key_Space:
            self._reset_progress()
            event.accept()
            return

        # '*' behavior: if a success result is pending, consume it to advance; otherwise toggle edit mode
        if text == "*":
            if self.last_result_pending:
                self._advance_after_success()
            else:
                if not self.edit_mode:
                    self.edit_mode = True
                    self.start_time = time.time()
                else:
                    self.edit_mode = False
                self._update_display()
            return

        # If success result is waiting, ignore other input until user presses '*'
        if self.last_result_pending:
            return

        if not self.edit_mode:
            return

        handled = False
        if key == Qt.Key_Left:
            self.active_field = (self.active_field - 1) % 4
            handled = True
        elif key == Qt.Key_Right:
            self.active_field = (self.active_field + 1) % 4
            handled = True
        elif key == Qt.Key_Tab:
            if event.modifiers() & Qt.ShiftModifier:
                self.active_field = (self.active_field - 1) % 4
            else:
                self.active_field = (self.active_field + 1) % 4
            handled = True
        elif key == Qt.Key_Up:
            self.input_tc.add_units(self.active_field, +1, CFG.fps, CFG.hours_wrap)
            handled = True
        elif key == Qt.Key_Down:
            self.input_tc.add_units(self.active_field, -1, CFG.fps, CFG.hours_wrap)
            handled = True
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._check_match()
            handled = True
        elif key == Qt.Key_Escape:
            self._reset_input_only()
            handled = True
        elif key == Qt.Key_Backspace:
            self.input_tc.set_field(self.active_field, 0, CFG.fps, CFG.hours_wrap)
            handled = True
        elif text.isdigit():
            current_val = [
                self.input_tc.hours,
                self.input_tc.minutes,
                self.input_tc.seconds,
                self.input_tc.frames,
            ][self.active_field]
            digit = int(text)
            new_val = current_val * 10 + digit if current_val < 10 else digit
            self.input_tc.set_field(self.active_field, new_val, CFG.fps, CFG.hours_wrap)
            handled = True

        if handled:
            event.accept()
        self._update_display()

    # ---------- Game Logic ----------
    def _check_match(self) -> None:
        eff = self.mode.effective_target(self.target)
        if self.input_tc == eff:
            elapsed = time.time() - self.start_time if self.start_time else 0.0
            self.stats.record_success(elapsed)
            avg = self.stats.average
            if avg is not None:
                self.average_time_label.setText(f"Average time: {avg:.2f}s")
            if self.stats.best_time is not None:
                self.best_time_label.setText(f"Best time: {self.stats.best_time:.2f}s")
            self.feedback_text = f"SUCCESS in {elapsed:.2f}s — press * to continue"
            self.feedback_label.setStyleSheet("font-size: 20px; color: #2ecc71;")
            self.last_was_success = True
            self.last_result_pending = True  # lock until '*'
        else:
            self.stats.record_fail()
            self.feedback_text = "NO MATCH — keep trying"
            self.feedback_label.setStyleSheet("font-size: 20px; color: #e74c3c;")
            self.last_was_success = False
            self.last_result_pending = False  # continue editing same target

        self.attempts_label.setText(f"Attempts: {self.stats.attempts}")
        self._update_display()

    # ---------- Render ----------
    def _update_display(self) -> None:
        self.target_label.setText(str(self.target))
        parts = [
            f"{self.input_tc.hours:02d}",
            f"{self.input_tc.minutes:02d}",
            f"{self.input_tc.seconds:02d}",
            f"{self.input_tc.frames:02d}",
        ]
        if self.edit_mode:
            parts[self.active_field] = f"[{parts[self.active_field]}]"
        self.input_label.setText(":".join(parts))
        self.feedback_label.setText(self.feedback_text)
        mode = "EDITING" if self.edit_mode else "VIEW"
        self.setWindowTitle(f"Timecode Trainer — {mode}")
