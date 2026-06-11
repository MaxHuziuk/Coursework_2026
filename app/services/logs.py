from typing import Optional

from sqlalchemy.orm import Session

from app.models import User, UserAction
from app.schemas import ActionOut


def log_action(db: Session, user: User, action_type: str, object_type: str, object_id: int,
               details: Optional[str] = None):
    action = UserAction(user_id=user.id, action_type=action_type, object_type=object_type, object_id=object_id,
                        details=details)
    db.add(action)
    db.commit()


def get_actions_data(db: Session, user_id: int) -> list:
    actions = db.query(UserAction).filter(UserAction.user_id == user_id).order_by(
        UserAction.created_at.desc()).all()
    return [ActionOut.model_validate(action).model_dump() for action in actions]


def get_all_actions_data(db: Session) -> list:
    actions = db.query(UserAction).order_by(UserAction.created_at.desc()).all()
    return [ActionOut.model_validate(action).model_dump() for action in actions]
