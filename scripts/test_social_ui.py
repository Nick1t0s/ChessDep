"""Browser smoke and social actions test suite for ChessDep.

Tests:
  - Gift modal recipient picker (friends initial, user search, selection, direct nickname)
  - Search race guard (slow earlier query does not overwrite newer query)
  - Gift error handling (modal stays open on error, closes on success, no double submit)
  - Lobby quick friend invite (POST /invites/{code}/send, no duplicate sends, feedback)
  - Retained public link (copy, cancel, countdown)
  - Lobby ?friend=id preselection
  - Friends page flow: incoming accept/reject, outgoing cancel, search/request, remove
  - Notifications flow: topbar bell, read-all, notifications.html pagination/read, polling toast
  - Mobile layout screenshots and overflow validation

Usage:
  /tmp/codex-venv-chessdep-ui/bin/python scripts/test_social_ui.py --root . --artifacts /tmp/chessdep-ui-artifacts
"""

from __future__ import annotations

import argparse
import copy
import traceback
import glob
import json
import os
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright


MOCK_INVENTORY = [
    {
        'id': 101,
        'status': 'owned',
        'exterior': 'FN',
        'equipped_slot': None,
        'def': {
            'id': 'd1',
            'kind': 'piece_skin',
            'piece_type': 'Q',
            'rarity': 'epic',
            'asset': {'type': 'stub', 'color': '#ffd700'},
            'value': 1000,
            'name': 'Golden Queen',
        },
    }
]

MOCK_FRIENDS = [
    {'id': 2, 'login': 'bob', 'elo': 1250},
    {'id': 3, 'login': 'charlie', 'elo': 1300},
]

MOCK_REQUESTS = {
    'incoming': [{'id': 4, 'login': 'dave', 'elo': 1100}],
    'outgoing': [{'id': 5, 'login': 'eve', 'elo': 1150}],
}

MOCK_SEARCH_USERS = [
    {'id': 2, 'login': 'bob', 'elo': 1250, 'relationship': 'friend'},
    {'id': 3, 'login': 'charlie', 'elo': 1300, 'relationship': 'friend'},
    {'id': 6, 'login': 'bobcat', 'elo': 1400, 'relationship': 'none'},
    {'id': 7, 'login': 'charlotte', 'elo': 1500, 'relationship': 'none'},
]

MOCK_NOTIFICATIONS_PAGE_1 = {
    'items': [
        {
            'id': 10,
            'kind': 'friend_request',
            'title': 'Заявка в друзья',
            'body': 'Пользователь dave хочет добавить вас в друзья',
            'href': '/user.html?login=dave',
            'read': False,
            'created_at': '2026-11-12T10:00:00Z',
        },
        {
            'id': 9,
            'kind': 'match_invite',
            'title': 'Приглашение в партию',
            'body': 'bob пригласил вас сыграть',
            'href': '/invite.html?code=testinvite123',
            'read': False,
            'created_at': '2026-11-12T09:30:00Z',
        },
    ],
    'next_cursor': 8,
    'unread_count': 2,
}

MOCK_NOTIFICATIONS_PAGE_2 = {
    'items': [
        {
            'id': 8,
            'kind': 'market_sale',
            'title': 'Предмет продан',
            'body': 'Ваш лот куплен за 500 кристаллов',
            'href': '/inventory.html',
            'read': True,
            'created_at': '2026-11-12T08:00:00Z',
        },
    ],
    'next_cursor': None,
    'unread_count': 0,
}


