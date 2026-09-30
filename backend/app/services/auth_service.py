"""
Auth Service — login and registration using the new UUID User model.
Field names: full_name, password_hash (not name/password).
"""

import uuid
import logging
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.core.exceptions import UnauthorizedException, ConflictException
from app.core.config import get_settings
from app.schemas.user import UserLogin, UserRegister, GoogleAuthRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:

    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def register(self, data: UserRegister) -> TokenResponse:
        if self.repo.email_exists(data.email):
            raise ConflictException(detail="Email already registered")
        user = User(
            full_name=data.name,
            email=data.email,
            password_hash=hash_password(data.password),
            role=data.role,
            is_active=True,
        )
        user = self.repo.create(user)
        from app.services.client_service import ClientService
        ClientService(self.repo.db).seed_starter_clients_for_user(user.id, user.full_name)
        logger.info("New user registered: %s (role=%s)", user.email, user.role)
        return self._tokens(user)

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.repo.get_by_email(data.email)
        if not user or not user.is_active:
            raise UnauthorizedException(detail="Invalid email or password")
        if not verify_password(data.password, user.password_hash):
            raise UnauthorizedException(detail="Invalid email or password")
        logger.info("User logged in: %s", user.email)
        return self._tokens(user)

    def google_auth(self, data: GoogleAuthRequest) -> TokenResponse:
        user = self.repo.get_by_email(data.email)
        raw_password = data.password or uuid.uuid4().hex
        if not user:
            display_name = data.name or data.email.split("@")[0].replace(".", " ").title()
            user = User(
                full_name=display_name,
                email=data.email,
                password_hash=hash_password(raw_password),
                role="ca",
                is_active=True,
            )
            user = self.repo.create(user)
            from app.services.client_service import ClientService
            ClientService(self.repo.db).seed_starter_clients_for_user(user.id, user.full_name)
            logger.info("New user registered via Google: %s", user.email)
        elif not user.is_active:
            raise UnauthorizedException(detail="Account is deactivated. Please contact support.")
        else:
            if data.password:
                user.password_hash = hash_password(data.password)
                self.repo.update(user)
        logger.info("User authenticated via Google: %s", user.email)
        return self._tokens(user)

    def _tokens(self, user: User) -> TokenResponse:
        payload = {"sub": str(user.id), "email": user.email, "role": user.role}
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )
