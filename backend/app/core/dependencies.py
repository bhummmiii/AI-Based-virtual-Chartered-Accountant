"""
FastAPI Dependencies — JWT auth, DB session, role guards.
Updated for UUID primary keys on the User model.
"""

import uuid
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.core.exceptions import UnauthorizedException
from app.database.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if payload is None:
        raise UnauthorizedException(detail="Invalid or expired token")

    user_id_str: str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedException(detail="Token payload invalid")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException(detail="Token payload invalid")

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None or not user.is_active:
        raise UnauthorizedException(detail="User not found or inactive")

    return user


def require_ca_role(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("ca", "admin"):
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException(
            detail="Only Chartered Accountants can access this resource"
        )
    return current_user
