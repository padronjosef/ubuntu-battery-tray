import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reading:
    """One battery reading. `percent` is None when the device gave no level."""

    percent: int | None
    charging: bool = False
    timestamp: float = field(default_factory=time.time)
    stale: bool = False
    detail: str = ""

    @classmethod
    def unavailable(cls, detail: str) -> "Reading":
        return cls(percent=None, detail=detail)