def find_chromium_executable(user_path: Optional[str] = None) -> Optional[str]:
    if user_path and os.path.exists(user_path):
        return user_path
    env_path = os.environ.get('CHROMIUM_PATH')
    if env_path and os.path.exists(env_path):
        return env_path
    home = os.path.expanduser('~')
    patterns = [
        os.path.join(home, '.cache/ms-playwright/chromium-*/chrome-linux64/chrome'),
        os.path.join(home, '.cache/ms-playwright/chromium-*/chrome-linux/chrome'),
        os.path.join(home, '.cache/ms-playwright/chromium-*/chrome-linux64/headless_shell'),
        os.path.join(home, '.cache/ms-playwright/chromium-*/chrome-linux/headless_shell'),
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            matches.sort(reverse=True)
            for m in matches:
                if os.access(m, os.X_OK):
                    return m
    return None


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def start_server(frontend_dir: str) -> tuple[ThreadingHTTPServer, int]:
    handler = partial(QuietHandler, directory=frontend_dir)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


class SocialTestContext:
    def __init__(self, page: Page, artifacts_dir: str):
        self.page = page
        self.artifacts_dir = artifacts_dir
        self.errors: List[str] = []

        # Request logs for assertions
        self.post_gifts: List[Dict[str, Any]] = []
        self.post_invites: List[Dict[str, Any]] = []
        self.send_invites: List[Dict[str, Any]] = []
        self.deleted_invites: List[str] = []
        self.friend_request_posts: List[Dict[str, Any]] = []
        self.friend_accept_posts: List[int] = []
        self.friend_request_deletes: List[int] = []
        self.friend_deletes: List[int] = []
        self.read_notifications: List[int] = []
        self.read_all_called: bool = False

        # Configurable routing hooks
        self.gift_error: Optional[str] = None
        self.held_gift_route: Optional[tuple[Any, Dict[str, Any]]] = None
        self.pending_searches: Dict[str, tuple[Any, str]] = {}
        self.hold_search_query: Optional[str] = None

        # Notifications polling state
        self.notifications_state = copy.deepcopy(MOCK_NOTIFICATIONS_PAGE_1)

        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        self._setup_routes()

    def _setup_routes(self) -> None:
        def handle_me(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'id': 1, 'login': 'alice', 'elo': 1200, 'balance': 5000, 'role': 'user',
                'daily_bonus_available_at': None,
            }))

        def handle_config(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'time_controls': ['3+0', '5+0', '10+0'],
            }))

        def handle_active_game(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({'game_id': None}))

        def handle_inventory(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(MOCK_INVENTORY))

        def handle_loadout(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        def handle_gifts_unseen(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({'count': 0}))

        def handle_friends(route: Any, request: Any) -> None:
            method = request.method
            path = urlparse(request.url).path

            if method == 'GET' and path == '/api/v1/friends':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'items': MOCK_FRIENDS,
                }))
            elif method == 'GET' and path == '/api/v1/friends/requests':
                route.fulfill(status=200, content_type='application/json', body=json.dumps(MOCK_REQUESTS))
            elif method == 'POST' and path == '/api/v1/friends/requests':
                data = json.loads(request.post_data or '{}')
                self.friend_request_posts.append(data)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'pending'}))
            elif method == 'POST' and '/accept' in path:
                uid = int(path.split('/')[-2])
                self.friend_accept_posts.append(uid)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'accepted'}))
            elif method == 'DELETE' and '/requests/' in path:
                uid = int(path.split('/')[-1])
                self.friend_request_deletes.append(uid)
                route.fulfill(status=204)
            elif method == 'DELETE' and path.startswith('/api/v1/friends/'):
                uid = int(path.split('/')[-1])
                self.friend_deletes.append(uid)
                route.fulfill(status=204)
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        def handle_users_search(route: Any, request: Any) -> None:
            parsed = urlparse(request.url)
            params = parse_qs(parsed.query)
            q = params.get('q', [''])[0].strip().lower()
            matched = [u for u in MOCK_SEARCH_USERS if q in u['login'].lower()]
            body = json.dumps({'items': matched})

            if self.hold_search_query and q == self.hold_search_query:
                self.pending_searches[q] = (route, body)
                return

            route.fulfill(status=200, content_type='application/json', body=body)

        def handle_gifts(route: Any, request: Any) -> None:
            if request.method == 'POST':
                data = json.loads(request.post_data or '{}')
                self.post_gifts.append(data)

                if self.held_gift_route is not None:
                    # Overwrite or store
                    pass

                if self.gift_error:
                    route.fulfill(status=400, content_type='application/json', body=json.dumps({
                        'error': {'code': 'GIFT_FAILED', 'message': self.gift_error}
                    }))
                elif hasattr(self, '_holding_gift') and self._holding_gift:
                    self.held_gift_route = (route, data)
                else:
                    route.fulfill(status=201, content_type='application/json', body=json.dumps({'ok': True}))
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'items': [], 'next_cursor': None}))

        def handle_invites(route: Any, request: Any) -> None:
            parsed = urlparse(request.url)
            path = parsed.path
            method = request.method

            if method == 'POST' and path == '/api/v1/invites':
                data = json.loads(request.post_data or '{}')
                self.post_invites.append(data)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'code': 'testinvite123',
                    'expires_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 600)),
                }))
            elif method == 'POST' and path.endswith('/send'):
                data = json.loads(request.post_data or '{}')
                self.send_invites.append(data)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'sent'}))
            elif method == 'DELETE':
                code = path.split('/')[-1]
                self.deleted_invites.append(code)
                route.fulfill(status=204)
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        def handle_notifications(route: Any, request: Any) -> None:
            parsed = urlparse(request.url)
            path = parsed.path
            params = parse_qs(parsed.query)
            method = request.method

            if path == '/api/v1/notifications/unread-count':
                count = self.notifications_state.get('unread_count', 0)
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'count': count}))
            elif path.endswith('/read'):
                parts = path.split('/')
                try:
                    nid = int(parts[-2])
                    self.read_notifications.append(nid)
                except Exception:
                    pass
                route.fulfill(status=204)
            elif path.endswith('/read-all'):
                self.read_all_called = True
                self.notifications_state['unread_count'] = 0
                for item in self.notifications_state.get('items', []):
                    item['read'] = True
                route.fulfill(status=204)
            elif method == 'GET':
                before = params.get('before_id', [None])[0]
                if before:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(MOCK_NOTIFICATIONS_PAGE_2))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(self.notifications_state))
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        self.page.route('**/api/v1/me', handle_me)
        self.page.route('**/api/v1/config', handle_config)
        self.page.route('**/api/v1/me/active-game', handle_active_game)
        self.page.route('**/api/v1/inventory*', handle_inventory)
        self.page.route('**/api/v1/loadout*', handle_loadout)
        self.page.route('**/api/v1/me/gifts/unseen-count', handle_gifts_unseen)
        self.page.route('**/api/v1/friends**', handle_friends)
        self.page.route('**/api/v1/users/search*', handle_users_search)
        self.page.route('**/api/v1/gifts*', handle_gifts)
        self.page.route('**/api/v1/invites**', handle_invites)
        self.page.route('**/api/v1/notifications**', handle_notifications)

        def handle_skins(route: Any) -> None:
            seed_p = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app', 'seed_images', 'base-wq.png')
            with open(seed_p, 'rb') as sf:
                route.fulfill(status=200, content_type='image/png', body=sf.read())

        self.page.route('**/api/v1/skins/**', handle_skins)

        def handle_daily_reward(route: Any, request: Any) -> None:
            if request.method == 'GET':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'wins_today': 1, 'wins_required': 3, 'claimed_today': False, 'available': False
                }))
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        self.page.route('**/api/v1/me/daily-reward', handle_daily_reward)

    def assert_no_errors(self) -> None:
        assert not self.errors, f'Page errors encountered: {self.errors}'


