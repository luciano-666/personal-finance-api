from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from typing import Annotated, Any
from datetime import timedelta, datetime, timezone
import jwt

from app.schemas import (
    Token,
    UserPublic,
    Message,
    NewPassword,
    UserUpdate,
    TokenWithRefresh,
    RefreshTokenRequest,
    LogoutRequest,
)
from app.api.deps import SessionDep, CurrentUser, TokenDep
from app import crud
from app.core.config import settings
from app.core import security
from app.utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    verify_password_reset_token,
    send_email,
)
from app.core.redis import get_redis

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
async def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    # Refresh token — tạo raw + hash, lưu hash vào DB
    raw_refresh, refresh_hash = security.create_refresh_token()
    await crud.create_refresh_token(
        session=session,
        user_id=user.id,
        token_hash=refresh_hash,
        expires_in_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )

    # return Token(
    #     access_token=security.create_access_token(
    #         user.id, expires_delta=access_token_expires
    #     )
    # )
    return TokenWithRefresh(access_token=access_token, refresh_token=raw_refresh)


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post("/password-recovery/{email}")
async def recover_password(email: str, session: SessionDep) -> Message:
    """
    Password Recovery
    """
    user = await crud.get_user_by_email(session=session, email=email)

    # Always return the same response to prevent email enumeration attacks
    # Only send email if user actually exists
    if user:
        password_reset_token = generate_password_reset_token(email=email)
        email_data = generate_reset_password_email(
            email_to=user.email, email=email, token=password_reset_token
        )
        send_email(
            email_to=user.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return Message(
        message="If that email is registered, we sent a password recovery link"
    )


@router.post("/reset-password/")
async def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = await crud.get_user_by_email(session=session, email=email)
    if not user:
        # Don't reveal that the user doesn't exist - use same error as invalid token
        raise HTTPException(status_code=400, detail="Invalid token")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    user_in_update = UserUpdate(password=body.new_password)
    await crud.update_user(
        session=session,
        db_user=user,
        user_in=user_in_update,
    )
    return Message(message="Password updated successfully")


@router.post("/login/refresh", response_model=Token)
async def refresh_access_token(session: SessionDep, body: RefreshTokenRequest) -> Any:
    """
    Đổi refresh token hợp lệ lấy access token mới.
    Refresh token cũ bị revoke ngay sau khi dùng (rotation).
    """
    token_hash = security.hash_token(body.refresh_token)
    rt = await crud.get_refresh_token_by_hash(session=session, token_hash=token_hash)

    if not rt:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if rt.is_revoked:
        # Token đã bị dùng lại — có thể bị đánh cắp, revoke toàn bộ
        await crud.revoke_all_user_refresh_tokens(session=session, user_id=rt.user_id)
        raise HTTPException(
            status_code=401,
            detail="Refresh token reuse detected. All sessions have been revoked.",
        )
    if rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Revoke token cũ (rotation)
    await crud.revoke_refresh_token(session=session, refresh_token=rt)

    # Tạo access token mới
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        rt.user_id, expires_delta=access_token_expires
    )

    return Token(access_token=access_token)


@router.post("/logout", response_model=Message)
async def logout(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    token: TokenDep,
    body: LogoutRequest = LogoutRequest(),
) -> Any:
    """
    Logout:
    1. Blacklist access token hiện tại vào Redis (TTL = thời gian còn lại).
    2. Revoke refresh token nếu client gửi kèm.
    """
    redis = await get_redis()

    # 1. Blacklist access token
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        exp: int = payload.get("exp", 0)
        ttl = exp - int(datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await redis.setex(f"blacklist:access:{token}", ttl, "1")
    except Exception:
        pass  # Token đã expired thì không cần blacklist
    # 2. Revoke refresh token nếu có
    if body.refresh_token:
        token_hash = security.hash_token(body.refresh_token)
        rt = await crud.get_refresh_token_by_hash(
            session=session, token_hash=token_hash
        )
        if rt and rt.user_id == current_user.id and not rt.is_revoked:
            await crud.revoke_refresh_token(session=session, refresh_token=rt)

    return Message(message="Logged out successfully")


@router.post("/logout/all", response_model=Message)
async def logout_all_sessions(
    session: SessionDep, current_user: CurrentUser, token: TokenDep
) -> Any:
    """
    Logout khỏi tất cả thiết bị:
    1. Blacklist access token hiện tại.
    2. Revoke toàn bộ refresh token của user.
    """
    redis = await get_redis()

    # Blacklist access token hiện tại
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        exp: int = payload.get("exp", 0)
        ttl = exp - int(datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await redis.setex(f"blacklist:access:{token}", ttl, "1")
    except Exception:
        pass

    # Revoke tất cả refresh token
    count = await crud.revoke_all_user_refresh_tokens(
        session=session, user_id=current_user.id
    )

    return Message(message=f"Logged out from all {count} session(s)")
