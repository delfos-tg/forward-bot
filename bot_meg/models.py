from typing import List

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.orm.properties import ForeignKey

from bot_meg.database import db


class Base(DeclarativeBase):
    pass


class Forward(Base):
    __tablename__ = 'forwards'
    id: Mapped[int] = mapped_column(primary_key=True)
    from_chat: Mapped[str]
    to_chat: Mapped[str]
    to_chat_id: Mapped[str]


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    message_type: Mapped[str]
    content: Mapped[str]
    welcome_message: Mapped['WelcomeMessage'] = relationship(
        back_populates='messages'
    )
    welcome_message_id: Mapped[int] = mapped_column(
        ForeignKey('welcome_messages.id')
    )


class WelcomeMessage(Base):
    __tablename__ = 'welcome_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    chat: Mapped[str]
    messages: Mapped[List['Message']] = relationship(
        back_populates='welcome_message', cascade='all, delete-orphan'
    )


Base.metadata.create_all(db)
