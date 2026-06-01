import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, UTC
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import Impression, Purchase, RoutePoint, SavedImpression, User, UserAction
from app.schemas import ActionOut, AuthRequest, ImpressionCreate, ImpressionUpdate, UserCreate, RoutePointIn

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')
PASSWORD_ITERATIONS = 100000


class AppError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.code,
                        content={'status': 'error', 'data': None, 'error': {'code': exc.code, 'message': exc.message}})


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={'status': 'error', 'data': None,
                                                              'error': {'code': exc.status_code,
                                                                        'message': exc.detail}})


@app.exception_handler(Exception)
def exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={'status': 'error', 'data': None,
                                                  'error': {'code': 500, 'message': 'Internal server error'}})


def app_response(data: Any):
    return {'status': 'success', 'data': data, 'error': None}


def get_password_hash(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return base64.b64encode(salt + key).decode()


def verify_password(password: str, password_hash: str) -> bool:
    data = base64.b64decode(password_hash.encode())
    salt, stored = data[:16], data[16:]
    key = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return hmac.compare_digest(key, stored)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def check_access(target_user_id: int, current_user: User):
    if current_user.role != 'admin' and current_user.id != target_user_id:
        raise AppError(403, 'Forbidden')


def log_action(db: Session, user: User, action_type: str, object_type: str, object_id: int,
               details: Optional[str] = None):
    action = UserAction(user_id=user.id, action_type=action_type, object_type=object_type, object_id=object_id,
                        details=details)
    db.add(action)
    db.commit()


@app.on_event('startup')
def startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.role == 'admin').first()
        if not admin:
            user = User(email='admin@travel.local', password_hash=get_password_hash('admin123'), role='admin',
                        status='active', name='Administrator')
            db.add(user)
            db.commit()


def get_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(
            status_code=401, detail='Unauthorized')
    user = db.query(User).filter(User.session_token ==
                                 token, User.status == 'active').first()
    if not user:
        raise HTTPException(
            status_code=401, detail='Unauthorized')
    return user


def get_impression_summary(impression: Impression) -> dict:
    return {'id': impression.id, 'title': impression.title, 'description': impression.description,
            'is_paid': impression.is_paid, 'cost': impression.cost, 'created_at': impression.created_at,
            'updated_at': impression.updated_at}


def get_impression_detail(impression: Impression) -> dict:
    points = []
    for point in sorted(impression.points, key=lambda item: item.order_index):
        points.append({'id': point.id, 'title': point.title, 'description': point.description,
                       'location_text': point.location_text, 'latitude': point.latitude, 'longitude': point.longitude,
                       'order_index': point.order_index})
    return {
        **get_impression_summary(impression),
        'points': points,
    }


def build_route_points(points: List[RoutePointIn], impression_id: int) -> List[RoutePoint]:
    route_points = []
    for point in points:
        route_points.append(RoutePoint(impression_id=impression_id, order_index=point.order_index, title=point.title,
                                       description=point.description, location_text=point.location_text,
                                       latitude=point.latitude, longitude=point.longitude))
    return route_points


@app.post('/auth/register')
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise AppError(400, 'Email already registered')
    user = User(email=data.email, password_hash=get_password_hash(data.password), name=data.name, role='user',
                status='active')
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, user, 'register', 'user', user.id)
    return app_response({'id': user.id, 'name': user.name, 'email': user.email})


@app.post('/auth/login')
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


@app.post('/auth/token')
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


