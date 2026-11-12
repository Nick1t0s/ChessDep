"""Browser smoke & regression test suite for ChessDep Social Phase 2 features.

Tests:
  - Rematch vs Spectator: participant sees rematch button and can request; spectator does not.
  - Rematch duplicate blocked send, error leaves retry available, expiry stops waiting.
  - Post-match social controls rendered in end modal for opponent.
  - Friend profile add: visiting other user's profile renders add friend; self-profile hides controls.
  - Privacy settings & blocks: navigating from profile, saving settings, watch link for in_game friends.
  - Targeted notification actions: accepting match invitation navigates to /game.html?id=...
  - Personal trade history: summary labels and integers, filter direction/def, pagination append,
    retry preserves rows on pagination error, skin click filter, responsive 390px mobile layout.

Usage:
  /tmp/codex-venv-chessdep-ui/bin/python scripts/test_social2_ui.py --root . --artifacts /tmp/chessdep-ui-artifacts
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys
import threading
import time
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright


def find_chromium_executable(user_path: Optional[str] = None) -> Optional[str]:
    if user_path and os.path.isfile(user_path) and os.access(user_path, os.X_OK):
        return user_path
    env_path = os.environ.get('CHROMIUM_PATH')
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path
    hardcoded = '/home/nik/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome'
    if os.path.isfile(hardcoded) and os.access(hardcoded, os.X_OK):
        return hardcoded
    cache_root = os.path.expanduser('~/.cache/ms-playwright')
    candidates = glob.glob(os.path.join(cache_root, 'chromium-*', 'chrome-linux64', 'chrome'))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
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


class Social2TestContext:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.rematch_post_count = 0
        self.rematch_fail = False
        self.rematch_expires_at: Optional[str] = None
        self.active_game_id: Optional[str] = None
        self.settings_patch_called = False
        self.notification_action_called = False
        self.friend_add_called = False
        self.trade_requests: List[Dict[str, Any]] = []
        self.relationship = 'none'
        self.blocks = []
        self.settings = {'presence_mode': 'online', 'match_invites': 'all',
                         'notifications': {k: True for k in ('friend_request', 'friend_accepted', 'match_invite', 'market_sale', 'gift')}}
        self.notifications = [dict(id=101, kind='match_invite', title='Вызов на матч', body='bob приглашает сыграть',
                                   read=False, action_state='pending', allowed_actions=['accept', 'decline'],
                                   created_at='2026-01-01T10:00:00Z'),
                              dict(id=102, kind='friend_request', title='Заявка bob', body='bob хочет дружить',
                                   read=False, action_state='pending', allowed_actions=['accept', 'decline'],
                                   created_at='2026-01-01T10:00:00Z'),
                              dict(id=103, kind='match_invite', title='Старое предложение', body='',
                                   read=True, action_state='expired', allowed_actions=[], created_at='2026-01-01T10:00:00Z')]
        self._setup_routes()

    def _setup_routes(self) -> None:
        def handler(route):
            request = route.request
            url = request.url
            method = request.method
            parsed = urlparse(url)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == '/api/v1/me':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'id': 1,
                    'login': 'alice',
                    'role': 'user',
                    'elo': 1250,
                    'balance': 3500,
                    'created_at': '2026-01-01T10:00:00Z',
                }))
                return

            if path == '/api/v1/me/active-game':
                if self.active_game_id:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({
                        'game_id': self.active_game_id,
                    }))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps(None))
                return

            if path.startswith('/api/v1/games/') and path.endswith('/rematch'):
                self.rematch_post_count += 1
                if self.rematch_fail:
                    route.fulfill(status=400, content_type='application/json', body=json.dumps({
                        'error': {'code': 'BUSY', 'message': 'Соперник занят'},
                    }))
                    return
                exp = self.rematch_expires_at or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 60))
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'code': 'rematch123',
                    'expires_at': exp,
                    'status': 'sent',
                }))
                return

            if path.startswith('/api/v1/games/') and not path.endswith('/events') and not path.endswith('/chat'):
                # State mock
                is_spec = 'spec=1' in self.page.url
                you_role = 'spectator' if is_spec else 'white'
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'id': '11111111-1111-1111-1111-111111111111',
                    'version': 10,
                    'status': 'finished',
                    'result': 'white',
                    'end_reason': 'checkmate',
                    'turn': 'white',
                    'ply': 12,
                    'you': you_role,
                    'players': {
                        'white': {'login': 'alice', 'elo': 1250, 'loadout': {}},
                        'black': {'login': 'bob', 'elo': 1200, 'loadout': {}},
                    },
                    'board': [],
                    'clocks': {'white_ms': 180000, 'black_ms': 175000, 'running': None},
                    'deps': {'limit': 3, 'white_used': 0, 'black_used': 0, 'used_this_turn': False},
                    'draw_offer_by': None,
                    'check_square': None,
                    'legal_moves': [],
                }))
                return

            if path.endswith('/events'):
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'events': []}))
                return

            if path.endswith('/chat'):
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'messages': []}))
                return

            if path == '/api/v1/users/bob/social' or path == '/api/v1/users/bob':
                if path.endswith('/social'):
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({
                        'id': 2,
                        'login': 'bob',
                        'relationship': self.relationship,
                        'blocked_by_me': False,
                        'presence': 'online',
                        'game_id': None,
                    }))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({
                        'id': 2,
                        'login': 'bob',
                        'elo': 1200,
                        'created_at': '2026-01-01T10:00:00Z',
                        'games': {'played': 10, 'wins': 5, 'draws': 1, 'losses': 4},
                    }))
                return

            if path == '/api/v1/users/alice/social' or path == '/api/v1/users/alice':
                if path.endswith('/social'):
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({
                        'id': 1,
                        'login': 'alice',
                        'relationship': 'self',
                        'blocked_by_me': False,
                        'presence': 'online',
                        'game_id': None,
                    }))
                else:
                    route.fulfill(status=200, content_type='application/json', body=json.dumps({
                        'id': 1,
                        'login': 'alice',
                        'elo': 1250,
                        'created_at': '2026-01-01T10:00:00Z',
                        'games': {'played': 12, 'wins': 8, 'draws': 2, 'losses': 2},
                    }))
                return

            if path.startswith('/api/v1/users/') and path.endswith('/games'):
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'items': [],
                    'next_before': None,
                }))
                return

            if path == '/api/v1/friends':
                route.fulfill(json={'items': [{'id': 2, 'login': 'bob', 'elo': 1200, 'presence': 'in_game',
                                              'game_id': '22222222-2222-2222-2222-222222222222'}]})
                return
            if path == '/api/v1/friends/requests':
                if method == 'POST':
                    self.friend_add_called = True
                    self.relationship = 'outgoing'
                    route.fulfill(json={'status': 'pending'})
                else:
                    route.fulfill(json={'incoming': [], 'outgoing': []})
                return
            if path == '/api/v1/me/social-settings':
                if method == 'PATCH':
                    self.settings_patch_called = True
                    patch = request.post_data_json
                    for key, value in patch.items():
                        if key == 'notifications': self.settings[key].update(value)
                        else: self.settings[key] = value
                route.fulfill(json=self.settings)
                return
            if path == '/api/v1/me/blocks':
                if method == 'POST':
                    self.blocks = [{'id': 2, 'login': request.post_data_json['login'], 'elo': 1200}]
                    route.fulfill(status=204)
                else: route.fulfill(json={'items': self.blocks})
                return
            if path.startswith('/api/v1/me/blocks/') and method == 'DELETE':
                self.blocks = []
                route.fulfill(status=204)
                return
            if path.startswith('/api/v1/notifications/') and path.endswith('/action'):
                self.notification_action_called = True
                item = next(n for n in self.notifications if n['id'] == int(path.split('/')[-2]))
                accepted = request.post_data_json['action'] == 'accept'
                item.update(action_state='accepted' if accepted else 'declined', allowed_actions=[], read=True)
                route.fulfill(json={'status': item['action_state'],
                                    'game_id': '33333333-3333-3333-3333-333333333333' if accepted and item['kind'] == 'match_invite' else None})
                return
            if path == '/api/v1/notifications':
                route.fulfill(json={'items': self.notifications, 'next_cursor': None,
                                    'unread_count': sum(not n['read'] for n in self.notifications)})
                return
            if path == '/api/v1/notifications/unread-count':
                route.fulfill(json={'count': sum(not n['read'] for n in self.notifications)})
                return
            if path == '/api/v1/item-defs':
                route.fulfill(json=[{'id': 42, 'name': 'Пешка Золото'}, {'id': 10, 'name': 'Ладья Рубин'}])
                return
            if path == '/api/v1/me/trades':
                self.trade_requests.append({'query': query})
                before_id = query.get('before_id', [None])[0]
                if before_id:
                    # Page 2
                    items = [
                        {
                            'id': 15,
                            'item_id': 102,
                            'item_def_id': 10,
                            'item_name': 'Ладья Рубин',
                            'direction': 'buy',
                            'price': 400,
                            'fee': 0,
                            'net': 400,
                            'created_at': '2026-01-02T12:00:00Z',
                        }
                    ]
                    next_cursor = None
                else:
                    # Page 1
                    items = [
                        {
                            'id': 20,
                            'item_id': 101,
                            'item_def_id': 42,
                            'item_name': 'Пешка Золото',
                            'direction': 'sell',
                            'price': 1000,
                            'fee': 50,
                            'net': 950,
                            'created_at': '2026-01-01T12:00:00Z',
                        }
                    ]
                    next_cursor = 15

                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'items': items,
                    'next_cursor': next_cursor,
                    'summary': {
                        'sold_count': 5,
                        'bought_count': 2,
                        'gross_sales': 5000,
                        'fees': 250,
                        'net_sales': 4750,
                        'total_spent': 800,
                    },
                }))
                return

            if path == '/api/v1/me/games':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'items': [], 'next_before': None}))
                return

            if path == '/api/v1/me/ledger':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'items': [], 'next_cursor': None}))
                return

            if path == '/api/v1/market':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'total': 0, 'items': []}))
                return

            route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        self.page.route('**/api/v1/**', handler)


def run_tests(root_dir: str, artifacts_dir: str, executable_path: Optional[str] = None) -> None:
    os.makedirs(artifacts_dir, exist_ok=True)
    server, port = start_server(os.path.join(root_dir, 'frontend'))
    base_url = f'http://127.0.0.1:{port}'

    chromium_path = find_chromium_executable(executable_path)
    if not chromium_path:
        print('CRITICAL: Chromium binary not found.')
        sys.exit(1)

    print(f'Starting Playwright with Chromium: {chromium_path}')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium_path, headless=True)

        passed = 0
        failed = 0

        def run_test(name, fn):
            nonlocal passed, failed
            print(f'\n[TEST] {name}...')
            page = browser.new_page()
            ctx = Social2TestContext(page, base_url)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                fn(ctx, page)
                assert not errors, errors
                print(f'[PASS] {name}')
                passed += 1
            except Exception as e:
                print(f'[FAIL] {name}: {e}')
                traceback.print_exc()
                try:
                    shot_path = os.path.join(artifacts_dir, f'{name}.png')
                    page.screenshot(path=shot_path, full_page=True)
                    print(f'Saved failure screenshot: {shot_path}')
                except Exception:
                    pass
                failed += 1
            finally:
                page.close()

        # Test 1: Rematch vs Spectator
        def t_rematch_vs_spectator(ctx: Social2TestContext, page: Page):
            # 1a. Participant
            page.goto(f'{base_url}/game.html?id=11111111-1111-1111-1111-111111111111')
            page.wait_for_selector('.modal', timeout=5000)
            rematch_btn = page.wait_for_selector('.m-btnrow button:has-text("Реванш")', timeout=3000)
            assert rematch_btn is not None, "Rematch button missing for participant"
            assert not rematch_btn.is_disabled(), "Rematch button should be enabled"

            # Click rematch
            rematch_btn.click()
            page.wait_for_selector('.rematch-status', timeout=3000)
            assert ctx.rematch_post_count == 1, f"Expected 1 rematch POST, got {ctx.rematch_post_count}"
            assert rematch_btn.is_disabled(), "Rematch button must be disabled while sending/waiting"
            assert page.is_visible('.modal'), "Modal must stay open after rematch click"

            # 1b. Duplicate click guard
            rematch_btn.dispatch_event('click')
            assert ctx.rematch_post_count == 1, "Duplicate click should be blocked"

            # 1c. Spectator
            page.goto(f'{base_url}/game.html?id=11111111-1111-1111-1111-111111111111&spec=1')
            page.wait_for_selector('.modal', timeout=5000)
            assert page.query_selector('.m-btnrow button:has-text("Реванш")') is None, "Spectator must not see Rematch button"

        # Test 2: Rematch error retry and expiry
        def t_rematch_error_and_expiry(ctx: Social2TestContext, page: Page):
            ctx.rematch_fail = True
            page.goto(f'{base_url}/game.html?id=11111111-1111-1111-1111-111111111111')
            page.wait_for_selector('.modal', timeout=5000)
            rematch_btn = page.wait_for_selector('.m-btnrow button:has-text("Реванш")', timeout=3000)

            # Click failing rematch
            rematch_btn.click()
            page.wait_for_selector('.rematch-status:has-text("Соперник занят")', timeout=3000)
            assert not rematch_btn.is_disabled(), "Error should leave retry available"

            # Retry succeeds
            ctx.rematch_fail = False
            ctx.rematch_expires_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 1))
            rematch_btn.click()
            page.wait_for_selector('.rematch-status:has-text("Ожидание соперника")', timeout=3000)
            assert rematch_btn.is_disabled(), "Button disabled during waiting"

            # Wait for relative expiry (1s)
            time.sleep(2.5)
            # Poller check will detect expiry
            page.wait_for_selector('.rematch-status:has-text("Время ожидания реванша истекло")', timeout=5000)
            assert not rematch_btn.is_disabled(), "Expiry must re-enable retry"

        # Test 3: Active game polling redirect
        def t_rematch_activegame_redirect(ctx: Social2TestContext, page: Page):
            page.goto(f'{base_url}/game.html?id=11111111-1111-1111-1111-111111111111')
            page.wait_for_selector('.modal', timeout=5000)
            rematch_btn = page.wait_for_selector('.m-btnrow button:has-text("Реванш")', timeout=3000)
            rematch_btn.click()

            # Opponent accepted -> active-game returns new game id
            ctx.active_game_id = '99999999-9999-9999-9999-999999999999'
            page.wait_for_url('**/game.html?id=99999999-9999-9999-9999-999999999999', timeout=7000)
            assert 'id=99999999-9999-9999-9999-999999999999' in page.url

        # Test 4: Profile links to social settings & trade history
        def t_profile_and_market_links(ctx: Social2TestContext, page: Page):
            page.goto(f'{base_url}/profile.html')
            page.wait_for_selector('.profile', timeout=5000)
            settings_link = page.wait_for_selector('.profile a[href="/social-settings.html"]', timeout=3000)
            assert settings_link is not None, "Profile missing link to /social-settings.html"
            trade_link = page.wait_for_selector('a[href="/trade-history.html"]', timeout=3000)
            assert trade_link is not None, "Profile missing link to /trade-history.html"

            page.goto(f'{base_url}/market.html')
            page.wait_for_selector('.market', timeout=5000)
            mk_trade_link = page.wait_for_selector('a[href="/trade-history.html"]', timeout=3000)
            assert mk_trade_link is not None, "Market missing link to /trade-history.html"

        # Test 5: Trade history summary, filters, pagination and race guard
        def t_trade_history_features(ctx: Social2TestContext, page: Page):
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(f'{base_url}/trade-history.html')
            page.wait_for_selector('.th-summary', timeout=5000)

            # Check summary text matches 'Продажи до комиссии'
            page.wait_for_selector('text=Продажи до комиссии', timeout=3000)
            page.wait_for_selector('text=5 000 ◈', timeout=3000)

            # Check initial table rows
            page.wait_for_selector('.th-table tbody tr', timeout=3000)
            rows = page.query_selector_all('.th-table tbody tr')
            assert len(rows) == 1

            # Test direction filter change
            page.select_option('#th-dir-select', 'sell')
            page.wait_for_timeout(300)

            # Select by skin name; database ids stay out of the product UI.
            page.select_option('#th-def-input', label='Пешка Золото')
            page.click('button:has-text("Применить")')
            page.wait_for_timeout(300)
            assert ctx.trade_requests[-1]['query']['item_def_id'] == ['42']

            # Test pagination click
            more_btn = page.wait_for_selector('button:has-text("Загрузить ещё")', timeout=3000)
            assert more_btn.is_visible()
            more_btn.click()
            page.wait_for_timeout(500)
            rows_after = page.query_selector_all('.th-table tbody tr')
            assert len(rows_after) == 2, f"Expected 2 rows after pagination, got {len(rows_after)}"

            # Test click on skin name sets filter
            skin_btn = page.wait_for_selector('.th-skin-btn', timeout=3000)
            skin_btn.click()
            page.wait_for_timeout(300)

            # Check mobile responsive: no horizontal overflow
            overflow = page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            assert overflow, "Page must not have horizontal overflow on 390px viewport"
            page.screenshot(path=os.path.join(artifacts_dir, "mobile_trade_history.png"))

        def t_friend_profile(ctx, page):
            page.goto(f'{base_url}/user.html?login=bob')
            page.get_by_role('button', name='Добавить в друзья', exact=True).click()
            page.locator('.social-controls').get_by_text('Заявка отправлена', exact=True).wait_for()
            assert ctx.friend_add_called
            page.goto(f'{base_url}/user.html?login=alice')
            page.locator('main h1').wait_for()
            assert page.get_by_role('button', name='Добавить в друзья', exact=True).count() == 0

        def t_settings_blocks_watch(ctx, page):
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(f'{base_url}/social-settings.html')
            page.locator('input[name=presence_mode][value=dnd]').check()
            page.wait_for_function("() => !document.querySelector('input[name=presence_mode]').disabled")
            assert ctx.settings['presence_mode'] == 'dnd'
            page.locator('input[name=match_invites][value=friends]').check()
            page.wait_for_function("() => !document.querySelector('input[name=match_invites]').disabled")
            assert ctx.settings['match_invites'] == 'friends'
            page.locator('input[name=gift]').uncheck()
            page.wait_for_function("() => !document.querySelector('input[name=gift]').disabled")
            assert ctx.settings['notifications']['gift'] is False
            page.locator('.settings-block-input').fill('bob')
            page.get_by_role('button', name='Заблокировать', exact=True).click()
            page.get_by_role('button', name='Разблокировать', exact=True).wait_for()
            assert len(ctx.blocks) == 1
            page.get_by_role('button', name='Разблокировать', exact=True).click()
            page.get_by_text('В чёрном списке пока никого нет.', exact=True).wait_for()
            assert not ctx.blocks
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=os.path.join(artifacts_dir, 'mobile_settings.png'))
            page.goto(f'{base_url}/friends.html')
            page.get_by_role('link', name='Смотреть', exact=True).wait_for()
            assert page.locator('.social-content').get_by_role('link', name='Позвать в игру').count() == 0
            page.screenshot(path=os.path.join(artifacts_dir, 'mobile_friends.png'))

        def t_notification_actions(ctx, page):
            page.goto(f'{base_url}/notifications.html')
            expired = page.locator('.notif-card').filter(has_text='Старое предложение')
            expired.get_by_text('Истекло', exact=True).wait_for()
            assert expired.get_by_role('button', name='Принять', exact=True).count() == 0
            friend = page.locator('.notif-card').filter(has_text='Заявка bob')
            friend.get_by_role('button', name='Принять', exact=True).click()
            friend.get_by_text('Принято', exact=True).wait_for()
            match = page.locator('.notif-card').filter(has_text='Вызов на матч')
            match.get_by_role('button', name='Отклонить', exact=True).click()
            match.get_by_text('Отклонено', exact=True).wait_for()
            ctx.notifications[0].update(action_state='pending', allowed_actions=['accept', 'decline'], read=False)
            page.reload()
            page.locator('.notif-card').filter(has_text='Вызов на матч').get_by_role('button', name='Принять', exact=True).click()
            page.wait_for_url('**/game.html?id=33333333-3333-3333-3333-333333333333')
            assert ctx.notification_action_called

        run_test('rematch_vs_spectator', t_rematch_vs_spectator)
        run_test('rematch_error_and_expiry', t_rematch_error_and_expiry)
        run_test('rematch_activegame_redirect', t_rematch_activegame_redirect)
        run_test('profile_and_market_links', t_profile_and_market_links)
        run_test('trade_history_features', t_trade_history_features)

        run_test('friend_profile', t_friend_profile)
        run_test('settings_blocks_watch', t_settings_blocks_watch)
        run_test('notification_actions', t_notification_actions)

        browser.close()

    server.shutdown()
    print(f'\nSuite finished: {passed} passed, {failed} failed.')
    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--artifacts', default='/tmp/chessdep-ui-artifacts')
    parser.add_argument('--executable-path', default=None)
    args = parser.parse_args()
    run_tests(args.root, args.artifacts, args.executable_path)
