from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Impression, RoutePoint, SavedImpression
from app.responses import AppError
from app.schemas import RoutePointIn


def get_impression_by_id(db: Session, impression_id: int, active_only: bool = True) -> Impression:
    query = db.query(Impression).filter(Impression.id == impression_id)
    if active_only:
        query = query.filter(Impression.active == True)
    impression = query.first()
    if not impression:
        raise AppError(404, 'Impression not found')
    return impression


def validate_price(is_paid: bool, cost: Optional[float]):
    if is_paid and (cost is None or cost <= 0):
        raise AppError(400, 'Paid impressions require cost greater than zero')
    if cost is not None and cost < 0:
        raise AppError(400, 'Cost cannot be negative')
    if not is_paid and cost not in (None, 0):
        raise AppError(400, 'Free impressions must have zero cost')


def get_impression_summary(impression: Impression) -> dict:
    return {'id': impression.id, 'title': impression.title, 'description': impression.description,
            'is_paid': impression.is_paid, 'cost': impression.cost, 'published': impression.published,
            'created_at': impression.created_at, 'updated_at': impression.updated_at}


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
    for point in sorted(points, key=lambda item: item.order_index):
        route_points.append(RoutePoint(impression_id=impression_id, order_index=point.order_index, title=point.title.strip(),
                                       description=point.description.strip(), location_text=point.location_text.strip(),
                                       latitude=point.latitude, longitude=point.longitude))
    return route_points


def apply_impression_filters(query, is_paid: Optional[bool], min_cost: Optional[float],
                             max_cost: Optional[float], search: Optional[str]):
    if is_paid is not None:
        query = query.filter(Impression.is_paid == is_paid)

    if min_cost is not None:
        if min_cost < 0:
            raise AppError(400, 'Minimum cost cannot be negative')
        query = query.filter(Impression.cost >= min_cost)

    if max_cost is not None:
        if max_cost < 0:
            raise AppError(400, 'Maximum cost cannot be negative')
        query = query.filter(Impression.cost <= max_cost)

    if min_cost is not None and max_cost is not None and min_cost > max_cost:
        raise AppError(400, 'Minimum cost cannot be greater than maximum cost')

    if search:
        text = f'%{search.strip()}%'
        query = query.filter(or_(Impression.title.ilike(text),
                                 Impression.description.ilike(text)))

    return query


def apply_impression_sort(query, sort_by: str, order: str):
    fields = {
        'created_at': Impression.created_at,
        'updated_at': Impression.updated_at,
        'cost': Impression.cost,
        'title': Impression.title,
    }

    if sort_by not in fields:
        raise AppError(400, 'Invalid sort field')
    if order not in {'asc', 'desc'}:
        raise AppError(400, 'Invalid sort order')

    field = fields[sort_by]
    if order == 'desc':
        field = field.desc()

    return query.order_by(field)


def get_catalog_data(db: Session, is_paid: Optional[bool] = None, min_cost: Optional[float] = None,
                     max_cost: Optional[float] = None, search: Optional[str] = None,
                     sort_by: str = 'created_at', order: str = 'desc',
                     user_id: Optional[int] = None) -> list:
    query = db.query(Impression).filter(
        Impression.active == True, Impression.published == True)
    if user_id is not None:
        saved = db.query(SavedImpression.impression_id).filter(
            SavedImpression.user_id == user_id)
        query = query.filter(Impression.id.notin_(saved))
    query = apply_impression_filters(query, is_paid, min_cost, max_cost, search)
    query = apply_impression_sort(query, sort_by, order)
    impressions = query.all()
    return [get_impression_summary(item) for item in impressions]


def get_admin_impressions_data(db: Session) -> list:
    impressions = db.query(Impression).order_by(Impression.created_at.desc()).all()
    return [{
        **get_impression_summary(item),
        'owner_id': item.owner_id,
        'active': item.active,
        'published': item.published,
    } for item in impressions]
