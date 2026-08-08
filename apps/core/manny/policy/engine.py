"""Deterministic authorization for all agent tool calls."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from manny.state import PrivacyState


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_AUTHENTICATION = "require_authentication"


class ToolRisk(StrEnum):
    READ = "read"
    LOCAL_WRITE = "local_write"
    FINANCIAL_WRITE = "financial_write"
    PROHIBITED = "prohibited"


class ToolRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, object] = Field(default_factory=dict)
    risk: ToolRisk = ToolRisk.READ
    exposes_sensitive_values: bool = True
    confirmed: bool = False


class PolicyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: PolicyDecision
    reason: str


class PolicyEngine:
    def evaluate(
        self,
        request: ToolRequest,
        *,
        allowed_tools: frozenset[str],
        privacy: PrivacyState,
        authenticated: bool,
    ) -> PolicyResult:
        if request.name not in allowed_tools or request.risk is ToolRisk.PROHIBITED:
            return PolicyResult(decision=PolicyDecision.DENY, reason="Tool is not approved")
        if (
            request.exposes_sensitive_values
            and privacy
            in {
                PrivacyState.PRESENT_UNKNOWN,
                PrivacyState.MULTIPLE_PEOPLE,
                PrivacyState.PRIVACY_LOCKED,
            }
            and not authenticated
        ):
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_AUTHENTICATION,
                reason="Unlock a private session before showing financial details",
            )
        if (
            request.risk in {ToolRisk.FINANCIAL_WRITE, ToolRisk.LOCAL_WRITE}
            and not request.confirmed
        ):
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_CONFIRMATION,
                reason="Explicit confirmation is required",
            )
        return PolicyResult(
            decision=PolicyDecision.ALLOW, reason="Approved by deterministic policy"
        )
