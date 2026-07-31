from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
import httpx

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.rate_limit import rate_limit
from app.models.user import User
from app.schemas.user import (
    UserCreate, UserLogin, TokenResponse, RefreshRequest, GoogleAuthRequest,
    VerifyEmailRequest, ResendOTPRequest, VerifyEmailResponse, OTPResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
    SendLoginOTPRequest, LoginWithOTPRequest, ChangePasswordRequest,
)
from app.services.auth_service import AuthService
from app.services.otp_service import OTPService
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def set_auth_cookies(response: Response, access_token: str, refresh_token: str, request: Request) -> None:
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_EXPIRATION_MINUTES * 60,
        httponly=False,
        samesite="lax",
        path="/",
        secure=is_https,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.JWT_REFRESH_EXPIRATION_DAYS * 86400,
        httponly=False,
        samesite="lax",
        path="/",
        secure=is_https,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


@router.post("/register", response_model=TokenResponse, dependencies=[rate_limit(3, 60)])
def register(data: UserCreate, response: Response, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.register(data)
    set_auth_cookies(response, result["access_token"], result["refresh_token"], request)
    return result


@router.post("/login", response_model=TokenResponse, dependencies=[rate_limit(10, 60)])
def login(data: UserLogin, response: Response, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.login(data.email, data.password)
    set_auth_cookies(response, result["access_token"], result["refresh_token"], request)
    return result


@router.post("/refresh", response_model=TokenResponse, dependencies=[rate_limit(5, 60)])
def refresh(data: RefreshRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.refresh(data.refresh_token)
    set_auth_cookies(response, result["access_token"], result["refresh_token"], request)
    return result


@router.post("/logout")
def logout(data: RefreshRequest, response: Response, db: Session = Depends(get_db)):
    service = AuthService(db)
    service.logout(data.refresh_token)
    clear_auth_cookies(response)
    return {"detail": "Logged out successfully"}


@router.post("/google", response_model=TokenResponse)
def google_auth(data: GoogleAuthRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    resp = httpx.get(
        f"https://oauth2.googleapis.com/tokeninfo?id_token={data.token}"
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    google_data = resp.json()
    service = AuthService(db)
    result = service.google_auth(
        email=google_data["email"],
        full_name=google_data.get("name", google_data["email"]),
        provider_id=google_data["sub"],
    )
    set_auth_cookies(response, result["access_token"], result["refresh_token"], request)
    return result


@router.get("/me", response_model=TokenResponse)
def get_me(current_user: User = Depends(get_current_user)):
    from app.core.security import create_access_token

    access_token = create_access_token({"sub": str(current_user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": "",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "avatar_url": current_user.avatar_url,
            "role": current_user.role.value if hasattr(current_user.role, 'value') else current_user.role,
            "is_active": current_user.is_active,
            "verified": current_user.verified if hasattr(current_user, 'verified') else False,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
    }


# ── Email OTP Verification ──


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    dependencies=[rate_limit(5, 60)],
)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.verified:
        return {"message": "Email already verified."}

    service = OTPService(db)
    service.verify(user.id, data.otp)
    return {"message": "Email verified successfully."}


@router.post(
    "/resend-otp",
    response_model=OTPResponse,
    dependencies=[rate_limit(3, 60)],
)
def resend_otp(data: ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified.",
        )

    service = OTPService(db)
    result = service.resend_otp(user.id)
    return OTPResponse(**result)


# ── Password Reset (future-ready) ──


@router.post(
    "/forgot-password",
    dependencies=[rate_limit(3, 300)],
)
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        return {"message": "If that email is registered, a reset link has been sent."}

    from app.core.security import create_access_token
    from datetime import timedelta

    reset_token = create_access_token(
        {"sub": str(user.id), "purpose": "password_reset"},
        expires_delta=timedelta(hours=1),
    )

    from app.services.email_service import email_service
    email_service.send_password_reset(user.email, reset_token, user.full_name)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post(
    "/reset-password",
    dependencies=[rate_limit(3, 300)],
)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    from app.core.security import decode_access_token, hash_password

    payload = decode_access_token(data.token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.hashed_password = hash_password(data.password)
    db.commit()
    return {"message": "Password reset successfully."}


# ── Sign in with OTP ──


@router.post(
    "/send-login-otp",
    response_model=OTPResponse,
    dependencies=[rate_limit(3, 60)],
)
def send_login_otp(data: SendLoginOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        return OTPResponse(message="If that email exists, an OTP has been sent.", email=data.email, sent=False)

    service = OTPService(db)
    result = service.create_and_send_otp(user)
    return OTPResponse(**result)


@router.post(
    "/login-with-otp",
    response_model=TokenResponse,
    dependencies=[rate_limit(5, 60)],
)
def login_with_otp(data: LoginWithOTPRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.login_with_otp(data.email, data.otp)
    set_auth_cookies(response, result["access_token"], result["refresh_token"], request)
    return result


# ── Change Password (authenticated) ──


@router.put(
    "/change-password",
    dependencies=[rate_limit(5, 60)],
)
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    service.change_password(current_user, data.current_password, data.new_password)
    return {"message": "Password changed successfully."}
