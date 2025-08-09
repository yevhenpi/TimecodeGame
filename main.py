import sys

from config import CFG
from models.timecode import Timecode
from modes.preroll import PrerollExactMode


def _selftest() -> None:
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


def main() -> None:
    if "--selftest" in sys.argv:
        _selftest()
        return

    from PySide6.QtWidgets import QApplication

    from ui.trainer import Trainer

    app = QApplication(sys.argv)
    trainer = Trainer()
    trainer.resize(700, 480)
    trainer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
