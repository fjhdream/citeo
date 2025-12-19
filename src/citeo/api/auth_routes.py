"""Authentication routes for token management.

Provides endpoints for token generation, refresh, and revocation.
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from citeo.auth.exceptions import TokenExpiredError
from citeo.auth.jwt_auth import create_access_token, create_refresh_token, decode_token
from citeo.auth.models import RefreshTokenRequest, RevokeTokenRequest, TokenResponse
from citeo.auth.token_storage import get_token_storage
from citeo.config.settings import settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model.

    Reason: For future extension to support username/password login.
    Currently accepts API key for token generation.
    """

    api_key: str = Field(..., description="API key for authentication")


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


@router.post("/token", response_model=TokenResponse)
async def generate_token(request: LoginRequest) -> TokenResponse:
    """Generate access and refresh tokens using API key.

    This endpoint exchanges an API key for JWT tokens.
    The access token is short-lived (1 hour) for API access.
    The refresh token is long-lived (7 days) for getting new access tokens.

    Args:
        request: Login request with API key.

    Returns:
        Access and refresh tokens.

    Raises:
        HTTPException: 401 if API key is invalid.
    """
    # Validate API key
    if not settings.auth_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key authentication not configured",
        )

    configured_key = settings.auth_api_key.get_secret_value()
    if request.api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Validate JWT secret is configured
    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT authentication not configured",
        )

    jwt_secret = settings.auth_jwt_secret.get_secret_value()

    # Generate access token
    access_token_delta = timedelta(minutes=settings.auth_jwt_access_token_expiry_minutes)
    access_token = create_access_token(
        secret_key=jwt_secret,
        expires_delta=access_token_delta,
        subject="default",
    )

    # Generate refresh token
    refresh_token_delta = timedelta(days=settings.auth_jwt_refresh_token_expiry_days)
    refresh_token, token_id, expires_at = create_refresh_token(
        secret_key=jwt_secret,
        expires_delta=refresh_token_delta,
        subject="default",
    )

    # Store refresh token for revocation tracking
    token_storage = get_token_storage()
    await token_storage.store_refresh_token(
        token_id=token_id,
        user_id="default",
        expires_at=expires_at,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_token_delta.total_seconds()),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> TokenResponse:
    """Refresh access token using refresh token.

    Exchange a valid refresh token for a new access token and refresh token.
    The old refresh token is automatically revoked.

    Args:
        request: Refresh token request.

    Returns:
        New access and refresh tokens.

    Raises:
        HTTPException: 401 if refresh token is invalid or revoked.
    """
    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT authentication not configured",
        )

    jwt_secret = settings.auth_jwt_secret.get_secret_value()

    # Decode and validate refresh token
    try:
        payload = decode_token(request.refresh_token, jwt_secret)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Verify it's a refresh token
    if payload.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    # Verify token is not revoked
    if not payload.jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing ID",
        )

    token_storage = get_token_storage()
    is_valid = await token_storage.is_token_valid(payload.jti)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked or is invalid",
        )

    # Revoke old refresh token
    await token_storage.revoke_token(payload.jti)

    # Generate new access token
    access_token_delta = timedelta(minutes=settings.auth_jwt_access_token_expiry_minutes)
    access_token = create_access_token(
        secret_key=jwt_secret,
        expires_delta=access_token_delta,
        subject=payload.sub,
    )

    # Generate new refresh token
    refresh_token_delta = timedelta(days=settings.auth_jwt_refresh_token_expiry_days)
    new_refresh_token, token_id, expires_at = create_refresh_token(
        secret_key=jwt_secret,
        expires_delta=refresh_token_delta,
        subject=payload.sub,
    )

    # Store new refresh token
    await token_storage.store_refresh_token(
        token_id=token_id,
        user_id=payload.sub,
        expires_at=expires_at,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=int(access_token_delta.total_seconds()),
    )


@router.post("/revoke", response_model=MessageResponse)
async def revoke_token(request: RevokeTokenRequest) -> MessageResponse:
    """Revoke a refresh token.

    Once revoked, the refresh token can no longer be used to get new access tokens.
    This does not revoke existing access tokens (they will expire naturally).

    Args:
        request: Token revocation request.

    Returns:
        Success message.

    Raises:
        HTTPException: 401 if token is invalid.
    """
    if not settings.auth_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT authentication not configured",
        )

    jwt_secret = settings.auth_jwt_secret.get_secret_value()

    # Decode token to get jti
    try:
        payload = decode_token(request.token, jwt_secret)
    except TokenExpiredError:
        # Allow revoking expired tokens
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke expired token",
        )

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only revoke refresh tokens",
        )

    if not payload.jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing ID",
        )

    # Revoke token
    token_storage = get_token_storage()
    revoked = await token_storage.revoke_token(payload.jti)

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found or already revoked",
        )

    return MessageResponse(message="Token revoked successfully")


@router.get("/health", response_model=MessageResponse)
async def auth_health() -> MessageResponse:
    """Check authentication service health.

    Returns:
        Health status message.
    """
    token_storage = get_token_storage()
    token_count = token_storage.get_token_count()

    return MessageResponse(
        message=f"Authentication service is healthy. Active tokens: {token_count}"
    )
