from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.responses import AppError, app_response
from app.schemas import AuthRequest, UserCreate
from app.security import create_session_token, get_password_hash, verify_password
from app.services.logs import log_action


router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/register')
def register(data: UserCreate, db: Session = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise AppError(400, 'Name is required')
    if db.query(User).filter(User.email == data.email).first():
        raise AppError(400, 'Email already registered')
    user = User(email=data.email, password_hash=get_password_hash(data.password), name=name, role='user',
                status='active')
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, user, 'register', 'user', user.id)
    return app_response({'id': user.id, 'name': user.name, 'email': user.email})


@router.post('/login')
def login(data: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise AppError(401, 'Invalid email or password')
    token = create_session_token()
    user.session_token = token
    user.token_created_at = datetime.now(UTC)
    db.commit()
    log_action(db, user, 'login', 'user', user.id)
    return app_response({'id': user.id, 'role': user.role, 'token': token})


@router.post('/token')
def login_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise AppError(401, 'Invalid email or password')
    token = create_session_token()
    user.session_token = token
    user.token_created_at = datetime.now(UTC)
    db.commit()
    log_action(db, user, 'login', 'user', user.id)
    return {'access_token': token, 'token_type': 'bearer'}
