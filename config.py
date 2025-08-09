from dataclasses import dataclass


@dataclass
class AppConfig:
    fps: int = 30  # frames per second
    hours_wrap: int = 100  # hours wrap (00..99)
    preroll_seconds: int = 2  # accept input this many seconds earlier than target
    continuous_default: bool = True


CFG = AppConfig()
