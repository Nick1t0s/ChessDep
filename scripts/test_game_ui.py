"""Browser smoke & regression test suite for ChessDep game and upgrade UI.

Usage:
  /tmp/codex-venv-chessdep-ui/bin/python scripts/test_game_ui.py --root /path/to/repository --artifacts /tmp/...

Requirements:
  - Python 3.10+ with `playwright` installed.
  - Chromium browser binary installed (in standard Playwright cache, e.g.
    ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome, or via CHROMIUM_PATH).
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright

INITIAL_BOARD: List[Dict[str, str]] = []
_PIECES_R1 = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
_FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
for _i, _f in enumerate(_FILES):
    INITIAL_BOARD.append({'square': f'{_f}1', 'piece': _PIECES_R1[_i], 'color': 'white'})
    INITIAL_BOARD.append({'square': f'{_f}2', 'piece': 'P', 'color': 'white'})
    INITIAL_BOARD.append({'square': f'{_f}7', 'piece': 'P', 'color': 'black'})
    INITIAL_BOARD.append({'square': f'{_f}8', 'piece': _PIECES_R1[_i], 'color': 'black'})

WHITE_LEGAL_MOVES = [
    'a2a3', 'a2a4', 'b2b3', 'b2b4', 'c2c3', 'c2c4', 'd2d3', 'd2d4',
    'e2e3', 'e2e4', 'f2f3', 'f2f4', 'g2g3', 'g2g4', 'h2h3', 'h2h4',
    'b1a3', 'b1c3', 'g1f3', 'g1h3'
]

MOCK_INVENTORY = [
    {
        'id': 'i1',
        'status': 'owned',
        'exterior': 'FN',
        'def': {
            'id': 'd1',
            'kind': 'piece_skin',
            'piece_type': 'P',
            'rarity': 'common',
            'asset': {'type': 'stub', 'color': '#ffd700'},
            'value': 100,
            'name': 'Pawn Skin',
        },
    }
]

MOCK_TARGET_DEFS = [
    {
        'id': 't1',
        'kind': 'piece_skin',
        'piece_type': 'Q',
        'rarity': 'common',
        'asset': {'type': 'stub', 'color': '#ffd700'},
        'value': 500,
        'name': 'Target Queen',
    }
]

MOCK_UPGRADE_ITEM = {
    'id': 'item-2',
    'exterior': 'FN',
    'def': {
        'id': 't1',
        'kind': 'piece_skin',
        'piece_type': 'Q',
        'rarity': 'common',
        'asset': {'type': 'stub', 'color': '#ffd700'},
        'value': 500,
        'name': 'Queen Skin',
    },
}


def make_game_state(
    game_id: str = '11111111-1111-1111-1111-111111111111',
    you: str = 'white',
    turn: str = 'white',
    status: str = 'active',
    check_square: Optional[str] = None,
    board: Optional[List[Dict[str, str]]] = None,
    legal_moves: Optional[List[str]] = None,
    version: int = 1,
    ply: int = 0,
) -> Dict[str, Any]:
    return {
        'id': game_id,
        'status': status,
        'turn': turn,
        'you': you,
        'ply': ply,
        'version': version,
        'check_square': check_square,
        'last_action': None,
        'draw_offer_by': None,
        'end_reason': None,
        'result': None,
        'players': {
            'white': {'login': 'alice', 'elo': 1200, 'loadout': {}},
            'black': {'login': 'bob', 'elo': 1250, 'loadout': {}},
        },
        'clocks': {
            'white_ms': 300000,
            'black_ms': 300000,
            'running': turn if status == 'active' else None,
        },
        'deps': {
            'limit': 3,
            'used_this_turn': False,
            'white_used': 0,
            'black_used': 0,
        },
        'board': list(board if board is not None else INITIAL_BOARD),
        'legal_moves': list(legal_moves if legal_moves is not None else WHITE_LEGAL_MOVES),
    }


def make_dep_options() -> Dict[str, Any]:
    return {
        'available': True,
        'unavailable_reason': None,
        'pieces': [
            {
                'square': 'e2',
                'piece': 'P',
                'targets': [
                    {'piece': 'N', 'allowed': True, 'chance': 0.5, 'chance_text': '50%', 'reason': None},
                    {'piece': 'Q', 'allowed': False, 'chance': 0.1, 'chance_text': '10%', 'reason': 'DEP_TARGET_NOT_ALLOWED'},
                ],
            }
        ],
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


FAKE_WS_SCRIPT = """
window.__mockSockets = [];
class FakeWebSocket extends EventTarget {
  constructor(url) {
    super();
    this.url = url;
    this.readyState = 0;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    window.__mockSockets.push(this);
    setTimeout(() => {
      this.readyState = 1;
      const ev = new Event('open');
      if (this.onopen) this.onopen(ev);
      this.dispatchEvent(ev);
    }, 10);
  }
  send(data) {}
  close() {
    this.readyState = 3;
    const ev = new CloseEvent('close');
    if (this.onclose) this.onclose(ev);
    this.dispatchEvent(ev);
  }
  receive(payload) {
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    const ev = new MessageEvent('message', { data });
    if (this.onmessage) this.onmessage(ev);
    this.dispatchEvent(ev);
  }
}
window.WebSocket = FakeWebSocket;
window.__sendMockWs = (payload) => {
  for (const s of window.__mockSockets) {
    if (s.readyState === 1) s.receive(payload);
  }
};
"""


class TestContext:
    def __init__(self, page: Page, artifacts_dir: str, game_id: str):
        self.page = page
        self.artifacts_dir = artifacts_dir
        self.game_id = game_id
        self.errors: List[str] = []
        self.post_moves: List[Dict[str, Any]] = []
        self.post_deps: List[Dict[str, Any]] = []
        self.post_upgrades: List[Dict[str, Any]] = []
        self.current_state: Dict[str, Any] = make_game_state(game_id=game_id)
        self.dep_options: Dict[str, Any] = make_dep_options()

        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        self.page.add_init_script(FAKE_WS_SCRIPT)
        self._setup_routes()

    def _setup_routes(self) -> None:
        def handle_me(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'id': 'u-alice', 'login': 'alice', 'elo': 1200, 'balance': 5000, 'role': 'user'
            }))

        def handle_gifts(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({'count': 0}))

        def handle_game(route: Any, request: Any) -> None:
            path = urlparse(request.url).path
            method = request.method
            if path.endswith('/dep-options') and method == 'GET':
                route.fulfill(status=200, content_type='application/json', body=json.dumps(self.dep_options))
            elif path.endswith('/events') and method == 'GET':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'events': []}))
            elif path.endswith('/chat') and method == 'GET':
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'items': []}))
            elif path.endswith('/move') and method == 'POST':
                data = json.loads(request.post_data or '{}')
                self.post_moves.append(data)
                uci = data.get('uci', '')
                self.current_state['version'] += 1
                self.current_state['ply'] += 1
                self.current_state['turn'] = 'black' if self.current_state['turn'] == 'white' else 'white'
                self.current_state['last_action'] = {'kind': 'move', 'uci': uci}
                route.fulfill(status=200, content_type='application/json', body=json.dumps(self.current_state))
            elif path.endswith('/dep') and method == 'POST':
                data = json.loads(request.post_data or '{}')
                self.post_deps.append(data)
                self.current_state['version'] += 1
                self.current_state['deps']['white_used'] += 1
                self.current_state['deps']['used_this_turn'] = True
                res = {
                    'from': 'P', 'to': data.get('target', 'N'), 'square': data.get('square', 'e2'),
                    'chance': 0.5, 'chance_text': '50%', 'roll_value': 0.2, 'success': True,
                    'state': self.current_state,
                }
                route.fulfill(status=200, content_type='application/json', body=json.dumps(res))
            elif method == 'GET':
                route.fulfill(status=200, content_type='application/json', body=json.dumps(self.current_state))
            else:
                route.fulfill(status=200, content_type='application/json', body=json.dumps({}))

        def handle_upgrade_preview(route: Any, request: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'allowed': True, 'chance': 0.5, 'chance_text': '50%', 'reason': None
            }))

        def handle_upgrade(route: Any, request: Any) -> None:
            data = json.loads(request.post_data or '{}')
            self.post_upgrades.append(data)
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'success': True, 'roll_value': 0.2, 'item': MOCK_UPGRADE_ITEM
            }))

        def handle_inventory(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(MOCK_INVENTORY))

        def handle_item_defs(route: Any) -> None:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(MOCK_TARGET_DEFS))

        self.page.route('**/api/v1/me', handle_me)
        self.page.route('**/api/v1/me/gifts/unseen-count', handle_gifts)
        self.page.route('**/api/v1/games/**', handle_game)
        self.page.route('**/api/v1/upgrade/preview', handle_upgrade_preview)
        self.page.route('**/api/v1/upgrade', handle_upgrade)
        self.page.route('**/api/v1/inventory*', handle_inventory)
        self.page.route('**/api/v1/item-defs*', handle_item_defs)

    def send_ws_state(self, new_state: Dict[str, Any]) -> None:
        self.page.wait_for_function('() => window.__mockSockets && window.__mockSockets.some(s => s.readyState === 1)')
        self.current_state = new_state
        self.page.evaluate('(msg) => window.__sendMockWs(msg)', {'type': 'state', 'data': new_state})

    def wait_board(self) -> None:
        self.page.wait_for_selector('.sq:nth-child(64)', timeout=5000)
        assert len(self.page.query_selector_all('.sq')) == 64, 'Board did not render 64 squares'
        self.page.wait_for_selector('.player-panel .p-login:has-text("alice")', timeout=5000)
        self.assert_no_errors()

    def assert_no_errors(self) -> None:
        assert not self.errors, f'Page errors encountered: {self.errors}'

    def drag(self, from_sq: str, to_sq: str) -> None:
        src = self.page.locator(f'.sq[data-square="{from_sq}"]')
        dst = self.page.locator(f'.sq[data-square="{to_sq}"]')
        sb = src.bounding_box()
        db = dst.bounding_box()
        assert sb and db, f'Bounding box missing for {from_sq} -> {to_sq}'
        self.page.mouse.move(sb['x'] + sb['width'] / 2, sb['y'] + sb['height'] / 2)
        self.page.mouse.down()
        self.page.mouse.move(db['x'] + db['width'] / 2, db['y'] + db['height'] / 2, steps=8)
        self.page.mouse.up()


def run_tests(root_dir: str, artifacts_dir: str, headless: bool, chromium_path: Optional[str]) -> bool:
    frontend_dir = os.path.join(root_dir, 'frontend')
    assert os.path.isdir(frontend_dir), f'Frontend dir not found: {frontend_dir}'
    os.makedirs(artifacts_dir, exist_ok=True)

    server, port = start_server(frontend_dir)
    base_url = f'http://127.0.0.1:{port}'
    game_id = '11111111-1111-1111-1111-111111111111'
    game_url = f'{base_url}/game.html?id={game_id}'
    upgrade_url = f'{base_url}/upgrade.html'

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

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exec_path, headless=headless)

        # Desktop Context
        ctx_desktop = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = ctx_desktop.new_page()
        tc = TestContext(page, artifacts_dir, game_id)

        # 1. Click to move
        def t_click_move() -> None:
            tc.post_moves.clear()
            page.goto(game_url)
            tc.wait_board()
            page.locator('.sq[data-square="e2"]').click()
            page.locator('.sq[data-square="e4"]').click()
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 1, f'Expected 1 move POST, got {len(tc.post_moves)}'
            assert tc.post_moves[0].get('uci') == 'e2e4'
            tc.assert_no_errors()
        check('Click to move e2->e4', t_click_move)

        # 2. Drag & drop move
        def t_drag_move() -> None:
            tc.post_moves.clear()
            tc.current_state = make_game_state(game_id=game_id, version=1)
            page.goto(game_url)
            tc.wait_board()
            tc.drag('e2', 'e4')
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 1, f'Expected 1 move POST via drag, got {len(tc.post_moves)}'
            assert tc.post_moves[0].get('uci') == 'e2e4'
            tc.assert_no_errors()
        check('Drag to move e2->e4', t_drag_move)

        # 3. Invalid & offboard drop
        def t_invalid_drop() -> None:
            tc.post_moves.clear()
            tc.current_state = make_game_state(game_id=game_id, version=1)
            page.goto(game_url)
            tc.wait_board()
            # drop to invalid square e5
            tc.drag('e2', 'e5')
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 0, 'Invalid drop sent move request'
            # offboard drop
            sq = page.locator('.sq[data-square="e2"]').bounding_box()
            assert sq
            page.mouse.move(sq['x'] + sq['width'] / 2, sq['y'] + sq['height'] / 2)
            page.mouse.down()
            page.mouse.move(5, 5, steps=5)
            page.mouse.up()
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 0, 'Offboard drop sent move request'
            tc.assert_no_errors()
        check('Invalid and offboard drop', t_invalid_drop)

        # 4. Turn guard & spectator no drag
        def t_guards() -> None:
            tc.post_moves.clear()
            tc.current_state = make_game_state(game_id=game_id, turn='black', you='white')
            page.goto(game_url)
            tc.wait_board()
            tc.drag('e2', 'e4')
            assert len(tc.post_moves) == 0, 'Moved on opponent turn'
            # spectator
            tc.current_state = make_game_state(game_id=game_id, turn='white', you='spectator')
            page.goto(game_url)
            tc.wait_board()
            tc.drag('e2', 'e4')
            assert len(tc.post_moves) == 0, 'Moved as spectator'
            tc.assert_no_errors()
        check('Turn guard and spectator guard', t_guards)

        # 5. Black orientation drag
        def t_black_drag() -> None:
            tc.post_moves.clear()
            tc.current_state = make_game_state(game_id=game_id, turn='black', you='black', legal_moves=['e7e5', 'e7e6'])
            page.goto(game_url)
            tc.wait_board()
            tc.drag('e7', 'e5')
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 1, 'Black orientation drag failed'
            assert tc.post_moves[0].get('uci') == 'e7e5'
            tc.assert_no_errors()
        check('Black orientation drag e7->e5', t_black_drag)

        # 6. Pawn promotion dialog without premature POST
        def t_promotion() -> None:
            tc.post_moves.clear()
            board = [
                {'square': 'a7', 'piece': 'P', 'color': 'white'},
                {'square': 'e1', 'piece': 'K', 'color': 'white'},
                {'square': 'e8', 'piece': 'K', 'color': 'black'},
            ]
            tc.current_state = make_game_state(
                game_id=game_id, board=board, legal_moves=['a7a8q', 'a7a8r', 'a7a8b', 'a7a8n']
            )
            page.goto(game_url)
            tc.wait_board()
            tc.drag('a7', 'a8')
            page.wait_for_timeout(150)
            assert len(tc.post_moves) == 0, 'Move sent before selecting promotion piece'
            promo_title = page.locator(':not(script):not(style):has-text("Превращение пешки")')
            assert promo_title.first.is_visible(), 'Promotion dialog not shown'
            q_btn = page.locator('.promo-btn, button:has-text("Ферзь")').first
            q_btn.click()
            page.wait_for_timeout(100)
            assert len(tc.post_moves) == 1, 'Move not sent after promotion piece selection'
            assert tc.post_moves[0].get('uci') == 'a7a8q'
            tc.assert_no_errors()
        check('Pawn promotion dialog and Queen selection', t_promotion)

        # 7. Check banner show/hide via WS
        def t_check_banner() -> None:
            tc.current_state = make_game_state(game_id=game_id, version=1, check_square=None)
            page.goto(game_url)
            tc.wait_board()
            banner = page.locator('[role="status"]:has-text("Вам шах"), .check-banner')
            assert banner.count() == 0 or not banner.first.is_visible(), 'Check banner visible without check'

            # Emit check on own king (e1 for white) with incremented version
            st_check = copy.deepcopy(tc.current_state)
            st_check['version'] = tc.current_state['version'] + 1
            st_check['check_square'] = 'e1'
            tc.send_ws_state(st_check)
            page.wait_for_timeout(200)
            assert banner.first.is_visible(), 'Check banner not displayed on WS check_square'
            page.screenshot(path=os.path.join(artifacts_dir, 'desktop_check_banner.png'))

            # Clear check with incremented version
            st_clear = copy.deepcopy(st_check)
            st_clear['version'] = st_check['version'] + 1
            st_clear['check_square'] = None
            tc.send_ws_state(st_clear)
            page.wait_for_timeout(200)
            assert banner.count() == 0 or not banner.first.is_visible(), 'Check banner not hidden after check cleared'
            tc.assert_no_errors()
        check('Check banner WS show/hide', t_check_banner)

        # 8. Dep panel direct POST without confirm & FX cleanup check
        def t_dep_panel() -> None:
            tc.post_deps.clear()
            tc.current_state = make_game_state(game_id=game_id, version=1)
            page.goto(game_url)
            tc.wait_board()
            btn_dep = page.locator('button:has-text("Деп")').first
            btn_dep.click()
            page.wait_for_timeout(150)
            # Pick piece e2 from board or panel
            page.locator('.sq[data-square="e2"]').click()
            page.wait_for_timeout(150)

            # Target cards visible
            dep_panel = page.locator('.dep-panel')
            assert dep_panel.is_visible(), 'Dep panel not visible'
            page.screenshot(path=os.path.join(artifacts_dir, 'desktop_dep_panel.png'))

            # Disabled option MUST exist and cannot be clicked to send POST
            dis = page.locator('.dep-panel button:disabled, .dep-panel .dep-row:disabled')
            assert dis.count() > 0, 'Disabled dep option target not found in dep panel'
            try:
                dis.first.click(timeout=300)
            except Exception:
                pass
            assert len(tc.post_deps) == 0, 'Disabled dep option triggered POST'

            # Allowed target click triggers immediate POST /dep
            allowed = page.locator('.dep-panel button:not(:disabled):has-text("50%"), .dep-panel .dep-row:not(:disabled), .dep-panel button:not(:disabled):has-text("Конь")').first
            allowed.click()
            page.wait_for_timeout(200)
            assert len(tc.post_deps) == 1, f'Expected immediate POST /dep, got {len(tc.post_deps)}'
            assert tc.post_deps[0].get('target') == 'N'
            # Confirm dialog should not exist
            risk_modal = page.locator('button:has-text("Рискнуть"), button:has-text("Депнуть")')
            assert risk_modal.count() == 0 or not risk_modal.first.is_visible(), 'Redundant confirm modal shown'

            # Wait for dep FX to finish and ensure own piece is draggable / interactive again
            try:
                page.locator('.dep-overlay').wait_for(state='detached', timeout=4000)
            except Exception:
                pass
            page.wait_for_timeout(200)
            sq_e2 = page.locator('.sq[data-square="e2"]')
            assert 'draggable' in (sq_e2.get_attribute('class') or ''), 'Drag remained disabled after dep FX'
            tc.assert_no_errors()
        check('Dep panel immediate POST without confirm', t_dep_panel)

        # 9. Pointercancel drag cleanup
        def t_pointer_cancel() -> None:
            tc.current_state = make_game_state(game_id=game_id, version=1, status='active', turn='white', you='white')
            page.goto(game_url)
            tc.wait_board()
            page.evaluate("""() => {
              const sq = document.querySelector('.sq[data-square="e2"]');
              if (!sq) return;
              const r = sq.getBoundingClientRect();
              sq.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: r.x + 10, clientY: r.y + 10, pointerId: 1}));
              window.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: r.x + 40, clientY: r.y + 40, pointerId: 1}));
            }""")
            page.wait_for_timeout(100)
            ghost = page.locator('.drag-ghost, .drag-glyph')
            assert ghost.count() > 0 and ghost.first.is_visible(), 'Drag ghost did not appear on pointermove'
            page.evaluate("""() => {
              window.dispatchEvent(new PointerEvent('pointercancel', {bubbles: true, pointerId: 1}));
            }""")
            page.wait_for_timeout(100)
            assert ghost.count() == 0 or not ghost.first.is_visible(), 'Drag ghost remained after pointercancel'
            tc.assert_no_errors()
        check('Pointercancel cleans up drag ghost', t_pointer_cancel)

        # Mobile Context (390x844)
        ctx_mobile = browser.new_context(viewport={'width': 390, 'height': 844})
        m_page = ctx_mobile.new_page()
        m_tc = TestContext(m_page, artifacts_dir, game_id)

        def t_mobile_screenshots() -> None:
            m_tc.current_state = make_game_state(game_id=game_id, check_square='e1')
            m_page.goto(game_url)
            m_tc.wait_board()
            m_page.screenshot(path=os.path.join(artifacts_dir, 'mobile_check_banner.png'))

            btn_dep = m_page.locator('button:has-text("Деп")').first
            btn_dep.click()
            m_page.wait_for_timeout(150)
            # Pick source e2 via bottom sheet panel or board
            src_in_sheet = m_page.locator('.dep-panel [data-square="e2"], .dep-panel button:has-text("e2")').first
            if src_in_sheet.is_visible():
                src_in_sheet.click()
            else:
                m_page.locator('.sq[data-square="e2"]').click()
            m_page.wait_for_timeout(150)
            m_page.screenshot(path=os.path.join(artifacts_dir, 'mobile_dep_panel.png'))
            m_tc.assert_no_errors()
        check('Mobile viewport screenshots (check & dep)', t_mobile_screenshots)

        # 10. Upgrade smoke test (immediate POST without confirm modal)
        def t_upgrade_smoke() -> None:
            u_page = ctx_desktop.new_page()
            u_tc = TestContext(u_page, artifacts_dir, game_id)
            u_page.goto(upgrade_url)
            u_page.wait_for_selector('.item-card', timeout=5000)

            cards = u_page.locator('.item-card')
            assert cards.count() >= 2, 'Upgrade items not rendered'
            cards.nth(0).click()
            cards.nth(1).click()

            btn = u_page.locator('button:has-text("Апгрейд")')
            btn.wait_for(state='visible')
            u_page.wait_for_timeout(150)

            # Rapid double click
            u_tc.post_upgrades.clear()
            btn.click()
            try:
                btn.click(timeout=100)
            except Exception:
                pass
            u_page.wait_for_timeout(200)

            assert len(u_tc.post_upgrades) == 1, f'Expected 1 POST /upgrade without duplicate, got {len(u_tc.post_upgrades)}'
            confirm_btn = u_page.locator('button:has-text("Рискнуть")')
            assert confirm_btn.count() == 0 or not confirm_btn.first.is_visible(), 'Confirm modal "Рискнуть" unexpectedly shown'
            u_tc.assert_no_errors()
        check('Upgrade page immediate POST without confirm modal', t_upgrade_smoke)

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
    parser = argparse.ArgumentParser(description='ChessDep UI Playwright Smoke & Regression Suite')
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
