from dataclasses import dataclass
import random


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
            updated.hours,
            updated.minutes,
            updated.seconds,
            updated.frames,
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
