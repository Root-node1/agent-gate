"""Decision values shared by every rule."""

from dataclasses import dataclass

ALLOW = "allow"
DENY = "deny"
NEEDS_APPROVAL = "needs_approval"

SOURCE_TRUSTED = "trusted"
SOURCE_UNTRUSTED = "untrusted"
SOURCE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reason:
    """A rule that fired, with a short message safe to show an agent."""

    code: str
    message: str
    outcome: str


@dataclass(frozen=True)
class Decision:
    """The aggregate outcome and every rule that contributed to it."""

    outcome: str
    reasons: tuple[Reason, ...]

    @property
    def matched_rules(self) -> list[str]:
        return [reason.code for reason in self.reasons]
