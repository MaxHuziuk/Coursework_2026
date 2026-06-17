import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.responses import setup_exception_handlers
from app.routes import admin, auth, impressions, user


@pytest.fixture()
def client():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(auth.router)
    test_app.include_router(user.router)
    test_app.include_router(admin.router)
    test_app.include_router(impressions.router)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def get_headers(client, email='user@example.com', password='123456', name='User'):
    response = client.post('/auth/register', json={
        'email': email,
        'password': password,
        'name': name,
    })
    assert response.status_code == 200

    response = client.post('/auth/login', json={
        'email': email,
        'password': password,
    })
    assert response.status_code == 200

    token = response.json()['data']['token']
    return {'Authorization': f'Bearer {token}'}


def impression_data(title='City route', description='Small route description', is_paid=False, cost=0, points=None):
    return {
        'title': title,
        'description': description,
        'is_paid': is_paid,
        'cost': cost,
        'points': points or [
            {
                'title': 'Start',
                'description': 'First point',
                'location_text': 'Main square',
                'latitude': 55.75,
                'longitude': 37.61,
                'order_index': 1,
            }
        ],
    }


def create_impression(client, headers, title='City route', description='Small route description',
                      is_paid=False, cost=0):
    response = client.post('/impressions', json=impression_data(title, description, is_paid, cost), headers=headers)
    assert response.status_code == 200
    return response.json()['data']['id']


def test_user_can_register_login_and_open_profile(client):
    headers = get_headers(client)

    response = client.get('/user/profile', headers=headers)

    assert response.status_code == 200
    assert response.json()['data']['email'] == 'user@example.com'
    assert 'role' not in response.json()['data']


def test_profile_requires_authorization(client):
    response = client.get('/user/profile')

    assert response.status_code == 401
    assert response.json()['status'] == 'error'


def test_duplicate_email_is_rejected(client):
    get_headers(client)

    response = client.post('/auth/register', json={
        'email': 'user@example.com',
        'password': '123456',
        'name': 'Second user',
    })

    assert response.status_code == 400
    assert response.json()['error']['message'] == 'Email already registered'


def test_paid_impression_requires_positive_cost(client):
    headers = get_headers(client)

    response = client.post('/impressions', json=impression_data(is_paid=True, cost=0), headers=headers)

    assert response.status_code == 422
    assert response.json()['status'] == 'error'
    assert 'Paid impressions require cost greater than zero' in response.json()['error']['message']


def test_free_impression_must_have_zero_cost(client):
    headers = get_headers(client)

    response = client.post('/impressions', json=impression_data(cost=15), headers=headers)

    assert response.status_code == 422
    assert 'Free impressions must have zero cost' in response.json()['error']['message']


def test_route_point_order_must_be_unique(client):
    headers = get_headers(client)
    data = impression_data(points=[
        {
            'title': 'Start',
            'description': 'First point',
            'location_text': 'Main square',
            'latitude': 55.75,
            'longitude': 37.61,
            'order_index': 1,
        },
        {
            'title': 'Finish',
            'description': 'Second point',
            'location_text': 'Park',
            'latitude': 55.76,
            'longitude': 37.62,
            'order_index': 1,
        },
    ])

    response = client.post('/impressions', json=data, headers=headers)

    assert response.status_code == 422
    assert 'Route point order must be unique' in response.json()['error']['message']


def test_impression_is_hidden_until_owner_publishes_it(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)

    catalog = client.get('/impressions', headers=visitor)
    assert catalog.status_code == 200
    assert catalog.json()['data'] == []

    response = client.post(f'/impressions/{impression_id}/save', headers=visitor)
    assert response.status_code == 400
    assert response.json()['error']['message'] == 'Impression is not published'

    response = client.patch(f'/impressions/{impression_id}/publish', headers=owner)
    assert response.status_code == 200
    assert response.json()['data']['published'] is True

    catalog = client.get('/impressions', headers=visitor)
    assert catalog.status_code == 200
    assert catalog.json()['data'][0]['id'] == impression_id

    response = client.post(f'/impressions/{impression_id}/save', headers=visitor)
    assert response.status_code == 200


def test_only_owner_can_change_impression(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)

    publish_response = client.patch(f'/impressions/{impression_id}/publish', headers=visitor)
    update_response = client.put(f'/impressions/{impression_id}', json={'title': 'New title'}, headers=visitor)
    delete_response = client.delete(f'/impressions/{impression_id}', headers=visitor)

    assert publish_response.status_code == 403
    assert update_response.status_code == 403
    assert delete_response.status_code == 403


def test_unpublished_impression_is_visible_only_for_owner(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)

    owner_response = client.get(f'/impressions/{impression_id}', headers=owner)
    visitor_response = client.get(f'/impressions/{impression_id}', headers=visitor)

    assert owner_response.status_code == 200
    assert visitor_response.status_code == 404


