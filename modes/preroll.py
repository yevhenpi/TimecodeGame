from abc import ABC, abstractmethod

from models.timecode import Timecode


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
