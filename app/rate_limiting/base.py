from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int | None = None


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """It recods one try for the key.
        Returns if allowed inside the limit tries per window seconds"""
