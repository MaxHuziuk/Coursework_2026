from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_user
from app.models import User
from app.responses import app_response
from app.services.logs import get_actions_data
from app.services.users import (get_available_impressions_data, get_created_impressions_data,
                                get_purchased_impressions_data, get_recommendations_data,
                                get_saved_impressions_data, get_user_public_profile_data)


router = APIRouter(prefix='/user', tags=['user'])


@router.get('/profile')
def get_current_user_profile(current_user: User = Depends(get_user)):
    return app_response(get_user_public_profile_data(current_user))


@router.get('/created-impressions')
def get_current_user_created_impressions(current_user: User = Depends(get_user),
                                         db: Session = Depends(get_db)):
    return app_response(get_created_impressions_data(db, current_user.id))


@router.get('/impressions')
def get_current_user_available_impressions(current_user: User = Depends(get_user),
                                           db: Session = Depends(get_db)):
    return app_response(get_available_impressions_data(db, current_user.id))


@router.get('/purchased-impressions')
def get_current_user_purchased_impressions(current_user: User = Depends(get_user),
                                           db: Session = Depends(get_db)):
    return app_response(get_purchased_impressions_data(db, current_user.id))


@router.get('/saved-impressions')
def get_current_user_saved_impressions(current_user: User = Depends(get_user),
                                       db: Session = Depends(get_db)):
    return app_response(get_saved_impressions_data(db, current_user.id))


@router.get('/recommendations')
def get_current_user_recommendations(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    return app_response(get_recommendations_data(db, current_user.id))


@router.get('/actions')
def get_current_user_actions(current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    return app_response(get_actions_data(db, current_user.id))
