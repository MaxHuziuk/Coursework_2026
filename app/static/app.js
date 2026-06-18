const state = {
    token: localStorage.getItem('travel_token') || '',
    profile: null,
    isAdmin: false,
    tab: 'catalog',
    filters: {
        search: '',
        is_paid: '',
        min_cost: '',
        max_cost: '',
        sort_by: 'created_at',
        order: 'desc',
    },
    catalog: [],
    created: [],
    saved: [],
    purchased: [],
    recommendations: [],
    adminUsers: [],
    adminImpressions: [],
};

const authView = document.querySelector('#authView');
const appView = document.querySelector('#appView');
const screen = document.querySelector('#screen');
const tabs = document.querySelector('#tabs');
const toast = document.querySelector('#toast');
const userBadge = document.querySelector('#userBadge');
const modal = document.querySelector('#modal');
const modalTitle = document.querySelector('#modalTitle');
const modalBody = document.querySelector('#modalBody');

function html(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function showMessage(message, type = 'ok') {
    toast.textContent = message;
    toast.className = type === 'error' ? 'toast error' : 'toast';
    toast.hidden = false;
    window.clearTimeout(showMessage.timer);
    showMessage.timer = window.setTimeout(() => {
        toast.hidden = true;
    }, 3600);
}

async function api(path, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (state.token) {
        headers.Authorization = `Bearer ${state.token}`;
    }

    const request = {
        method: options.method || 'GET',
        headers,
    };

    if (options.body !== undefined) {
        request.headers['Content-Type'] = 'application/json';
        request.body = JSON.stringify(options.body);
    }

    const response = await fetch(path, request);
    const isJson = response.headers.get('content-type')?.includes('application/json');
    const payload = isJson ? await response.json() : null;

    if (!response.ok) {
        if (response.status === 401 && state.token) {
            logout(false);
        }
        throw new Error(payload?.error?.message || payload?.detail || 'Ошибка запроса');
    }

    if (payload?.status === 'error') {
        throw new Error(payload.error?.message || 'Ошибка запроса');
    }

    return payload && Object.hasOwn(payload, 'data') ? payload.data : payload;
}

async function login(email, password) {
    const form = new URLSearchParams();
    form.set('username', email);
    form.set('password', password);

    const response = await fetch('/auth/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: form.toString(),
    });
    const payload = await response.json();

    if (!response.ok) {
        throw new Error(payload?.error?.message || payload?.detail || 'Не удалось войти');
    }

    state.token = payload.access_token;
    localStorage.setItem('travel_token', state.token);
    await loadSession();
}

async function loadSession() {
    state.profile = await api('/user/profile');
    try {
        state.adminUsers = await api('/admin/users');
        state.isAdmin = true;
    } catch (error) {
        state.isAdmin = false;
        state.adminUsers = [];
    }
    authView.hidden = true;
    appView.hidden = false;
    userBadge.textContent = `${state.profile.name} · ${state.profile.email}`;
    renderTabs();
    await setTab(state.tab);
}

function logout(show = true) {
    state.token = '';
    state.profile = null;
    state.isAdmin = false;
    localStorage.removeItem('travel_token');
    appView.hidden = true;
    authView.hidden = false;
    screen.innerHTML = '';
    if (show) {
        showMessage('Вы вышли из аккаунта');
    }
}

function availableTabs() {
    const items = [
        ['catalog', 'Каталог'],
        ['mine', 'Мои впечатления'],
        ['saved', 'Сохраненные'],
        ['purchased', 'Купленные'],
        ['recommendations', 'Рекомендации'],
    ];
    if (state.isAdmin) {
        items.push(['admin', 'Админ']);
    }
    return items;
}

function renderTabs() {
    tabs.innerHTML = availableTabs().map(([id, label]) => `
        <button class="tab ${state.tab === id ? 'active' : ''}" type="button" data-tab="${id}">
            ${label}
        </button>
    `).join('');
}

async function setTab(tab) {
    if (!availableTabs().some(([id]) => id === tab)) {
        tab = 'catalog';
    }
    state.tab = tab;
    renderTabs();
    screen.innerHTML = '<div class="empty">Загрузка...</div>';
    await loadTab(tab);
    renderScreen();
}

