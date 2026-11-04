"""Who is calling, without a user table (#13).

The token proves who issued it, and the public key is all that needs. The one thing
it cannot say is whether its owner was deactivated after it was issued, so that comes
from `BlockedOwner`. This runs before any view, so before any cached read.
"""

from dataclasses import dataclass
from uuid import UUID

from rest_framework_simplejwt.authentication import JWTStatelessUserAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .models import BlockedOwner


@dataclass(frozen=True)
class Owner:
    pk: UUID
    is_authenticated: bool = True
    is_active: bool = True


class OwnerJWTAuthentication(JWTStatelessUserAuthentication):
    def get_user(self, validated_token) -> Owner:
        try:
            owner_id = UUID(str(validated_token[api_settings.USER_ID_CLAIM]))
        except (KeyError, ValueError) as exc:
            raise InvalidToken("Token contained no recognizable user id") from exc
        if BlockedOwner.objects.filter(pk=owner_id, blocked=True).exists():
            raise AuthenticationFailed("User is inactive", code="user_inactive")
        return Owner(pk=owner_id)
