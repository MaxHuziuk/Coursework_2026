from sqlalchemy.orm import Session

from app.models import Impression, Purchase, SavedImpression, User
from app.responses import AppError
from app.services.impressions import get_impression_summary


def get_user_by_id(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(404, 'User not found')
    return user


def get_user_public_profile_data(user: User) -> dict:
    return {'id': user.id, 'email': user.email, 'name': user.name, 'status': user.status}


def get_user_profile_data(user: User) -> dict:
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'status': user.status}


def get_users_data(db: Session) -> list:
    users = db.query(User).order_by(User.id).all()
    return [get_user_profile_data(user) for user in users]


def get_created_impressions_data(db: Session, user_id: int) -> list:
    impressions = db.query(Impression).filter(Impression.owner_id == user_id, Impression.active == True).order_by(
        Impression.created_at.desc()).all()
    return [get_impression_summary(item) for item in impressions]


def get_available_impressions_data(db: Session, user_id: int) -> list:
    paid = db.query(Impression).join(Purchase, Purchase.impression_id == Impression.id).filter(
        Purchase.user_id == user_id, Purchase.status == 'success', Impression.active == True,
        Impression.published == True).all()
    saved = db.query(Impression).join(SavedImpression, SavedImpression.impression_id == Impression.id).filter(
        SavedImpression.user_id == user_id, Impression.active == True, Impression.published == True).all()
    unique = {item.id: item for item in paid + saved}
    return [get_impression_summary(item) for item in unique.values()]


def get_purchased_impressions_data(db: Session, user_id: int) -> list:
    impressions = db.query(Impression).join(Purchase, Purchase.impression_id == Impression.id).filter(
        Purchase.user_id == user_id, Purchase.status == 'success', Impression.active == True,
        Impression.published == True).order_by(
        Purchase.created_at.desc()).all()
    return [get_impression_summary(item) for item in impressions]


def get_saved_impressions_data(db: Session, user_id: int) -> list:
    impressions = db.query(Impression).join(SavedImpression, SavedImpression.impression_id == Impression.id).filter(
        SavedImpression.user_id == user_id, Impression.active == True, Impression.published == True).order_by(
        SavedImpression.saved_at.desc()).all()
    return [get_impression_summary(item) for item in impressions]


def get_recommendations_data(db: Session, user_id: int) -> list:
    user = get_user_by_id(db, user_id)
    own_ids = {item.id for item in user.impressions if item.active}
    paid_ids = {
        purchase.impression_id for purchase in user.purchases if purchase.status == 'success'}
    saved_ids = {saved.impression_id for saved in user.saved_impressions}
    excluded = own_ids | paid_ids | saved_ids
    recent = [
        action.object_id for action in user.actions if action.object_type == 'impression']
    recent.reverse()

    result = db.query(Impression).filter(Impression.active == True, Impression.published == True,
                                         Impression.id.notin_(excluded), Impression.id.in_(recent)).all()
    result += db.query(Impression).filter(Impression.active == True, Impression.published == True,
                                          Impression.id.notin_(excluded), Impression.id.notin_(recent)).order_by(Impression.created_at.desc()).all()

    return [get_impression_summary(item) for item in result]
