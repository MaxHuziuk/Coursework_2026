import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User
from app.responses import setup_exception_handlers
from app.routes import admin, auth, impressions, user
from app.security import get_password_hash


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
    test_app.state.test_session = test_session
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
                      is_paid=False, cost=0, points=None):
    response = client.post('/impressions', json=impression_data(title, description, is_paid, cost, points),
                           headers=headers)
    assert response.status_code == 200
    return response.json()['data']['id']


def get_admin_headers(client):
    db = client.app.state.test_session()
    admin = User(email='admin@example.com', password_hash=get_password_hash('123456'), role='admin',
                 status='active', name='Admin')
    db.add(admin)
    db.commit()
    db.close()
    return login_headers(client, 'admin@example.com', '123456')


def login_headers(client, email, password):
    response = client.post('/auth/login', json={
        'email': email,
        'password': password,
    })
    assert response.status_code == 200
    token = response.json()['data']['token']
    return {'Authorization': f'Bearer {token}'}


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


def test_saved_impressions_are_hidden_from_catalog(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    first_id = create_impression(client, owner, title='First route')
    second_id = create_impression(client, owner, title='Second route')
    client.patch(f'/impressions/{first_id}/publish', headers=owner)
    client.patch(f'/impressions/{second_id}/publish', headers=owner)
    client.post(f'/impressions/{first_id}/save', headers=visitor)

    response = client.get('/impressions', headers=visitor)

    assert response.status_code == 200
    assert [item['id'] for item in response.json()['data']] == [second_id]


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


def test_login_rejects_wrong_password(client):
    get_headers(client)

    response = client.post('/auth/login', json={
        'email': 'user@example.com',
        'password': 'wrong-password',
    })

    assert response.status_code == 401
    assert response.json()['error']['message'] == 'Invalid email or password'


def test_impression_detail_returns_route_points_in_order(client):
    owner = get_headers(client)
    points = [
        {
            'title': 'Finish',
            'description': 'Second point',
            'location_text': 'Park',
            'latitude': 55.76,
            'longitude': 37.62,
            'order_index': 2,
        },
        {
            'title': 'Start',
            'description': 'First point',
            'location_text': 'Square',
            'latitude': 55.75,
            'longitude': 37.61,
            'order_index': 1,
        },
    ]
    impression_id = create_impression(client, owner, points=points)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    response = client.get(f'/impressions/{impression_id}', headers=owner)

    assert response.status_code == 200
    data = response.json()['data']
    assert data['id'] == impression_id
    assert [point['order_index'] for point in data['points']] == [1, 2]
    assert [point['title'] for point in data['points']] == ['Start', 'Finish']


def test_owner_can_update_impression_and_replace_route_points(client):
    owner = get_headers(client)
    impression_id = create_impression(client, owner)
    new_points = [
        {
            'title': 'Museum',
            'description': 'Updated point',
            'location_text': 'Museum street',
            'latitude': 55.70,
            'longitude': 37.50,
            'order_index': 1,
        },
        {
            'title': 'Cafe',
            'description': 'Final point',
            'location_text': 'Cafe place',
            'latitude': 55.71,
            'longitude': 37.51,
            'order_index': 2,
        },
    ]

    update_response = client.put(f'/impressions/{impression_id}', json={
        'title': 'Updated route',
        'description': 'Updated description',
        'points': new_points,
    }, headers=owner)
    detail_response = client.get(f'/impressions/{impression_id}', headers=owner)

    assert update_response.status_code == 200
    data = detail_response.json()['data']
    assert data['title'] == 'Updated route'
    assert data['description'] == 'Updated description'
    assert [point['title'] for point in data['points']] == ['Museum', 'Cafe']


def test_update_rejects_duplicate_route_point_order(client):
    owner = get_headers(client)
    impression_id = create_impression(client, owner)

    response = client.put(f'/impressions/{impression_id}', json={
        'points': [
            {
                'title': 'One',
                'description': 'Point one',
                'location_text': 'Place one',
                'order_index': 1,
            },
            {
                'title': 'Two',
                'description': 'Point two',
                'location_text': 'Place two',
                'order_index': 1,
            },
        ],
    }, headers=owner)

    assert response.status_code == 422
    assert 'Route point order must be unique' in response.json()['error']['message']


def test_created_saved_purchased_and_available_lists(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    user_headers = get_headers(client, 'reader@example.com', name='Reader')
    free_id = create_impression(client, owner, title='Free route')
    paid_id = create_impression(client, owner, title='Paid route', is_paid=True, cost=75)
    client.patch(f'/impressions/{free_id}/publish', headers=owner)
    client.patch(f'/impressions/{paid_id}/publish', headers=owner)
    client.post(f'/impressions/{free_id}/save', headers=user_headers)
    client.post(f'/impressions/{paid_id}/buy', headers=user_headers)

    created = client.get('/user/created-impressions', headers=owner).json()['data']
    saved = client.get('/user/saved-impressions', headers=user_headers).json()['data']
    purchased = client.get('/user/purchased-impressions', headers=user_headers).json()['data']
    available = client.get('/user/impressions', headers=user_headers).json()['data']

    assert {item['id'] for item in created} == {free_id, paid_id}
    assert [item['id'] for item in saved] == [free_id]
    assert [item['id'] for item in purchased] == [paid_id]
    assert {item['id'] for item in available} == {free_id, paid_id}


def test_user_can_remove_saved_impression_after_it_was_unpublished(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)
    client.post(f'/impressions/{impression_id}/save', headers=visitor)
    client.patch(f'/impressions/{impression_id}/unpublish', headers=owner)

    response = client.delete(f'/impressions/{impression_id}/save', headers=visitor)

    assert response.status_code == 200
    assert response.json()['data']['impression_id'] == impression_id


def test_recommendations_use_actions_and_exclude_unavailable_items(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    user_headers = get_headers(client, 'reader@example.com', name='Reader')
    viewed_id = create_impression(client, owner, title='Viewed route')
    saved_id = create_impression(client, owner, title='Saved route')
    paid_id = create_impression(client, owner, title='Paid route', is_paid=True, cost=60)
    hidden_id = create_impression(client, owner, title='Hidden route')
    own_id = create_impression(client, user_headers, title='Own route')

    for impression_id in [viewed_id, saved_id, paid_id, own_id]:
        client.patch(f'/impressions/{impression_id}/publish', headers=owner if impression_id != own_id else user_headers)

    client.get(f'/impressions/{viewed_id}', headers=user_headers)
    client.post(f'/impressions/{saved_id}/save', headers=user_headers)
    client.post(f'/impressions/{paid_id}/buy', headers=user_headers)

    response = client.get('/user/recommendations', headers=user_headers)

    assert response.status_code == 200
    ids = {item['id'] for item in response.json()['data']}
    assert viewed_id in ids
    assert saved_id not in ids
    assert paid_id not in ids
    assert hidden_id not in ids
    assert own_id not in ids


def test_user_actions_history_contains_main_operations(client):
    headers = get_headers(client)
    impression_id = create_impression(client, headers)
    client.patch(f'/impressions/{impression_id}/publish', headers=headers)
    client.get(f'/impressions/{impression_id}', headers=headers)

    response = client.get('/user/actions', headers=headers)

    assert response.status_code == 200
    action_types = {item['action_type'] for item in response.json()['data']}
    assert {'register', 'login', 'create_impression', 'publish_impression', 'view_impression'} <= action_types


def test_non_admin_cannot_open_admin_routes(client):
    headers = get_headers(client)

    response = client.get('/admin/users', headers=headers)

    assert response.status_code == 403
    assert response.json()['error']['message'] == 'Admin access required'


def test_admin_can_list_users_and_change_user_status(client):
    user_headers = get_headers(client, 'target@example.com', name='Target')
    admin_headers = get_admin_headers(client)
    users = client.get('/admin/users', headers=admin_headers).json()['data']
    target_id = next(item['id'] for item in users if item['email'] == 'target@example.com')

    block_response = client.patch(f'/admin/users/{target_id}/status', json={'status': 'blocked'},
                                  headers=admin_headers)
    blocked_profile = client.get('/user/profile', headers=user_headers)
    activate_response = client.patch(f'/admin/users/{target_id}/status', json={'status': 'active'},
                                     headers=admin_headers)
    active_profile = client.get('/user/profile', headers=user_headers)

    assert block_response.status_code == 200
    assert block_response.json()['data']['status'] == 'blocked'
    assert blocked_profile.status_code == 401
    assert activate_response.status_code == 200
    assert active_profile.status_code == 200


def test_admin_cannot_block_himself(client):
    admin_headers = get_admin_headers(client)
    admin_profile = client.get('/user/profile', headers=admin_headers).json()['data']

    response = client.patch(f'/admin/users/{admin_profile["id"]}/status', json={'status': 'blocked'},
                            headers=admin_headers)

    assert response.status_code == 400
    assert response.json()['error']['message'] == 'Admin cannot block himself'


def test_admin_can_view_all_actions_and_user_actions(client):
    user_headers = get_headers(client, 'target@example.com', name='Target')
    admin_headers = get_admin_headers(client)
    impression_id = create_impression(client, user_headers)
    client.patch(f'/impressions/{impression_id}/publish', headers=user_headers)
    users = client.get('/admin/users', headers=admin_headers).json()['data']
    target_id = next(item['id'] for item in users if item['email'] == 'target@example.com')

    all_actions = client.get('/admin/actions', headers=admin_headers)
    user_actions = client.get(f'/admin/users/{target_id}/actions', headers=admin_headers)

    assert all_actions.status_code == 200
    assert user_actions.status_code == 200
    assert len(all_actions.json()['data']) >= len(user_actions.json()['data'])
    assert 'create_impression' in {item['action_type'] for item in user_actions.json()['data']}


def test_admin_can_change_impression_activity(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    visitor = get_headers(client, 'visitor@example.com', name='Visitor')
    admin_headers = get_admin_headers(client)
    impression_id = create_impression(client, owner)
    client.patch(f'/impressions/{impression_id}/publish', headers=owner)

    hide_response = client.patch(f'/admin/impressions/{impression_id}/active?active=false',
                                 headers=admin_headers)
    hidden_catalog = client.get('/impressions', headers=visitor)
    restore_response = client.patch(f'/admin/impressions/{impression_id}/active?active=true',
                                    headers=admin_headers)
    visible_catalog = client.get('/impressions', headers=visitor)

    assert hide_response.status_code == 200
    assert hidden_catalog.json()['data'] == []
    assert restore_response.status_code == 200
    assert [item['id'] for item in visible_catalog.json()['data']] == [impression_id]


def test_admin_impressions_include_active_and_published_statuses(client):
    owner = get_headers(client, 'owner@example.com', name='Owner')
    admin_headers = get_admin_headers(client)
    impression_id = create_impression(client, owner)

    response = client.get('/admin/impressions', headers=admin_headers)

    assert response.status_code == 200
    item = next(item for item in response.json()['data'] if item['id'] == impression_id)
    assert item['active'] is True
    assert item['published'] is False
    assert item['owner_id'] > 0
