"""Authentication API Endpoints for Token Issuance and User Profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.config import settings
from comp_flow.core.database import get_db
from comp_flow.core.security import (
    create_access_token,
    get_current_user,
    verify_password,
)
from comp_flow.domain.entities import User
from comp_flow.domain.models import Token, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login", response_model=Token)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    """Authenticates user with email and password, returning signed JWT."""
    stmt = select(User).where(User.email == req.email, User.is_active.is_(True))
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        subject=user.email,
        role=user.role,
        extra_claims={"user_id": str(user.id), "full_name": user.full_name},
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_role=user.role,
        user_email=user.email,
    )


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)) -> User:
    """Returns the profile of the currently authenticated user."""
    return current_user
