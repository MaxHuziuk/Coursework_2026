from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.responses import AppError


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')


def get_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail='Unauthorized')
    user = db.query(User).filter(User.session_token == token, User.status == 'active').first()
    if not user:
        raise HTTPException(status_code=401, detail='Unauthorized')
    return user


def require_admin(current_user: User):
    if current_user.role != 'admin':
        raise AppError(403, 'Admin access required')


def check_owner(target_user_id: int, current_user: User):
    if current_user.id != target_user_id:
        raise AppError(403, 'Only owner can change this impression')