async function loadTab(tab) {
    if (tab === 'catalog') {
        state.catalog = await api(`/impressions${catalogQuery()}`);
    }
    if (tab === 'mine') {
        state.created = await api('/user/created-impressions');
    }
    if (tab === 'saved') {
        state.saved = await api('/user/saved-impressions');
    }
    if (tab === 'purchased') {
        state.purchased = await api('/user/purchased-impressions');
    }
    if (tab === 'recommendations') {
        state.recommendations = await api('/user/recommendations');
    }
    if (tab === 'admin') {
        state.adminUsers = await api('/admin/users');
        state.adminImpressions = await api('/admin/impressions');
    }
}

function catalogQuery() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(state.filters)) {
        if (value !== '') {
            params.set(key, value);
        }
    }
    const query = params.toString();
    return query ? `?${query}` : '';
}

function renderScreen() {
    if (state.tab === 'catalog') {
        renderCatalog();
    }
    if (state.tab === 'mine') {
        renderMine();
    }
    if (state.tab === 'saved') {
        renderList('Сохраненные впечатления', state.saved, 'saved');
    }
    if (state.tab === 'purchased') {
        renderList('Купленные впечатления', state.purchased, 'purchased');
    }
    if (state.tab === 'recommendations') {
        renderList('Рекомендации', state.recommendations, 'catalog');
    }
    if (state.tab === 'admin') {
        renderAdmin();
    }
}

function renderCatalog() {
    screen.innerHTML = `
        <section class="panel stack">
            <div>
                <h2>Каталог</h2>
                <p class="muted">Здесь показываются только активные и опубликованные впечатления.</p>
            </div>
            <form id="filtersForm" class="form-grid">
                <label>
                    Поиск
                    <input name="search" value="${html(state.filters.search)}" placeholder="Название или описание">
                </label>
                <label>
                    Тип
                    <select name="is_paid">
                        <option value="">Все</option>
                        <option value="false" ${state.filters.is_paid === 'false' ? 'selected' : ''}>Бесплатные</option>
                        <option value="true" ${state.filters.is_paid === 'true' ? 'selected' : ''}>Платные</option>
                    </select>
                </label>
                <label>
                    Цена от
                    <input name="min_cost" type="number" min="0" step="0.01" value="${html(state.filters.min_cost)}">
                </label>
                <label>
                    Цена до
                    <input name="max_cost" type="number" min="0" step="0.01" value="${html(state.filters.max_cost)}">
                </label>
                <label>
                    Сортировать по
                    <select name="sort_by">
                        ${selectOption('created_at', 'Дате создания', state.filters.sort_by)}
                        ${selectOption('updated_at', 'Дате обновления', state.filters.sort_by)}
                        ${selectOption('cost', 'Цене', state.filters.sort_by)}
                        ${selectOption('title', 'Названию', state.filters.sort_by)}
                    </select>
                </label>
                <label>
                    Порядок
                    <select name="order">
                        ${selectOption('desc', 'По убыванию', state.filters.order)}
                        ${selectOption('asc', 'По возрастанию', state.filters.order)}
                    </select>
                </label>
                <button type="submit">Применить</button>
                <button class="secondary" type="button" data-action="reset-filters">Сбросить</button>
            </form>
        </section>
        ${cards(state.catalog, 'catalog')}
    `;
}

function renderMine() {
    screen.innerHTML = `
        <section class="two-columns">
            <form id="createForm" class="panel stack">
                <div>
                    <h2>Создать впечатление</h2>
                    <p class="muted">После создания оно будет черновиком. Чтобы показать его в каталоге, нажмите "Опубликовать".</p>
                </div>
                <label>
                    Название
                    <input name="title" required>
                </label>
                <label>
                    Описание
                    <textarea name="description" required></textarea>
                </label>
                <div class="row">
                    <label>
                        <span>Платное</span>
                        <input name="is_paid" type="checkbox">
                    </label>
                    <label>
                        Цена
                        <input name="cost" type="number" min="0" step="0.01" value="0">
                    </label>
                </div>
                <div class="stack">
                    <div class="row">
                        <h3>Точки маршрута</h3>
                        <button class="secondary" type="button" data-action="add-point">Добавить точку</button>
                    </div>
                    <div id="pointsBox" class="stack">${pointFields(1)}</div>
                </div>
                <button type="submit">Создать</button>
            </form>
            <section class="stack">
                <div class="panel">
                    <h2>Мои впечатления</h2>
                    <p class="muted">Публикация управляет видимостью в каталоге. Удаление скрывает впечатление полностью.</p>
                </div>
                ${cards(state.created, 'mine')}
            </section>
        </section>
    `;
}

