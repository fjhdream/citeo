"""Authentication-related Pydantic models."""

from datetime import datetime

from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    """Authenticated user information.

    Reason: Single-user mode simplifies this to just auth method tracking.
    Can be extended for multi-user scenarios.
    """

    user_id: str = Field(default="default", description="User identifier")
    auth_method: str = Field(..., description="How user was authenticated: 'api_key' or 'jwt'")
    authenticated_at: datetime = Field(default_factory=datetime.utcnow)


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str = Field(default="default", description="Subject (user ID)")
    exp: datetime = Field(..., description="Expiration time")
    iat: datetime = Field(default_factory=datetime.utcnow, description="Issued at")
    type: str = Field(default="access", description="Token type: 'access' or 'refresh'")
    jti: str | None = Field(default=None, description="JWT ID (for revocation)")


class TokenResponse(BaseModel):
    """Response model for token generation endpoint."""

    access_token: str = Field(..., description="Access token for API calls")
    refresh_token: str = Field(..., description="Refresh token for getting new access tokens")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str = Field(..., description="Refresh token to exchange")


class RevokeTokenRequest(BaseModel):
    """Request model for token revocation."""

    token: str = Field(..., description="Refresh token to revoke")
