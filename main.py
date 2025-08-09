import sys
import random
import time
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
)

# =============================
# Config & Constants
# =============================

@dataclass
class AppConfig:
    fps: int = 30                 # frames per second
    hours_wrap: int = 100         # hours wrap (00..99)
    preroll_seconds: int = 2      # accept input this many seconds earlier than target
    continuous_default: bool = True


CFG = AppConfig()


# =============================
# Timecode Model
# =============================

@dataclass(eq=True)
class Timecode:
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0

    # ---- Formatting ----
    def __str__(self) -> str:
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}:{self.frames:02d}"

    to_string = __str__  # backward-compat alias

    # ---- Construction & Conversion ----
    @staticmethod
    def random_target() -> "Timecode":
        """Generate a random target with frames fixed at 00; hours kept small by design."""
        return Timecode(
            hours=0,
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
            frames=0,
        )

    def to_total_frames(self, fps: int, hours_wrap: int) -> int:
        wrap_frames = hours_wrap * 3600 * fps
        total = ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * fps + self.frames
        return total % wrap_frames

    @staticmethod
    def from_total_frames(total_frames: int, fps: int, hours_wrap: int) -> "Timecode":
        wrap_frames = hours_wrap * 3600 * fps
        tf = total_frames % wrap_frames
        total_seconds, frames = divmod(tf, fps)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return Timecode(hours % hours_wrap, minutes, seconds, frames)

    # ---- Arithmetic ----
    def add_units(self, field: int, delta: int, fps: int, hours_wrap: int) -> None:
        """Adjust the full time by exactly one unit of the field (borrow/carry-aware).
        field: 0=hours,1=minutes,2=seconds,3=frames; delta may be +/- any int.
        """
        units_to_frames = [3600 * fps, 60 * fps, fps, 1]
        total = self.to_total_frames(fps, hours_wrap)
        total = (total + delta * units_to_frames[field]) % (hours_wrap * 3600 * fps)
        updated = Timecode.from_total_frames(total, fps, hours_wrap)
        self.hours, self.minutes, self.seconds, self.frames = (
            updated.hours, updated.minutes, updated.seconds, updated.frames
        )

    def set_field(self, field: int, value: int, fps: int, hours_wrap: int) -> None:
        if field == 0:
            self.hours = value % hours_wrap
        elif field == 1:
            self.minutes = value % 60
        elif field == 2:
            self.seconds = value % 60
        elif field == 3:
            self.frames = value % fps


# =============================
# Game Modes
# =============================

class GameMode(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def effective_target(self, target: Timecode) -> Timecode:
        pass

    def is_match(self, user: Timecode, target: Timecode) -> bool:
        return user == self.effective_target(target)


class PrerollExactMode(GameMode):
    """Match when the input equals the target shifted earlier by PREROLL seconds."""

    def __init__(self, preroll_seconds: int, fps: int, hours_wrap: int):
        self.name = f"Preroll -{preroll_seconds}s (exact)"
        self.description = (
            f"Input must equal target minus {preroll_seconds} seconds. Frames are considered."
        )
        self._preroll = preroll_seconds
        self._fps = fps
        self._wrap = hours_wrap

    def effective_target(self, target: Timecode) -> Timecode:
        total = target.to_total_frames(self._fps, self._wrap)
        total = (total - self._preroll * self._fps) % (self._wrap * 3600 * self._fps)
        return Timecode.from_total_frames(total, self._fps, self._wrap)


# =============================
# Stats Model
# =============================

@dataclass
class Stats:
    attempts: int = 0
    best_time: float | None = None
    successes: List[float] = None

    def __post_init__(self):
        if self.successes is None:
            self.successes = []

    def record_success(self, elapsed: float) -> None:
        self.attempts += 1
        self.successes.append(elapsed)
        if self.best_time is None or elapsed < self.best_time:
            self.best_time = elapsed

    def record_fail(self) -> None:
        self.attempts += 1

    @property
    def average(self) -> float | None:
        if not self.successes:
            return None
        return sum(self.successes) / len(self.successes)


# =============================
# UI - Trainer Widget
# =============================

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
    def _build_ui(self):
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
    def _advance_after_success(self):
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

    def _reset_input_only(self):
        self.input_tc = Timecode(0, 0, 0, 0)
        self.edit_mode = False
        self.active_field = 0
        self.start_time = None
        self.last_result_pending = False
        self.feedback_text = ""
        self.feedback_label.setStyleSheet("font-size: 20px;")
        self._update_display()

    def _reset_progress(self):
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
    def keyPressEvent(self, event):
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
    def _check_match(self):
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
    def _update_display(self):
        self.target_label.setText(str(self.target))
        parts = [f"{self.input_tc.hours:02d}", f"{self.input_tc.minutes:02d}", f"{self.input_tc.seconds:02d}", f"{self.input_tc.frames:02d}"]
        if self.edit_mode:
            parts[self.active_field] = f"[{parts[self.active_field]}]"
        self.input_label.setText(":".join(parts))
        self.feedback_label.setText(self.feedback_text)
        mode = "EDITING" if self.edit_mode else "VIEW"
        self.setWindowTitle(f"Timecode Trainer — {mode}")


# =============================
# Tests (non-GUI)
# =============================

def _selftest():
    cfg = CFG
    fps = cfg.fps
    wrap = cfg.hours_wrap

    # subtract_seconds / effective_target equivalence
    tgt = Timecode(0, 1, 30, 0)
    mode = PrerollExactMode(cfg.preroll_seconds, fps, wrap)
    eff = mode.effective_target(tgt)
    manual_total = tgt.to_total_frames(fps, wrap) - cfg.preroll_seconds * fps
    manual = Timecode.from_total_frames(manual_total, fps, wrap)
    assert eff == manual

    # wrap-around
    assert PrerollExactMode(2, fps, wrap).effective_target(Timecode(0, 0, 0, 0)) == Timecode(99, 59, 58, 0)

    # frames preserved when subtracting seconds
    assert PrerollExactMode(1, fps, wrap).effective_target(Timecode(1, 0, 0, 15)) == Timecode(0, 59, 59, 15)

    # add_units borrow/carry correctness
    tc = Timecode(0, 25, 0, 0)
    tc.add_units(2, -1, fps, wrap)  # seconds -1
    assert tc == Timecode(0, 24, 59, 0)

    tc = Timecode(0, 25, 59, 0)
    tc.add_units(2, +1, fps, wrap)  # seconds +1
    assert tc == Timecode(0, 26, 0, 0)

    tc = Timecode(1, 0, 10, 0)
    tc.add_units(1, -1, fps, wrap)  # minutes -1
    assert tc == Timecode(0, 59, 10, 0)

    tc = Timecode(0, 0, 0, 0)
    tc.add_units(3, -1, fps, wrap)  # frames -1
    assert tc == Timecode(99, 59, 59, fps - 1)

    print("Self-test passed.")


# =============================
# Entrypoint
# =============================

def main():
    if "--selftest" in sys.argv:
        _selftest()
        return

    app = QApplication(sys.argv)
    trainer = Trainer()
    trainer.resize(700, 480)
    trainer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