function renderList(title, items, mode) {
    screen.innerHTML = `
        <section class="panel">
            <h2>${title}</h2>
            <p class="muted">${items.length ? 'Найдено: ' + items.length : 'Пока здесь пусто.'}</p>
        </section>
        ${cards(items, mode)}
    `;
}

function renderAdmin() {
    screen.innerHTML = `
        <section class="panel stack">
            <div>
                <h2>Администрирование</h2>
                <p class="muted">Здесь видны пользователи и все впечатления, включая скрытые.</p>
            </div>
            <div class="stack">
                <h3>Пользователи</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Email</th>
                            <th>Имя</th>
                            <th>Роль</th>
                            <th>Статус</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>${state.adminUsers.map(adminUserRow).join('')}</tbody>
                </table>
            </div>
            <div class="stack">
                <h3>Впечатления</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Название</th>
                            <th>Автор</th>
                            <th>Статусы</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>${state.adminImpressions.map(adminImpressionRow).join('')}</tbody>
                </table>
            </div>
        </section>
    `;
}

function adminUserRow(item) {
    const nextStatus = item.status === 'active' ? 'blocked' : 'active';
    return `
        <tr>
            <td>${item.id}</td>
            <td>${html(item.email)}</td>
            <td>${html(item.name)}</td>
            <td>${html(item.role)}</td>
            <td>${statusBadge(item.status === 'active', 'active', 'blocked')}</td>
            <td>
                <button class="secondary" type="button" data-action="set-user-status" data-id="${item.id}" data-status="${nextStatus}">
                    ${nextStatus === 'active' ? 'Разблокировать' : 'Заблокировать'}
                </button>
            </td>
        </tr>
    `;
}

function adminImpressionRow(item) {
    return `
        <tr>
            <td>${item.id}</td>
            <td>${html(item.title)}</td>
            <td>${item.owner_id}</td>
            <td>
                <div class="badge-row">
                    ${statusBadge(item.active, 'active', 'inactive')}
                    ${statusBadge(item.published, 'published', 'draft')}
                    ${item.is_paid ? '<span class="badge warning">paid</span>' : '<span class="badge">free</span>'}
                </div>
            </td>
            <td>
                <button class="secondary" type="button" data-action="toggle-active" data-id="${item.id}" data-active="${item.active}">
                    ${item.active ? 'Скрыть' : 'Вернуть'}
                </button>
            </td>
        </tr>
    `;
}

function cards(items, mode) {
    if (!items.length) {
        return '<div class="empty">Нет данных для отображения.</div>';
    }
    return `<section class="grid">${items.map((item) => card(item, mode)).join('')}</section>`;
}

function card(item, mode) {
    return `
        <article class="card">
            <div class="card-head">
                <h3>${html(item.title)}</h3>
                <span class="badge ${item.is_paid ? 'warning' : ''}">${item.is_paid ? `${money(item.cost)}` : 'Бесплатно'}</span>
            </div>
            <p class="muted">${html(item.description)}</p>
            <div class="badge-row">
                ${publicationBadge(item)}
            </div>
            <div class="card-actions">
                <button class="secondary" type="button" data-action="view" data-id="${item.id}">Открыть</button>
                ${cardActions(item, mode)}
            </div>
        </article>
    `;
}

