"""
Auth Router — Login & Registration endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.auth_service import AuthService
from app.schemas.user import UserLogin, UserRegister, GoogleAuthRequest, TokenResponse
from app.schemas.common import APIResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=APIResponse[TokenResponse],
    status_code=201,
    summary="Register a new CA account",
)
def register(data: UserRegister, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.register(data)
    return APIResponse(data=result, message="Registration successful")


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    summary="Login with email & password",
)
def login(data: UserLogin, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.login(data)
    return APIResponse(data=result, message="Login successful")


@router.post(
    "/google",
    response_model=APIResponse[TokenResponse],
    summary="Login or register with Google account",
)
def google_auth(data: GoogleAuthRequest, db: Session = Depends(get_db)):
    service = AuthService(db)
    result = service.google_auth(data)
    return APIResponse(data=result, message="Google authentication successful")