def test_catalog_search_filters_and_sorting(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    free_id = create_impression(client, owner, title='Museum walk', description='Art route')
    paid_id = create_impression(client, owner, title='River trip', description='Boat and water',
                                is_paid=True, cost=50)
    client.patch(f'/impressions/{free_id}/publish', headers=owner)
    client.patch(f'/impressions/{paid_id}/publish', headers=owner)

    search_response = client.get('/impressions?search=river', headers=visitor)
    free_response = client.get('/impressions?is_paid=false', headers=visitor)
    cost_response = client.get('/impressions?min_cost=10&max_cost=60', headers=visitor)
    sort_response = client.get('/impressions?sort_by=cost&order=asc', headers=visitor)

    assert [item['id'] for item in search_response.json()['data']] == [paid_id]
    assert [item['id'] for item in free_response.json()['data']] == [free_id]
    assert [item['id'] for item in cost_response.json()['data']] == [paid_id]
    assert [item['id'] for item in sort_response.json()['data']] == [free_id, paid_id]


def test_invalid_catalog_filters_return_error(client):
    headers = get_headers(client)

    range_response = client.get('/impressions?min_cost=100&max_cost=10', headers=headers)
    sort_response = client.get('/impressions?sort_by=owner&order=desc', headers=headers)

    assert range_response.status_code == 400
    assert range_response.json()['error']['message'] == 'Minimum cost cannot be greater than maximum cost'
    assert sort_response.status_code == 400
    assert sort_response.json()['error']['message'] == 'Invalid sort field'


def test_free_impression_can_be_unpublished(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)
    client.post(f'/impressions/{impression_id}/save', headers=visitor)

    response = client.patch(f'/impressions/{impression_id}/unpublish', headers=owner)

    assert response.status_code == 200
    assert response.json()['data']['published'] is False
    assert client.get('/impressions', headers=visitor).json()['data'] == []
    assert client.get('/user/saved-impressions', headers=visitor).json()['data'] == []


def test_paid_impression_cannot_be_unpublished(client):
    owner = get_headers(client)
    impression_id = create_impression(client, owner, is_paid=True, cost=100)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    response = client.patch(f'/impressions/{impression_id}/unpublish', headers=owner)

    assert response.status_code == 400
    assert response.json()['error']['message'] == 'Paid impressions cannot be unpublished'


def test_save_duplicate_and_delete_saved_impression(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    first_save = client.post(f'/impressions/{impression_id}/save', headers=visitor)
    second_save = client.post(f'/impressions/{impression_id}/save', headers=visitor)
    saved_list = client.get('/user/saved-impressions', headers=visitor)
    delete_response = client.delete(f'/impressions/{impression_id}/save', headers=visitor)
    empty_list = client.get('/user/saved-impressions', headers=visitor)
    second_delete = client.delete(f'/impressions/{impression_id}/save', headers=visitor)

    assert first_save.status_code == 200
    assert second_save.status_code == 400
    assert second_save.json()['error']['message'] == 'Impression already saved'
    assert len(saved_list.json()['data']) == 1
    assert delete_response.status_code == 200
    assert empty_list.json()['data'] == []
    assert second_delete.status_code == 404


def test_paid_impression_can_be_bought_once(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    buyer = get_headers(client, 'buyer@example.com', name='Buyer')
    impression_id = create_impression(client, owner, is_paid=True, cost=100)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    first_buy = client.post(f'/impressions/{impression_id}/buy', headers=buyer)
    second_buy = client.post(f'/impressions/{impression_id}/buy', headers=buyer)

    assert first_buy.status_code == 200
    assert first_buy.json()['data']['status'] == 'success'
    assert second_buy.status_code == 400
    assert second_buy.json()['error']['message'] == 'Impression already paid'


def test_free_impression_cannot_be_bought(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    buyer = get_headers(client, 'buyer@example.com', name='Buyer')
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    response = client.post(f'/impressions/{impression_id}/buy', headers=buyer)

    assert response.status_code == 400
    assert response.json()['error']['message'] == 'Impression is not paid'


def test_update_keeps_price_rules(client):
    owner = get_headers(client)
    impression_id = create_impression(client, owner)

    paid_response = client.put(f'/impressions/{impression_id}', json={'is_paid': True}, headers=owner)
    cost_response = client.put(f'/impressions/{impression_id}', json={'cost': 20}, headers=owner)

    assert paid_response.status_code == 400
    assert paid_response.json()['error']['message'] == 'Paid impressions require cost greater than zero'
    assert cost_response.status_code == 400
    assert cost_response.json()['error']['message'] == 'Free impressions must have zero cost'


def test_deleted_impression_is_removed_from_saved(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)
    client.post(f'/impressions/{impression_id}/save', headers=visitor)

    response = client.delete(f'/impressions/{impression_id}', headers=owner)

    assert response.status_code == 200
    assert client.get('/user/saved-impressions', headers=visitor).json()['data'] == []
    assert client.get(f'/impressions/{impression_id}', headers=visitor).status_code == 404