function cardActions(item, mode) {
    if (mode === 'mine') {
        if (item.published) {
            return `
                <button class="secondary" type="button" data-action="unpublish" data-id="${item.id}" ${item.is_paid ? 'disabled' : ''}>Снять</button>
                <button class="danger" type="button" data-action="delete" data-id="${item.id}">Удалить</button>
            `;
        }
        return `
            <button type="button" data-action="publish" data-id="${item.id}">Опубликовать</button>
            <button class="danger" type="button" data-action="delete" data-id="${item.id}">Удалить</button>
        `;
    }
    if (mode === 'saved') {
        return `<button class="secondary" type="button" data-action="remove-save" data-id="${item.id}">Убрать</button>`;
    }
    if (mode === 'purchased') {
        return '';
    }
    return `
        <button type="button" data-action="save" data-id="${item.id}">Сохранить</button>
        ${item.is_paid ? `<button type="button" data-action="buy" data-id="${item.id}">Купить</button>` : ''}
    `;
}

function statusBadge(value, yes, no) {
    return `<span class="badge ${value ? 'success' : 'danger'}">${value ? yes : no}</span>`;
}

function publicationBadge(item) {
    return item.published ? '<span class="badge success">Опубликовано</span>' : '';
}

function selectOption(value, label, selected) {
    return `<option value="${value}" ${selected === value ? 'selected' : ''}>${label}</option>`;
}

function pointFields(index) {
    return `
        <div class="route-point" data-point>
            <div class="row">
                <strong>Точка ${index}</strong>
                <button class="secondary" type="button" data-action="remove-point">Удалить</button>
            </div>
            <div class="route-point-grid">
                <label>
                    Название
                    <input data-field="title" required>
                </label>
                <label>
                    Порядок
                    <input data-field="order_index" type="number" min="1" value="${index}" required>
                </label>
                <label class="wide">
                    Описание
                    <input data-field="description" required>
                </label>
                <label class="wide">
                    Локация
                    <input data-field="location_text" required>
                </label>
                <label>
                    Широта
                    <input data-field="latitude" type="number" min="-90" max="90" step="0.000001">
                </label>
                <label>
                    Долгота
                    <input data-field="longitude" type="number" min="-180" max="180" step="0.000001">
                </label>
            </div>
        </div>
    `;
}

function collectPoints(form) {
    return [...form.querySelectorAll('[data-point]')].map((point) => {
        const value = (field) => point.querySelector(`[data-field="${field}"]`).value.trim();
        const latitude = value('latitude');
        const longitude = value('longitude');
        return {
            title: value('title'),
            description: value('description'),
            location_text: value('location_text'),
            latitude: latitude === '' ? null : Number(latitude),
            longitude: longitude === '' ? null : Number(longitude),
            order_index: Number(value('order_index')),
        };
    });
}

function money(value) {
    return `${Number(value || 0).toLocaleString('ru-RU')} ₽`;
}

function formatDate(value) {
    if (!value) {
        return '';
    }
    return new Date(value).toLocaleString('ru-RU');
}

async function openDetails(id) {
    const item = await api(`/impressions/${id}`);
    modalTitle.textContent = item.title;
    modalBody.innerHTML = `
        <div class="stack">
            <p>${html(item.description)}</p>
            <div class="badge-row">
                ${item.is_paid ? `<span class="badge warning">${money(item.cost)}</span>` : '<span class="badge">Бесплатно</span>'}
                ${publicationBadge(item)}
                <span class="badge">Создано: ${html(formatDate(item.created_at))}</span>
            </div>
            <div>
                <h3>Маршрут</h3>
                <div class="stack">
                    ${(item.points || []).map((point) => `
                        <div class="card">
                            <div class="card-head">
                                <h3>${point.order_index}. ${html(point.title)}</h3>
                                <span class="badge">${html(point.location_text)}</span>
                            </div>
                            <p class="muted">${html(point.description)}</p>
                            <p class="muted">${point.latitude ?? ''} ${point.longitude ?? ''}</p>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
    modal.hidden = false;
}

