"""Advisory classifier output used by the engine without provider details."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifierResult:
    """A classifier score, or an unavailable result when no provider answered."""

    score: int | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("Classifier score must be between 0 and 100.")

    @property
    def available(self) -> bool:
        return self.score is not None
