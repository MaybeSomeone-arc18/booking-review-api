from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    # admins are seeded, never self-registered
    role: UserRole = UserRole.customer


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: UserRole


class BookingCreate(BaseModel):
    provider_id: int
    start_time: datetime
    end_time: datetime


class BookingPatch(BaseModel):
    status: BookingStatus


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    provider_id: int
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    created_at: datetime


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = ""


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    rating: int
    text: str
    created_at: datetime


class SummarizeRequest(BaseModel):
    # admins pick a provider; providers always summarise their own reviews
    provider_id: int | None = None


class JobOut(BaseModel):
    job_id: str
    status: str
    result: str | None = None
