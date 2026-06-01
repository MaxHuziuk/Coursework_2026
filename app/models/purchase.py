from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Purchase(Base):
    __tablename__ = 'purchases'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'), nullable=False)
    impression_id: Mapped[int] = mapped_column(
        ForeignKey('impressions.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    result_data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    user = relationship('User', back_populates='purchases')
    impression = relationship('Impression', back_populates='purchases')
