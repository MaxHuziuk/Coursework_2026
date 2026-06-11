from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class UserStatusUpdate(BaseModel):
    status: Literal['active', 'blocked']


class RoutePointIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    location_text: str = Field(min_length=1)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    order_index: int = Field(gt=0)


class RoutePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    location_text: str
    latitude: Optional[float]
    longitude: Optional[float]
    order_index: int


class ImpressionCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    is_paid: bool = False
    cost: Optional[float] = Field(default=0.0, ge=0)
    points: List[RoutePointIn] = Field(min_length=1)

    @model_validator(mode='after')
    def check_impression(self):
        if self.is_paid and (self.cost is None or self.cost <= 0):
            raise ValueError('Paid impressions require cost greater than zero')
        if not self.is_paid and self.cost not in (None, 0):
            raise ValueError('Free impressions must have zero cost')

        orders = [point.order_index for point in self.points]
        if len(orders) != len(set(orders)):
            raise ValueError('Route point order must be unique')

        return self


class ImpressionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    is_paid: Optional[bool] = None
    cost: Optional[float] = Field(default=None, ge=0)
    points: Optional[List[RoutePointIn]] = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def check_update(self):
        if self.is_paid is True and self.cost is not None and self.cost <= 0:
            raise ValueError('Paid impressions require cost greater than zero')
        if self.is_paid is False and self.cost not in (None, 0):
            raise ValueError('Free impressions must have zero cost')

        if self.points is not None:
            orders = [point.order_index for point in self.points]
            if len(orders) != len(set(orders)):
                raise ValueError('Route point order must be unique')

        return self


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_type: str
    object_type: str
    object_id: int
    created_at: datetime
    details: Optional[str] = None
