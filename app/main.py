from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models import User
from app.responses import setup_exception_handlers
from app.routes import admin, auth, impressions, user
from app.security import get_password_hash


app = FastAPI()
setup_exception_handlers(app)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(impressions.router)


def update_db_schema():
    with engine.begin() as connection:
        columns = {column['name']
                   for column in inspect(connection).get_columns('impressions')}
        if 'published' not in columns:
            connection.execute(
                text('ALTER TABLE impressions ADD COLUMN published BOOLEAN NOT NULL DEFAULT 0'))


@app.on_event('startup')
def startup():
    Base.metadata.create_all(bind=engine)
    update_db_schema()
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == 'admin').first()
        if not admin_user:
            user = User(email='admin@travel.local', password_hash=get_password_hash('admin123'), role='admin',
                        status='active', name='Administrator')
            db.add(user)
            db.commit()
