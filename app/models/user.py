from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default='user')
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default='active')
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    session_token: Mapped[str] = mapped_column(String(255), nullable=True)
    token_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True)

    impressions = relationship(
        'Impression', back_populates='owner', cascade='all, delete-orphan')
    purchases = relationship(
        'Purchase', back_populates='user', cascade='all, delete-orphan')
    saved_impressions = relationship(
        'SavedImpression', back_populates='user', cascade='all, delete-orphan')
    actions = relationship(
        'UserAction', back_populates='user', cascade='all, delete-orphan')