async function handleAction(button) {
    const action = button.dataset.action;
    const id = button.dataset.id;

    if (action === 'reset-filters') {
        state.filters = { search: '', is_paid: '', min_cost: '', max_cost: '', sort_by: 'created_at', order: 'desc' };
        await setTab('catalog');
        return;
    }
    if (action === 'add-point') {
        const box = document.querySelector('#pointsBox');
        box.insertAdjacentHTML('beforeend', pointFields(box.querySelectorAll('[data-point]').length + 1));
        return;
    }
    if (action === 'remove-point') {
        const box = document.querySelector('#pointsBox');
        if (box.querySelectorAll('[data-point]').length > 1) {
            button.closest('[data-point]').remove();
        }
        return;
    }
    if (action === 'view') {
        await openDetails(id);
        return;
    }
    if (action === 'save') {
        await api(`/impressions/${id}/save`, { method: 'POST' });
        showMessage('Впечатление сохранено');
    }
    if (action === 'buy') {
        const result = await api(`/impressions/${id}/buy`, { method: 'POST' });
        showMessage(`Покупка выполнена: ${result.result}`);
    }
    if (action === 'publish') {
        await api(`/impressions/${id}/publish`, { method: 'PATCH' });
        showMessage('Впечатление опубликовано');
    }
    if (action === 'unpublish') {
        await api(`/impressions/${id}/unpublish`, { method: 'PATCH' });
        showMessage('Впечатление снято с публикации');
    }
    if (action === 'delete') {
        if (!window.confirm('Удалить впечатление?')) {
            return;
        }
        await api(`/impressions/${id}`, { method: 'DELETE' });
        showMessage('Впечатление удалено');
    }
    if (action === 'remove-save') {
        await api(`/impressions/${id}/save`, { method: 'DELETE' });
        showMessage('Впечатление удалено из сохраненных');
    }
    if (action === 'toggle-active') {
        const next = button.dataset.active !== 'true';
        await api(`/admin/impressions/${id}/active?active=${next}`, { method: 'PATCH' });
        showMessage('Статус впечатления изменен');
    }
    if (action === 'set-user-status') {
        await api(`/admin/users/${id}/status`, {
            method: 'PATCH',
            body: { status: button.dataset.status },
        });
        showMessage('Статус пользователя изменен');
    }

    await setTab(state.tab);
}

document.querySelector('#loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
        await login(form.get('email'), form.get('password'));
        showMessage('Вы вошли в систему');
    } catch (error) {
        showMessage(error.message, 'error');
    }
});

document.querySelector('#registerForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const body = {
        name: form.get('name'),
        email: form.get('email'),
        password: form.get('password'),
    };
    try {
        await api('/auth/register', { method: 'POST', body });
        await login(body.email, body.password);
        showMessage('Аккаунт создан');
    } catch (error) {
        showMessage(error.message, 'error');
    }
});

document.querySelector('#logoutButton').addEventListener('click', () => logout());

tabs.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-tab]');
    if (!button) {
        return;
    }
    try {
        await setTab(button.dataset.tab);
    } catch (error) {
        showMessage(error.message, 'error');
    }
});

screen.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) {
        return;
    }
    try {
        button.disabled = true;
        await handleAction(button);
    } catch (error) {
        showMessage(error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

screen.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (event.target.id === 'filtersForm') {
        const form = new FormData(event.target);
        state.filters = {
            search: form.get('search').trim(),
            is_paid: form.get('is_paid'),
            min_cost: form.get('min_cost'),
            max_cost: form.get('max_cost'),
            sort_by: form.get('sort_by'),
            order: form.get('order'),
        };
        try {
            await setTab('catalog');
        } catch (error) {
            showMessage(error.message, 'error');
        }
    }

    if (event.target.id === 'createForm') {
        const form = new FormData(event.target);
        const body = {
            title: form.get('title'),
            description: form.get('description'),
            is_paid: form.get('is_paid') === 'on',
            cost: Number(form.get('cost') || 0),
            points: collectPoints(event.target),
        };
        try {
            await api('/impressions', { method: 'POST', body });
            showMessage('Впечатление создано');
            await setTab('mine');
        } catch (error) {
            showMessage(error.message, 'error');
        }
    }
});

document.querySelector('#modalClose').addEventListener('click', () => {
    modal.hidden = true;
});

modal.addEventListener('click', (event) => {
    if (event.target === modal) {
        modal.hidden = true;
    }
});

if (state.token) {
    loadSession().catch(() => logout(false));
} else {
    logout(false);
}