@app.get('/users/{user_id}')
def get_user_profile(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(404, 'User not found')
    return app_response(
        {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'status': user.status})


@app.get('/users/{user_id}/role')
def get_user_role(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(404, 'User not found')
    return app_response({'role': user.role})


@app.get('/users/{user_id}/created-impressions')
def get_created_impressions(user_id: int, current_user: User = Depends(get_user),
                            db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    impressions = db.query(Impression).filter(Impression.owner_id == user_id, Impression.active == True).order_by(
        Impression.created_at.desc()).all()
    return app_response([get_impression_summary(item) for item in impressions])


@app.get('/users/{user_id}/impressions')
def get_available_impressions(user_id: int, current_user: User = Depends(get_user),
                              db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    paid = db.query(Impression).join(Purchase, Purchase.impression_id == Impression.id).filter(
        Purchase.user_id == user_id, Purchase.status == 'success', Impression.active == True).all()
    saved = db.query(Impression).join(SavedImpression, SavedImpression.impression_id == Impression.id).filter(
        SavedImpression.user_id == user_id, Impression.active == True).all()
    unique = {item.id: item for item in paid + saved}
    return app_response([get_impression_summary(item) for item in unique.values()])


@app.get('/users/{user_id}/recommendations')
def get_recommendations(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(404, 'User not found')
    own_ids = {item.id for item in user.impressions if item.active}
    paid_ids = {
        purchase.impression_id for purchase in user.purchases if purchase.status == 'success'}
    saved_ids = {saved.impression_id for saved in user.saved_impressions}
    excluded = own_ids | paid_ids | saved_ids
    recent = [
        action.object_id for action in user.actions if action.object_type == 'impression']
    recent.reverse()

    result = db.query(Impression).filter(Impression.active == True,
                                         Impression.id.notin_(excluded), Impression.id.in_(recent)).all()
    result += db.query(Impression).filter(Impression.active == True,
                                          Impression.id.notin_(excluded), Impression.id.notin_(recent)).order_by(Impression.created_at.desc()).all()

    return app_response([get_impression_summary(item) for item in result])


@app.get('/users/{user_id}/actions')
def get_actions(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    check_access(user_id, current_user)
    actions = db.query(UserAction).filter(UserAction.user_id == user_id).order_by(
        UserAction.created_at.desc()).all()
    return app_response([ActionOut.from_orm(action).dict() for action in actions])


@app.get('/impressions')
def get_impressions(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impressions = db.query(Impression).filter(
        Impression.active == True).order_by(Impression.created_at.desc()).all()
    return app_response([get_impression_summary(item) for item in impressions])


@app.post('/impressions')
def create_impression(data: ImpressionCreate, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    if data.is_paid and (data.cost is None or data.cost <= 0):
        raise AppError(400, 'Paid impressions require cost greater than zero')
    if not data.points:
        raise AppError(400, 'Route points are required')
    impression = Impression(owner_id=current_user.id, title=data.title, description=data.description,
                            is_paid=data.is_paid, cost=float(data.cost or 0.0))
    db.add(impression)
    db.commit()
    db.refresh(impression)
    points = build_route_points(data.points, impression.id)
    db.add_all(points)
    db.commit()
    db.refresh(impression)
    log_action(db, current_user, 'create_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@app.get('/impressions/{impression_id}')
def get_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = db.query(Impression).filter(
        Impression.id == impression_id, Impression.active == True).first()
    if not impression:
        raise AppError(404, 'Impression not found')
    log_action(db, current_user, 'view_impression',
               'impression', impression.id)
    return app_response(get_impression_detail(impression))


@app.put('/impressions/{impression_id}')
def update_impression(impression_id: int, data: ImpressionUpdate, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    impression = db.query(Impression).filter(
        Impression.id == impression_id, Impression.active == True).first()
    if not impression:
        raise AppError(404, 'Impression not found')
    check_access(impression.owner_id, current_user)
    if data.title is not None:
        impression.title = data.title
    if data.description is not None:
        impression.description = data.description
    if data.is_paid is not None:
        impression.is_paid = data.is_paid
        if data.is_paid and data.cost is None and impression.cost <= 0:
            raise AppError(
                400, 'Paid impressions require cost greater than zero')
    if data.cost is not None:
        impression.cost = float(data.cost)
    if data.points is not None:
        db.query(RoutePoint).filter(
            RoutePoint.impression_id == impression.id).delete()
        db.commit()
        db.add_all(build_route_points(data.points, impression.id))
    db.commit()
    log_action(db, current_user, 'update_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@app.delete('/impressions/{impression_id}')
def delete_impression(impression_id: int, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    impression = db.query(Impression).filter(
        Impression.id == impression_id, Impression.active == True).first()
    if not impression:
        raise AppError(404, 'Impression not found')
    check_access(impression.owner_id, current_user)
    impression.active = False
    db.commit()
    log_action(db, current_user, 'delete_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@app.post('/impressions/{impression_id}/buy')
def buy_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = db.query(Impression).filter(
        Impression.id == impression_id, Impression.active == True).first()
    if not impression:
        raise AppError(404, 'Impression not found')
    if not impression.is_paid:
        raise AppError(400, 'Impression is not paid')
    existing = db.query(Purchase).filter(Purchase.user_id == current_user.id, Purchase.impression_id == impression_id,
                                         Purchase.status == 'success').first()
    if existing:
        raise AppError(400, 'Impression already paid')
    result = {'status': 'success',
              'transaction_id': f'tx-{impression.id}-{current_user.id}-{int(datetime.now(UTC).timestamp())}'}
    purchase = Purchase(user_id=current_user.id, impression_id=impression_id, status='success',
                        result_data=json.dumps(result))
    db.add(purchase)
    db.commit()
    log_action(db, current_user, 'buy_impression', 'impression',
               impression.id, details=json.dumps(result))
    return app_response({'purchase_id': purchase.id, 'impression_id': impression.id, 'status': purchase.status,
                         'result': result['transaction_id']})


@app.post('/impressions/{impression_id}/save')
def save_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = db.query(Impression).filter(
        Impression.id == impression_id, Impression.active == True).first()
    if not impression:
        raise AppError(404, 'Impression not found')
    existing = db.query(SavedImpression).filter(SavedImpression.user_id == current_user.id,
                                                SavedImpression.impression_id == impression_id).first()
    if existing:
        raise AppError(400, 'Impression already saved')
    saved = SavedImpression(user_id=current_user.id,
                            impression_id=impression_id)
    db.add(saved)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(400, 'Impression already saved')
    log_action(db, current_user, 'save_impression',
               'impression', impression.id)
    return app_response({'saved_id': saved.id, 'impression_id': impression.id, 'saved_at': saved.saved_at})