def run_tests(root_dir: str, artifacts_dir: str, headless: bool, chromium_path: Optional[str]) -> bool:
    frontend_dir = os.path.join(root_dir, 'frontend')
    assert os.path.isdir(frontend_dir), f'Frontend dir not found: {frontend_dir}'
    os.makedirs(artifacts_dir, exist_ok=True)

    server, port = start_server(frontend_dir)
    base_url = f'http://127.0.0.1:{port}'

    exec_path = find_chromium_executable(chromium_path)
    print(f'[INFO] Serving frontend on {base_url}')
    print(f'[INFO] Using Chromium executable: {exec_path or "default"}')

    passed: List[str] = []
    failed: List[str] = []

    def check(name: str, fn: Any) -> None:
        try:
            fn()
            passed.append(name)
            print(f'  [PASS] {name}')
        except Exception as e:
            failed.append(name)
            print(f'  [FAIL] {name}: {e}')
            traceback.print_exc()
            page.screenshot(path=os.path.join(artifacts_dir, f'failure_{len(failed)}.png'))

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exec_path, headless=headless)

        # ---------------- DESKTOP TESTS ----------------
        ctx_desktop = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = ctx_desktop.new_page()
        tc = SocialTestContext(page, artifacts_dir)

        # 1. Gift friend selection
        def t_gift_friend_selection() -> None:
            tc.post_gifts.clear()
            tc.gift_error = None
            page.goto(f'{base_url}/inventory.html')
            page.wait_for_selector('.item-card', timeout=5000)

            # Open gift modal
            page.locator('button:has-text("Подарить")').first.click()
            page.wait_for_selector('.overlay.open', timeout=5000)
            page.wait_for_selector('.social-picker', timeout=5000)

            # Check that initial friends are rendered
            page.wait_for_selector('.social-person:has-text("bob")', timeout=5000)
            page.wait_for_selector('.social-person:has-text("charlie")', timeout=5000)

            # Select charlie
            page.locator('.social-person:has-text("charlie")').click()
            login_val = page.locator('#gift-login').input_value()
            assert login_val == 'charlie', f'Expected #gift-login to be charlie, got {login_val}'

            # Status indicator
            status_text = page.locator('.gift-chosen-recipient').text_content() or ''
            assert 'charlie' in status_text, f'Expected chosen recipient to mention charlie, got {status_text}'

            # Send gift
            page.locator('.modal .btn-gold:has-text("Подарить")').click()
            page.wait_for_timeout(200)

            assert len(tc.post_gifts) == 1, f'Expected 1 POST /gifts, got {len(tc.post_gifts)}'
            assert tc.post_gifts[0]['to_login'] == 'charlie'
            assert tc.post_gifts[0]['item_id'] == 101

            # Modal explicitly closes on success
            page.wait_for_selector('.overlay:not(.open)', timeout=5000)
            tc.assert_no_errors()

        check('Gift modal friend selection and submission', t_gift_friend_selection)

        # 2. Search race guard and direct nickname
        def t_gift_search_race_and_direct_nickname() -> None:
            tc.post_gifts.clear()
            tc.gift_error = None
            page.goto(f'{base_url}/inventory.html')
            page.wait_for_selector('.item-card', timeout=5000)

            page.locator('button:has-text("Подарить")').first.click()
            page.wait_for_selector('.overlay.open', timeout=5000)

            # Hold 'bo' route to simulate slow network response
            tc.hold_search_query = 'bo'

            search_input = page.locator('.social-search')
            search_input.fill('bo')
            page.wait_for_timeout(250)  # Wait for debounce to trigger 'bo' search and hold it

            # Immediately type 'ch' which fulfills instantly
            search_input.fill('ch')
            page.wait_for_selector('.social-person:has-text("charlotte")', timeout=5000)

            # Now release the held 'bo' search
            if 'bo' in tc.pending_searches:
                bo_route, bo_body = tc.pending_searches.pop('bo')
                bo_route.fulfill(status=200, content_type='application/json', body=bo_body)

            page.wait_for_timeout(100)

            # The list MUST still show 'ch' results and not be overwritten by 'bo'
            person_texts = page.locator('.social-list').text_content() or ''
            assert 'charlotte' in person_texts, 'Expected charlotte in search results'
            assert 'bobcat' not in person_texts, 'Stale bo response improperly overwrote ch results'

            # Preserve direct typed nickname
            login_input = page.locator('#gift-login')
            login_input.fill('direct_user_99')

            # Verify stale selection unhighlighted
            assert page.locator('.social-person.social-selected').count() == 0

            page.locator('.modal .btn-gold:has-text("Подарить")').click()
            page.wait_for_timeout(200)

            assert len(tc.post_gifts) == 1, 'Expected POST /gifts with direct nickname'
            assert tc.post_gifts[0]['to_login'] == 'direct_user_99'
            page.wait_for_selector('.overlay:not(.open)', timeout=5000)
            tc.hold_search_query = None
            tc.assert_no_errors()

        check('Gift search race guard and direct typed nickname', t_gift_search_race_and_direct_nickname)

        # 3. Gift error handling: error stays visible, no premature close, no double submit
        def t_gift_error_stays_open_and_no_double_submit() -> None:
            tc.post_gifts.clear()
            tc.gift_error = 'Пользователь не найден'
            page.goto(f'{base_url}/inventory.html')
            page.wait_for_selector('.item-card', timeout=5000)

            page.locator('button:has-text("Подарить")').first.click()
            page.wait_for_selector('.overlay.open', timeout=5000)

            page.locator('#gift-login').fill('nonexistent')

            # Click gift button
            page.locator('.modal .btn-gold:has-text("Подарить")').click()
            page.wait_for_timeout(200)

            # Modal MUST stay open on error
            assert page.locator('.overlay.open').is_visible(), 'Modal unexpectedly closed on error'
            err_box = page.locator('.form-error')
            assert err_box.is_visible(), 'Error banner is not visible in modal'
            assert 'Пользователь не найден' in (err_box.text_content() or '')

            # Double submit check with route hold (no blocking sleep)
            tc.gift_error = None
            tc._holding_gift = True
            tc.held_gift_route = None

            page.locator('#gift-login').fill('bob')
            gift_btn = page.locator('.modal .m-btnrow .btn-gold')

            # First click triggers request which is held
            gift_btn.click()
            page.wait_for_timeout(50)

            # While in-flight, button is disabled; dispatch click to verify double submit guard
            assert gift_btn.is_disabled(), 'Button should be disabled while submitting'
            gift_btn.dispatch_event('click')

            # Now release the held gift route
            tc._holding_gift = False
            if tc.held_gift_route is not None:
                r, _ = tc.held_gift_route
                r.fulfill(status=201, content_type='application/json', body=json.dumps({'ok': True}))

            page.wait_for_timeout(200)

            # 1 from error attempt + 1 from successful attempt = exactly 2 POSTs
            assert len(tc.post_gifts) == 2, f'Expected 2 requests, got {len(tc.post_gifts)}'
            page.wait_for_selector('.overlay:not(.open)', timeout=5000)
            tc.assert_no_errors()

        check('Gift error stays visible and blocks double submit', t_gift_error_stays_open_and_no_double_submit)

        # 4. Lobby quick friend invitation and retained copy link
        def t_lobby_quick_friend_invite() -> None:
            tc.post_invites.clear()
            tc.send_invites.clear()
            tc.deleted_invites.clear()

            page.goto(f'{base_url}/index.html')

            # Scope specifically to the friend card
            friend_btn = page.locator('.card:has-text("Сыграть с другом") .tc-grid button:has-text("5+0")')
            friend_btn.wait_for(state='visible', timeout=5000)
            friend_btn.click()

            page.wait_for_selector('.invite-link', timeout=5000)

            # Verify public link elements retained
            link_input = page.locator('.invite-link')
            assert 'testinvite123' in link_input.input_value()
            assert page.locator('button:has-text("Копировать")').is_visible()
            page.locator('.invite-countdown').wait_for(state='visible', timeout=2000)
            assert page.locator('button:has-text("Отменить")').is_visible()

            # Verify quick friend invite picker is present (friend-only: searchAll=false)
            page.wait_for_selector('.lobby-friend-invite .social-picker', timeout=5000)
            page.wait_for_selector('.lobby-friend-invite .social-person:has-text("bob")', timeout=5000)

            # Send button initially disabled
            send_btn = page.locator('.btn-send-invite')
            assert send_btn.is_disabled(), 'Send invite button should be disabled before friend selection'

            # Select friend bob
            page.locator('.lobby-friend-invite .social-person:has-text("bob")').click()
            assert not send_btn.is_disabled(), 'Send button should be enabled after selection'
            assert 'bob' in (send_btn.text_content() or '')

            # Send invite
            send_btn.click()
            page.wait_for_timeout(200)

            assert len(tc.send_invites) == 1, f'Expected 1 send invite request, got {len(tc.send_invites)}'
            assert tc.send_invites[0]['friend_id'] == 2

            # Verify success feedback
            status_text = page.locator('.friend-send-status').text_content() or ''
            assert 'bob' in status_text, f'Expected feedback for bob, got {status_text}'

            # Duplicate send prevention: button is disabled; dispatch click to ensure no duplicate POST
            assert send_btn.is_disabled(), 'Send button should be disabled after successful delivery'
            send_btn.dispatch_event('click')
            page.wait_for_timeout(100)
            assert len(tc.send_invites) == 1, 'Duplicate send sent another request'

            # Cancel invite returns to idle
            cancel_btn = page.locator('.invite-meta button:has-text("Отменить")')
            cancel_btn.click()
            page.wait_for_timeout(200)
            assert 'testinvite123' in tc.deleted_invites
            assert friend_btn.is_visible()
            tc.assert_no_errors()

        check('Lobby quick friend invite, duplicate prevention, and retained link', t_lobby_quick_friend_invite)

        # 5. Lobby ?friend=id preselection
        def t_lobby_friend_preselection() -> None:
            tc.post_invites.clear()
            tc.send_invites.clear()

            page.goto(f'{base_url}/index.html?friend=3')
            friend_btn = page.locator('.card:has-text("Сыграть с другом") .tc-grid button:has-text("5+0")')
            friend_btn.wait_for(state='visible', timeout=5000)
            friend_btn.click()

            page.wait_for_selector('.invite-link', timeout=5000)

            # Friend with id 3 is charlie; verify charlie is preselected
            page.wait_for_selector('.lobby-friend-invite .social-person.social-selected', timeout=5000)
            selected_person = page.locator('.lobby-friend-invite .social-person.social-selected').text_content() or ''
            assert 'charlie' in selected_person, f'Expected charlie to be preselected, got {selected_person}'

            send_btn = page.locator('.btn-send-invite')
            assert not send_btn.is_disabled()
            assert 'charlie' in (send_btn.text_content() or '')
            tc.assert_no_errors()

        check('Lobby ?friend=id preselection', t_lobby_friend_preselection)

        # 6. Actual UI clicks/assertions on friends.html and notifications.html
        def t_friends_notifications_ui_flow() -> None:
            tc.friend_request_posts.clear()
            tc.friend_accept_posts.clear()
            tc.friend_request_deletes.clear()
            tc.friend_deletes.clear()
            tc.read_notifications.clear()
            tc.read_all_called = False

            tc.notifications_state = copy.deepcopy(MOCK_NOTIFICATIONS_PAGE_1)
            page.goto(f'{base_url}/friends.html')
            people = page.locator('.social-content .social-person')
            people.filter(has_text='bob').get_by_role('button', name='Удалить').click()
            page.wait_for_timeout(100)
            assert tc.friend_deletes == [2]
            page.get_by_role('button', name='Входящие заявки').click()
            people.filter(has_text='dave').get_by_role('button', name='Принять', exact=True).click()
            page.wait_for_timeout(100)
            assert tc.friend_accept_posts == [4]
            people.filter(has_text='dave').get_by_role('button', name='Отклонить').click()
            page.wait_for_timeout(100)
            assert tc.friend_request_deletes == [4]
            page.get_by_role('button', name='Исходящие').click()
            people.filter(has_text='eve').get_by_role('button', name='Отменить заявку').click()
            page.wait_for_timeout(100)
            assert tc.friend_request_deletes == [4, 5]
            page.locator('main .social-search').fill('charlotte')
            people.filter(has_text='charlotte').get_by_role('button', name='Добавить в друзья').click()
            page.wait_for_timeout(100)
            assert tc.friend_request_posts == [{'login': 'charlotte'}]
            page.locator('.notif-bell-btn').click()
            assert page.locator('.notif-popover').is_visible()
            page.locator('.notif-popover .notif-read-all-btn').click()
            page.wait_for_timeout(100)
            assert tc.read_all_called
            assert page.locator('.notif-badge').is_hidden()
            tc.notifications_state = copy.deepcopy(MOCK_NOTIFICATIONS_PAGE_1)
            page.goto(f'{base_url}/notifications.html')
            page.locator('.notif-card').first.get_by_role('button', name='Прочитать', exact=True).click()
            page.wait_for_timeout(100)
            assert 10 in tc.read_notifications
            page.locator('main .notif-mark-all-btn').click()
            page.wait_for_timeout(100)
            assert page.locator('.notif-badge').is_hidden()
            page.locator('main .notif-load-more').click()
            page.get_by_role('heading', name='Предмет продан').wait_for()
            assert page.locator('.toast').filter(has_text='Новое приглашение').count() == 0
            tc.notifications_state['items'].insert(0, {
                'id': 99, 'kind': 'match_invite', 'title': 'Новое приглашение',
                'body': 'Новый соперник ждёт вас', 'href': '/invite.html?code=pollcode',
                'read': False, 'created_at': '2026-11-12T11:00:00Z',
            })
            tc.notifications_state['unread_count'] = 1
            page.evaluate("() => window.dispatchEvent(new Event('focus'))")
            page.locator('.toast').filter(has_text='Новое приглашение').wait_for()
            page.get_by_role('heading', name='Новое приглашение').wait_for()
            page.evaluate("() => window.dispatchEvent(new Event('focus'))")
            page.wait_for_timeout(150)
            assert page.locator('.toast').filter(has_text='Новое приглашение').count() == 1
            page.screenshot(path=os.path.join(artifacts_dir, 'desktop_notifications.png'))
            tc.assert_no_errors()

        check('Friends and notifications page UI flows per contract', t_friends_notifications_ui_flow)

        # ---------------- MOBILE TESTS ----------------
        ctx_mobile = browser.new_context(viewport={'width': 390, 'height': 844})
        m_page = ctx_mobile.new_page()
        m_tc = SocialTestContext(m_page, artifacts_dir)

        # 7. Mobile screenshots & no horizontal overflow
        def t_mobile_screenshots_and_overflow() -> None:
            # Gift modal on mobile
            m_page.goto(f'{base_url}/inventory.html')
            m_page.wait_for_selector('.item-card', timeout=5000)
            m_page.locator('button:has-text("Подарить")').first.click()
            m_page.wait_for_selector('.overlay.open', timeout=5000)
            m_page.wait_for_selector('.social-picker', timeout=5000)

            # Check no horizontal overflow
            modal_has_overflow = m_page.evaluate("""() => {
                const modal = document.querySelector('.modal');
                return modal ? modal.scrollWidth > window.innerWidth : false;
            }""")
            assert not modal_has_overflow, 'Gift modal has horizontal overflow on mobile'

            gift_shot = os.path.join(artifacts_dir, 'mobile_gift_modal.png')
            m_page.screenshot(path=gift_shot)

            # Lobby invite on mobile
            m_page.goto(f'{base_url}/index.html')
            friend_btn = m_page.locator('.card:has-text("Сыграть с другом") .tc-grid button:has-text("5+0")')
            friend_btn.wait_for(state='visible', timeout=5000)
            friend_btn.click()

            m_page.wait_for_selector('.invite-link', timeout=5000)
            m_page.wait_for_selector('.lobby-friend-invite', timeout=5000)

            body_has_overflow = m_page.evaluate("""() => {
                return document.documentElement.scrollWidth > window.innerWidth;
            }""")
            assert not body_has_overflow, 'Lobby invite view has horizontal overflow on mobile'

            lobby_shot = os.path.join(artifacts_dir, 'mobile_lobby_invite.png')
            m_page.screenshot(path=lobby_shot)

            m_tc.assert_no_errors()

        check('Mobile screenshots and no horizontal overflow', t_mobile_screenshots_and_overflow)

        def t_mobile_social_pages() -> None:
            for path in ('friends', 'notifications'):
                m_page.goto(f'{base_url}/{path}.html')
                m_page.locator('main .social-person, main .notif-card').first.wait_for()
                assert m_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                m_page.screenshot(path=os.path.join(artifacts_dir, f'mobile_{path}.png'))
            m_page.locator('.notif-bell-btn').click()
            popover = m_page.locator('.notif-popover')
            popover.wait_for(state='visible')
            bounds = popover.bounding_box()
            assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
            m_page.screenshot(path=os.path.join(artifacts_dir, 'mobile_bell.png'))
            m_page.keyboard.press('Escape')
            assert popover.is_hidden()
            assert m_page.locator('.notif-bell-btn').evaluate('(el) => el === document.activeElement')
            m_tc.assert_no_errors()

        check('Mobile friends, notifications, and accessible bell', t_mobile_social_pages)

        browser.close()

    server.shutdown()
    server.server_close()

    print('\n================ TEST SUMMARY ================')
    print(f'Total passed: {len(passed)}')
    print(f'Total failed: {len(failed)}')
    if failed:
        print('Failed tests:')
        for f in failed:
            print(f'  - {f}')
    print('==============================================\n')
    return len(failed) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description='ChessDep Social Actions Playwright Suite')
    parser.add_argument('--root', default='.', help='Root path to ChessDep repository')
    parser.add_argument('--artifacts', default='/tmp/chessdep-ui-artifacts', help='Directory to store artifacts/screenshots')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser headless (default: True)')
    parser.add_argument('--no-headless', dest='headless', action='store_false', help='Run browser headed')
    parser.add_argument('--executable-path', default=None, help='Explicit path to Chromium browser executable')
    args = parser.parse_args()

    success = run_tests(
        root_dir=os.path.abspath(args.root),
        artifacts_dir=os.path.abspath(args.artifacts),
        headless=args.headless,
        chromium_path=args.executable_path,
    )
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
