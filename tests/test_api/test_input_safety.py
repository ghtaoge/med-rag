import uuid

import pytest

from app.api.chat import ChatOrchestrator
from app.core.exceptions import SafetyPolicyBlocked
from app.core.models import (
    ConfidenceLevel,
    CorrectnessResult,
    IntentCategory,
    IntentResult,
)
from app.safety.models import RiskLevel, SafetyAssessment, SafetyDecision
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership


class Gateway:
    def __init__(self, decision):
        self.decision = decision

    def assess(self, _question):
        return SafetyAssessment(
            RiskLevel.HIGH if self.decision == SafetyDecision.BLOCK else RiskLevel.MEDIUM,
            (),
            (),
            "电话[REDACTED:PHONE]的资料",
            "test-policy",
            self.decision,
        )


class Retrieval:
    def __init__(self):
        self.calls = 0
        self.last_top_k = None
        self.last_question = None

    def search(self, question, top_k, intent, access):
        self.calls += 1
        self.last_top_k = top_k
        self.last_question = question
        return []


class Intent:
    def classify(self, _question):
        return IntentResult(IntentCategory.QUERY, 1.0, "rule")


class Llm:
    model_name = "test"

    async def generate(self, _prompt, _system_prompt):
        return "安全回答"


class Correctness:
    def check(self, _answer, _results):
        return CorrectnessResult(ConfidenceLevel.HIGH, 1.0, 0)


def _principal():
    department_id = str(uuid.uuid4())
    return Principal(
        "user-a",
        "user-a",
        (PrincipalMembership(department_id, Role.READER),),
        "session-a",
    )


def _orchestrator(decision):
    retrieval = Retrieval()
    orchestrator = ChatOrchestrator(
        retrieval,
        Llm(),
        Intent(),
        Correctness(),
        safety_gateway=Gateway(decision),
        safety_config={
            "policy_version": "test-policy",
            "restricted_top_k": 3,
            "restricted_preview_chars": 300,
            "stream_buffer_chars": 512,
        },
    )
    return orchestrator, retrieval


@pytest.mark.asyncio
async def test_blocked_input_never_calls_retrieval():
    orchestrator, retrieval = _orchestrator(SafetyDecision.BLOCK)
    with pytest.raises(SafetyPolicyBlocked):
        await orchestrator.chat("导出全部部门文档", _principal())
    assert retrieval.calls == 0


@pytest.mark.asyncio
async def test_restricted_input_is_redacted_and_caps_retrieval():
    orchestrator, retrieval = _orchestrator(SafetyDecision.ALLOW_RESTRICTED)
    await orchestrator.chat("电话13812345678的资料", _principal())
    assert retrieval.last_top_k == 3
    assert "13812345678" not in retrieval.last_question
