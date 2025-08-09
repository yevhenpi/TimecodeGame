from dataclasses import dataclass
from typing import List


@dataclass
class Stats:
    attempts: int = 0
    best_time: float | None = None
    successes: List[float] | None = None

    def __post_init__(self) -> None:
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
