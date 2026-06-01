from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class RoutePointIn(BaseModel):
    title: str
    description: str
    location_text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    order_index: Optional[int] = None


class RoutePointOut(BaseModel):
    id: int
    title: str
    description: str
    location_text: str
    latitude: Optional[float]
    longitude: Optional[float]
    order_index: int

    class Config:
        orm_mode = True


class ImpressionCreate(BaseModel):
    title: str
    description: str
    is_paid: bool = False
    cost: Optional[float] = 0.0
    points: List[RoutePointIn]


class ImpressionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_paid: Optional[bool] = None
    cost: Optional[float] = None
    points: Optional[List[RoutePointIn]] = None


class ActionOut(BaseModel):
    id: int
    action_type: str
    object_type: str
    object_id: int
    created_at: datetime
    details: Optional[str] = None

    class Config:
        orm_mode = True
