from datetime import UTC, datetime, timedelta
from hashlib import sha256
import re
import secrets
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import httpx
from anyio import to_thread
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token as google_id_token
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.email import send_auth_email
from app.core.security import (
    create_access_token,
    create_oauth_state,
    decode_access_token,
    decode_oauth_state,
    hash_login_code,
    hash_password,
    is_allowed_frontend_url,
    verify_password,
)
from app.models.auth import (
    AuthActionToken,
    AuthTokenPurpose,
    AuthTokenResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    EmailChangeRequest,
    ForgotPasswordRequest,
    GoogleCodeExchange,
    LoginRequest,
    MessageResponse,
    OAuthLoginCode,
    ResetPasswordRequest,
    TokenActionRequest,
    UsernameUpdateRequest,
)
from app.models.profile import UserProfile
from app.models.user import User, UserCreate, UserResponse


router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def _ensure_auth_configured() -> None:
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )


async def _next_path(db: AsyncSession, user_id: int) -> str:
    user = await db.get(User, user_id)
    if user is None or not user.email_verified:
        return "/verify-email"
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None or profile.onboarding_completed_at is None:
        return "/onboarding"
    return "/dashboard"


async def _token_response(db: AsyncSession, user: User) -> AuthTokenResponse:
    token, expires_in = create_access_token(user.id, user.token_version)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        next_path=await _next_path(db, user.id),
        user=UserResponse.model_validate(user),
    )


def _ensure_email_delivery() -> None:
    if not settings.email_delivery_configured and not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured",
        )


async def _create_action_token(
    db: AsyncSession,
    user_id: int,
    purpose: AuthTokenPurpose,
    lifetime: timedelta,
    target_email: str | None = None,
    supersede_existing: bool = False,
) -> str | None:
    now = datetime.now(UTC)
    lock_material = f"auth-action:{user_id}:{purpose.value}".encode("utf-8")
    lock_key = int.from_bytes(sha256(lock_material).digest()[:8], signed=True)
    # Serialize the cooldown check and insert across all API workers.
    await db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    if supersede_existing:
        await db.execute(
            update(AuthActionToken)
            .where(
                AuthActionToken.user_id == user_id,
                AuthActionToken.purpose == purpose,
                AuthActionToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
    else:
        recent_token = await db.scalar(
            select(AuthActionToken.id).where(
                AuthActionToken.user_id == user_id,
                AuthActionToken.purpose == purpose,
                AuthActionToken.used_at.is_(None),
                AuthActionToken.created_at > now - timedelta(seconds=60),
            )
        )
        if recent_token is not None:
            return None
    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthActionToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_login_code(raw_token),
            target_email=target_email,
            expires_at=now + lifetime,
        )
    )
    return raw_token


async def _send_verification_email(email: str, token: str) -> None:
    link = f"{settings.frontend_url.rstrip('/')}/verify-email#token={token}"
    await send_auth_email(
        email,
        "Verifikasi email Jalur B",
        f"Verifikasi email Jalur B melalui tautan berikut (berlaku 24 jam):\n\n{link}",
    )


async def _send_password_reset_email(email: str, token: str) -> None:
    link = f"{settings.frontend_url.rstrip('/')}/reset-password#token={token}"
    await send_auth_email(
        email,
        "Reset password Jalur B",
        f"Atur ulang password Jalur B melalui tautan berikut (berlaku 30 menit):\n\n{link}",
    )


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    _ensure_auth_configured()
    _ensure_email_delivery()
    email = payload.email.lower()
    username = payload.username.strip()
    duplicate = await db.scalar(
        select(User.id).where(
            (func.lower(User.email) == email)
            | (func.lower(User.username) == username.lower())
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")

    user = User(
        username=username,
        email=email,
        password=await to_thread.run_sync(hash_password, payload.password),
        email_verified=(
            settings.debug
            and settings.auth_dev_auto_verify_email
            and not settings.email_delivery_configured
        ),
    )
    db.add(user)
    try:
        await db.flush()
        verification_token = None
        if not user.email_verified:
            verification_token = await _create_action_token(
                db,
                user.id,
                AuthTokenPurpose.verify_email,
                timedelta(hours=24),
            )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already exists",
        ) from None
    await db.refresh(user)
    if verification_token:
        background_tasks.add_task(
            _send_verification_email,
            user.email,
            verification_token,
        )
    return await _token_response(db, user)


@router.post("/login", response_model=AuthTokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthTokenResponse:
    _ensure_auth_configured()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == payload.email.strip().lower())
    )
    password_valid = (
        user is not None
        and user.password is not None
        and await to_thread.run_sync(verify_password, payload.password, user.password)
    )
    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return await _token_response(db, user)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_identity = decode_access_token(credentials.credentials)
    if token_identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id, token_version = token_identity
    user = await db.get(User, user_id)
    if user is None or user.token_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user


