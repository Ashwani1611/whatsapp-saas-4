from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.database import get_db
from app.models.user import User, UserRole
from app.utils.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == payload.email,
        User.is_active == True
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    token_data = {"sub": str(user.id), "role": user.role}

    return {
        "access_token":  create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type":    "bearer",
        "user": {
            "id":        user.id,
            "name":      user.name,
            "email":     user.email,
            "role":      user.role,
            "client_id": user.client_id
        }
    }


# ── Refresh Token ─────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)

    if token_data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(
        User.id == int(token_data["sub"]),
        User.is_active == True
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_token_data = {"sub": str(user.id), "role": user.role}

    return {
        "access_token":  create_access_token(new_token_data),
        "refresh_token": create_refresh_token(new_token_data),
        "token_type":    "bearer",
        "user": {
            "id":        user.id,
            "name":      user.name,
            "email":     user.email,
            "role":      user.role,
            "client_id": user.client_id
        }
    }


# ── Me ────────────────────────────────────────────────────────────────────────
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id":        current_user.id,
        "name":      current_user.name,
        "email":     current_user.email,
        "role":      current_user.role,
        "client_id": current_user.client_id
    }


# ── Change Password ───────────────────────────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password changed successfully"}
