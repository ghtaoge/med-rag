from datetime import datetime

from app.api.chat import ChatOrchestrator
from app.core.models import QaSession
from app.security.models import Role
from app.security.principal import Principal, PrincipalMembership


def _principal(user_id: str) -> Principal:
    return Principal(
        user_id=user_id,
        username=user_id,
        memberships=(PrincipalMembership("department", Role.READER),),
        session_id=f"session-{user_id}",
    )


def test_session_history_is_scoped_to_user(tmp_path):
    path = tmp_path / "sessions.json"
    orchestrator = ChatOrchestrator(
        None, None, None, None, redis_client=None, session_store_path=path
    )
    user_a = _principal("user-a")
    user_b = _principal("user-b")
    orchestrator._save_session(
        QaSession(
            session_id="same-session-id",
            question="private-a",
            user_id=user_a.user_id,
            department_ids=user_a.department_ids,
            created_at=datetime(2026, 7, 22, 9, 0, 0),
        )
    )
    orchestrator._save_session(
        QaSession(
            session_id="same-session-id",
            question="private-b",
            user_id=user_b.user_id,
            department_ids=user_b.department_ids,
            created_at=datetime(2026, 7, 22, 9, 1, 0),
        )
    )

    assert orchestrator.get_session("same-session-id", user_a)["question"] == "private-a"
    assert orchestrator.get_session("same-session-id", user_b)["question"] == "private-b"
    assert [item["question"] for item in orchestrator.list_sessions(user_a)] == [
        "private-a"
    ]
    assert orchestrator.delete_session("same-session-id", user_a) is True
    assert orchestrator.get_session("same-session-id", user_b) is not None