async def get_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return user


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    payload: TokenActionRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    action_token = await db.scalar(
        select(AuthActionToken)
        .where(
            AuthActionToken.token_hash == hash_login_code(payload.token),
            AuthActionToken.purpose == AuthTokenPurpose.verify_email,
            AuthActionToken.used_at.is_(None),
            AuthActionToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if action_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    user = await db.get(User, action_token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    now = datetime.now(UTC)
    action_token.used_at = now
    if action_token.target_email is not None:
        duplicate = await db.scalar(
            select(User.id).where(
                func.lower(User.email) == action_token.target_email.lower(),
                User.id != user.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
        user.email = action_token.target_email.lower()
        user.token_version = await db.scalar(
            update(User)
            .where(User.id == user.id)
            .values(token_version=User.token_version + 1)
            .returning(User.token_version)
        )
    user.email_verified = True
    await db.execute(
        update(AuthActionToken)
        .where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == AuthTokenPurpose.verify_email,
            AuthActionToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    if action_token.target_email is not None:
        await db.execute(
            update(AuthActionToken)
            .where(
                AuthActionToken.user_id == user.id,
                AuthActionToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        await db.execute(
            update(OAuthLoginCode)
            .where(
                OAuthLoginCode.user_id == user.id,
                OAuthLoginCode.used_at.is_(None),
            )
            .values(used_at=now)
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        ) from None
    return user


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    _ensure_email_delivery()
    if user.email_verified:
        return MessageResponse(message="Email is already verified")

    token = await _create_action_token(
        db,
        user.id,
        AuthTokenPurpose.verify_email,
        timedelta(hours=24),
    )
    await db.commit()
    if token:
        background_tasks.add_task(_send_verification_email, user.email, token)
    return MessageResponse(message="Verification email sent")


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    _ensure_email_delivery()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == str(payload.email).lower())
    )
    if user is not None:
        token = await _create_action_token(
            db,
            user.id,
            AuthTokenPurpose.reset_password,
            timedelta(minutes=30),
        )
        await db.commit()
        if token:
            background_tasks.add_task(_send_password_reset_email, user.email, token)

    return MessageResponse(
        message="If the account exists, password reset instructions have been sent"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    action_token = await db.scalar(
        select(AuthActionToken)
        .where(
            AuthActionToken.token_hash == hash_login_code(payload.token),
            AuthActionToken.purpose == AuthTokenPurpose.reset_password,
            AuthActionToken.used_at.is_(None),
            AuthActionToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if action_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    user = await db.get(User, action_token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    user.password = await to_thread.run_sync(hash_password, payload.password)
    user.token_version = await db.scalar(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .returning(User.token_version)
    )
    action_token.used_at = datetime.now(UTC)
    await db.execute(
        update(AuthActionToken)
        .where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == AuthTokenPurpose.reset_password,
            AuthActionToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )
    await db.commit()
    return MessageResponse(message="Password updated")


@router.post("/change-password", response_model=AuthTokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    if user.password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use password reset to add a password to this account",
        )
    password_valid = bool(
        payload.current_password
        and await to_thread.run_sync(
            verify_password,
            payload.current_password,
            user.password,
        )
    )
    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid",
        )

    user.password = await to_thread.run_sync(hash_password, payload.new_password)
    user.token_version = await db.scalar(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .returning(User.token_version)
    )
    await db.commit()
    return await _token_response(db, user)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
    )
    await db.commit()
    return MessageResponse(message="Logged out")


@router.patch("/username", response_model=UserResponse)
async def update_username(
    payload: UsernameUpdateRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    locked_user = await db.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    duplicate = await db.scalar(
        select(User.id).where(
            func.lower(User.username) == payload.username.lower(),
            User.id != user.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    locked_user.username = payload.username
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        ) from None
    await db.refresh(locked_user)
    return locked_user


@router.post("/change-email", response_model=MessageResponse)
async def change_email(
    payload: EmailChangeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    _ensure_email_delivery()
    locked_user = await db.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if locked_user.password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use password reset to add a password to this account",
        )
    password_valid = await to_thread.run_sync(
        verify_password,
        payload.current_password,
        locked_user.password,
    )
    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid",
        )
    target_email = str(payload.email).strip().lower()
    if target_email == locked_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is unchanged",
        )
    duplicate = await db.scalar(
        select(User.id).where(func.lower(User.email) == target_email)
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        )
    token = await _create_action_token(
        db,
        locked_user.id,
        AuthTokenPurpose.verify_email,
        timedelta(hours=24),
        target_email=target_email,
        supersede_existing=True,
    )
    await db.commit()
    background_tasks.add_task(_send_verification_email, target_email, token)
    return MessageResponse(message="Verification email sent")


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    locked_user = await db.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if locked_user.password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use password reset to add a password to this account",
        )
    if not await to_thread.run_sync(
        verify_password,
        payload.current_password,
        locked_user.password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid",
        )
    await db.delete(locked_user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/google/start")
async def google_start(return_to: str | None = Query(None)) -> RedirectResponse:
    _ensure_auth_configured()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google auth is not configured")

    callback_url = return_to or f"{settings.frontend_url.rstrip('/')}/auth/callback"
    if not is_allowed_frontend_url(callback_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid return URL")

    nonce = secrets.token_urlsafe(24)
    browser_state = secrets.token_urlsafe(24)
    state_token = create_oauth_state(callback_url, nonce, browser_state)
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.backend_url.rstrip('/')}/api/auth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state_token,
            "nonce": nonce,
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")
    response.set_cookie(
        "jalurB_oauth_state",
        browser_state,
        max_age=600,
        httponly=True,
        secure=settings.backend_url.startswith("https://"),
        samesite="lax",
        path="/api/auth/google/callback",
    )
    return response


def _redirect_with_fragment(url: str, **params: str) -> RedirectResponse:
    parts = urlsplit(url)
    fragment = dict(parse_qsl(parts.fragment))
    fragment.update(params)
    return RedirectResponse(
        urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, urlencode(fragment)))
    )


def _oauth_redirect(url: str, **params: str) -> RedirectResponse:
    response = _redirect_with_fragment(url, **params)
    response.delete_cookie("jalurB_oauth_state", path="/api/auth/google/callback")
    return response


async def _unique_google_username(db: AsyncSession, email: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", email.split("@", 1)[0].lower())[:40] or "user"
    candidate = base
    suffix = 1
    while await db.scalar(select(User.id).where(func.lower(User.username) == candidate.lower())):
        suffix += 1
        candidate = f"{base[: 49 - len(str(suffix))]}{suffix}"
    return candidate


def google_is_email_authority(email: str, hosted_domain: str | None) -> bool:
    email_domain = email.lower().rsplit("@", 1)[-1]
    normalized_hosted_domain = (hosted_domain or "").lower()
    return email_domain == "gmail.com" or (
        bool(normalized_hosted_domain) and email_domain == normalized_hosted_domain
    )


@router.get("/google/callback")
async def google_callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    oauth_state_cookie: str | None = Cookie(None, alias="jalurB_oauth_state"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    _ensure_auth_configured()
    state_data = decode_oauth_state(state)
    if state_data is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    return_to, expected_nonce, expected_browser_state = state_data
    if not is_allowed_frontend_url(return_to):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid return URL")
    if not secrets.compare_digest(oauth_state_cookie or "", expected_browser_state):
        return _oauth_redirect(return_to, error="invalid_oauth_session")
    if error or not code:
        return _oauth_redirect(return_to, error="google_auth_cancelled")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": f"{settings.backend_url.rstrip('/')}/api/auth/google/callback",
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            token_data = response.json()
        claims = await to_thread.run_sync(
            google_id_token.verify_oauth2_token,
            token_data["id_token"],
            GoogleRequest(),
            settings.google_client_id,
        )
        if claims.get("nonce") != expected_nonce or claims.get("email_verified") is not True:
            return _oauth_redirect(return_to, error="google_identity_unverified")
        google_sub = str(claims["sub"])
        email = str(claims["email"]).lower()
    except (GoogleAuthError, httpx.HTTPError, KeyError, TypeError, ValueError):
        return _oauth_redirect(return_to, error="google_auth_failed")
    is_authoritative_email = google_is_email_authority(
        email,
        str(claims["hd"]) if claims.get("hd") else None,
    )
    user = await db.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        user = await db.scalar(
            select(User).where(func.lower(User.email) == email).with_for_update()
        )
        if user is not None:
            if not is_authoritative_email:
                return _oauth_redirect(return_to, error="account_link_requires_login")
            if user.google_sub is not None and user.google_sub != google_sub:
                return _oauth_redirect(return_to, error="account_link_conflict")
            user.google_sub = google_sub
            # An unverified password account may have been pre-registered by someone
            # else. The verified Google identity takes ownership without retaining
            # that potentially hostile credential.
            if not user.email_verified:
                user.password = None
                user.token_version += 1
            user.email_verified = True
        else:
            user = User(
                username=await _unique_google_username(db, email),
                email=email,
                password=None,
                google_sub=google_sub,
                email_verified=True,
            )
            db.add(user)

    try:
        await db.flush()
        raw_code = secrets.token_urlsafe(32)
        db.add(
            OAuthLoginCode(
                user_id=user.id,
                code_hash=hash_login_code(raw_code),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return _oauth_redirect(return_to, error="account_link_conflict")
    return _oauth_redirect(return_to, code=raw_code)


@router.post("/google/exchange", response_model=AuthTokenResponse)
async def google_exchange(
    payload: GoogleCodeExchange,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    _ensure_auth_configured()
    login_code = await db.scalar(
        select(OAuthLoginCode)
        .where(
            OAuthLoginCode.code_hash == hash_login_code(payload.code),
            OAuthLoginCode.used_at.is_(None),
            OAuthLoginCode.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if login_code is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")

    login_code.used_at = datetime.now(UTC)
    user = await db.get(User, login_code.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    await db.commit()
    return await _token_response(db, user)
