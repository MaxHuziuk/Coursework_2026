import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_user, require_admin
from app.models import User
from app.responses import AppError, app_response
from app.schemas import UserStatusUpdate
from app.services.impressions import get_admin_impressions_data, get_impression_by_id
from app.services.logs import get_actions_data, get_all_actions_data, log_action
from app.services.users import get_user_by_id, get_user_profile_data, get_users_data


router = APIRouter(prefix='/admin', tags=['admin'])


@router.get('/users')
def get_admin_users(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    return app_response(get_users_data(db))


@router.get('/users/{user_id}/profile')
def get_admin_user_profile(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    user = get_user_by_id(db, user_id)
    return app_response(get_user_profile_data(user))


@router.get('/users/{user_id}/role')
def get_admin_user_role(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    user = get_user_by_id(db, user_id)
    return app_response({'role': user.role})


@router.get('/users/{user_id}/status')
def get_admin_user_status(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    user = get_user_by_id(db, user_id)
    return app_response({'id': user.id, 'status': user.status})


@router.patch('/users/{user_id}/status')
def change_user_status(user_id: int, data: UserStatusUpdate, current_user: User = Depends(get_user),
                       db: Session = Depends(get_db)):
    require_admin(current_user)
    user = get_user_by_id(db, user_id)
    if user.id == current_user.id and data.status != 'active':
        raise AppError(400, 'Admin cannot block himself')
    user.status = data.status
    db.commit()
    log_action(db, current_user, 'change_user_status',
               'user', user.id, details=json.dumps({'status': data.status}))
    return app_response({'id': user.id, 'status': user.status})


@router.get('/users/{user_id}/actions')
def get_admin_user_actions(user_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    get_user_by_id(db, user_id)
    return app_response(get_actions_data(db, user_id))


@router.get('/actions')
def get_admin_actions(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    return app_response(get_all_actions_data(db))


@router.get('/impressions')
def get_admin_impressions(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    require_admin(current_user)
    return app_response(get_admin_impressions_data(db))


@router.patch('/impressions/{impression_id}/active')
def change_impression_active(impression_id: int, active: bool, current_user: User = Depends(get_user),
                             db: Session = Depends(get_db)):
    require_admin(current_user)
    impression = get_impression_by_id(db, impression_id, active_only=False)
    impression.active = active
    db.commit()
    log_action(db, current_user, 'change_impression_active',
               'impression', impression.id, details=json.dumps({'active': active}))
    return app_response({'id': impression.id, 'active': impression.active})
