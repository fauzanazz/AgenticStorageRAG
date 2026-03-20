"""OAuth provider module.

Extensible OAuth authentication system. Each provider implements
AbstractOAuthProvider. See base.py for the interface contract.
"""

from app.domain.auth.oauth.base import (
    AbstractOAuthProvider,
    OAuthTokens,
    OAuthUserInfo,
)
from app.domain.auth.oauth.google import GoogleOAuthProvider

__all__ = [
    "AbstractOAuthProvider",
    "GoogleOAuthProvider",
    "OAuthTokens",
    "OAuthUserInfo",
]
