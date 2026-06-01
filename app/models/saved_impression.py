from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SavedImpression(Base):
    __tablename__ = 'saved_impressions'
    __table_args__ = (UniqueConstraint(
        'user_id', 'impression_id', name='uix_user_impression'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'), nullable=False)
    impression_id: Mapped[int] = mapped_column(
        ForeignKey('impressions.id'), nullable=False)
    saved_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    user = relationship('User', back_populates='saved_impressions')
    impression = relationship('Impression', back_populates='saved_by')
