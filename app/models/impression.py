from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Impression(Base):
    __tablename__ = 'impressions'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_paid: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship('User', back_populates='impressions')
    points = relationship('RoutePoint', back_populates='impression',
                          order_by='RoutePoint.order_index', cascade='all, delete-orphan')
    purchases = relationship(
        'Purchase', back_populates='impression', cascade='all, delete-orphan')
    saved_by = relationship(
        'SavedImpression', back_populates='impression', cascade='all, delete-orphan')
