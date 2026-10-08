from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, enum_column, user_fk
from app.models.enums import MessageRole


class CoachConversation(TimestampMixin, db.Model):
    __tablename__ = "coach_conversations"

    user_id: Mapped[int] = user_fk()
    title: Mapped[str] = mapped_column(String(160))

    messages: Mapped[list["CoachMessage"]] = relationship(
        back_populates="conversation", passive_deletes=True, order_by="CoachMessage.id"
    )


class CoachMessage(TimestampMixin, db.Model):
    __tablename__ = "coach_messages"
    __table_args__ = (
        Index("ix_coach_messages_conversation_time", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("coach_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole, "message_role"))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(40))
    # {facts, calculations, predictions, recommendations, sources} for assistant messages
    structured: Mapped[dict | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(20))

    conversation: Mapped[CoachConversation] = relationship(back_populates="messages")
