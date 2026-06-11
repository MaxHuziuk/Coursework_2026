import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import check_owner, get_user
from app.models import Impression, Purchase, RoutePoint, SavedImpression, User
from app.responses import AppError, app_response
from app.schemas import ImpressionCreate, ImpressionUpdate
from app.services.impressions import (build_route_points, get_catalog_data, get_impression_by_id,
                                      get_impression_detail, validate_price)
from app.services.logs import log_action


router = APIRouter(prefix='/impressions', tags=['impressions'])


@router.get('')
def get_impressions(is_paid: bool | None = None, min_cost: float | None = None,
                    max_cost: float | None = None, search: str | None = None,
                    sort_by: str = 'created_at', order: str = 'desc',
                    current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    return app_response(get_catalog_data(db, is_paid, min_cost, max_cost, search, sort_by, order))


@router.post('')
def create_impression(data: ImpressionCreate, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    title = data.title.strip()
    description = data.description.strip()
    if not title:
        raise AppError(400, 'Title is required')
    if not description:
        raise AppError(400, 'Description is required')

    impression = Impression(owner_id=current_user.id, title=title, description=description,
                            is_paid=data.is_paid, cost=float(data.cost or 0.0))
    try:
        db.add(impression)
        db.flush()
        db.add_all(build_route_points(data.points, impression.id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(impression)
    log_action(db, current_user, 'create_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@router.get('/{impression_id}')
def get_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
    log_action(db, current_user, 'view_impression',
               'impression', impression.id)
    return app_response(get_impression_detail(impression))


@router.put('/{impression_id}')
def update_impression(impression_id: int, data: ImpressionUpdate, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
    check_owner(impression.owner_id, current_user)
    if data.title is not None:
        title = data.title.strip()
        if not title:
            raise AppError(400, 'Title is required')
        impression.title = title
    if data.description is not None:
        description = data.description.strip()
        if not description:
            raise AppError(400, 'Description is required')
        impression.description = description
    if data.is_paid is not None:
        impression.is_paid = data.is_paid
    if data.cost is not None:
        impression.cost = float(data.cost)
    validate_price(impression.is_paid, impression.cost)
    if data.points is not None:
        db.query(RoutePoint).filter(
            RoutePoint.impression_id == impression.id).delete()
        db.add_all(build_route_points(data.points, impression.id))
    db.commit()
    log_action(db, current_user, 'update_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@router.delete('/{impression_id}')
def delete_impression(impression_id: int, current_user: User = Depends(get_user),
                      db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
    check_owner(impression.owner_id, current_user)
    impression.active = False
    db.commit()
    log_action(db, current_user, 'delete_impression',
               'impression', impression.id)
    return app_response({'id': impression.id})


@router.post('/{impression_id}/buy')
def buy_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
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


@router.post('/{impression_id}/save')
def save_impression(impression_id: int, current_user: User = Depends(get_user), db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
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


@router.delete('/{impression_id}/save')
def delete_saved_impression(impression_id: int, current_user: User = Depends(get_user),
                            db: Session = Depends(get_db)):
    impression = get_impression_by_id(db, impression_id)
    saved = db.query(SavedImpression).filter(SavedImpression.user_id == current_user.id,
                                             SavedImpression.impression_id == impression_id).first()
    if not saved:
        raise AppError(404, 'Saved impression not found')
    db.delete(saved)
    db.commit()
    log_action(db, current_user, 'delete_saved_impression',
               'impression', impression.id)
    return app_response({'impression_id': impression.id})
