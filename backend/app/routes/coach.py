from flask import Blueprint
from pydantic import Field

from app.extensions import db
from app.models import CoachConversation
from app.repositories.base import get_owned
from app.schemas.common import InModel, parse_body
from app.services.coach.service import ask
from app.utils.auth import current_user_id, protect
from app.utils.http import ok

bp = protect(Blueprint("coach", __name__, url_prefix="/coach"))


class ChatIn(InModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None


@bp.post("/chat")
def chat():
    body = parse_body(ChatIn)
    return ok(ask(current_user_id(), body.message, body.conversation_id))


@bp.get("/conversations")
def conversations():
    rows = db.session.scalars(
        db.select(CoachConversation)
        .where(CoachConversation.user_id == current_user_id())
        .order_by(CoachConversation.updated_at.desc(), CoachConversation.id.desc())
    )
    return ok(
        [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "messages": len(c.messages),
            }
            for c in rows
        ]
    )


@bp.get("/conversations/<int:conversation_id>")
def conversation(conversation_id: int):
    c = get_owned(CoachConversation, conversation_id, current_user_id())
    return ok(
        {
            "id": c.id,
            "title": c.title,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role.value,
                    "content": m.content,
                    "intent": m.intent,
                    "provider": m.provider,
                    "structured": m.structured,
                    "created_at": m.created_at.isoformat(),
                }
                for m in c.messages
            ],
        }
    )


@bp.delete("/conversations/<int:conversation_id>")
def delete_conversation(conversation_id: int):
    db.session.delete(get_owned(CoachConversation, conversation_id, current_user_id()))
    db.session.commit()
    return "", 204
