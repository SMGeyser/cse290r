"""Exercise the Snake executable through a real Windows console.

Watch: python snake/e2e/test_snake.py --visual
Headless: python -m unittest discover -s snake/e2e -v
Only Python's standard library and the .NET 10 SDK are required.
"""

import argparse
import ctypes
from collections import deque
from ctypes import wintypes
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import textwrap
import time
import unittest
import uuid


PROJECT = Path(__file__).resolve().parents[1]
DLL = PROJECT / "bin" / "Debug" / "net10.0" / "Snake.dll"
DOTNET = shutil.which("dotnet")
VISUAL = False
HOLD_SECONDS = 2.0
CURRENT_SCENARIO = ""
SCENARIO_TITLES = {
    "startup_steering_and_quit": "Startup, W / Left Arrow steering, and Escape to quit",
    "reversal_wall_collision_and_restart": "Reject reverse direction, hit wall, restart with R",
    "wall_collision_stops_round": "Hit the right wall and verify the round stays stopped",
    "eating_fruit_grows_snake": "Eat three fruits: verify growth and +10 points each time",
    "restart_after_growth": "Grow, end the round, press R: reset length and score",
    "self_collision_ends_round": "Eat four fruits, turn into the body, verify game over",
    "arrow_up": "Up Arrow changes direction and keeps moving up",
    "arrow_down": "Down Arrow changes direction and keeps moving down",
    "arrow_left": "Left Arrow changes direction and keeps moving left",
    "arrow_right": "Right Arrow changes direction and keeps moving right",
}


class Coord(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]


class SmallRect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_short) for name in ("left", "top", "right", "bottom")]


class BufferInfo(ctypes.Structure):
    _fields_ = [
        ("size", Coord), ("cursor", Coord), ("attributes", wintypes.WORD),
        ("window", SmallRect), ("maximum_size", Coord),
    ]


class KeyEvent(ctypes.Structure):
    _fields_ = [
        ("down", wintypes.BOOL), ("repeat", wintypes.WORD),
        ("virtual_key", wintypes.WORD), ("scan_code", wintypes.WORD),
        ("character", ctypes.c_wchar), ("control_state", wintypes.DWORD),
    ]


class EventData(ctypes.Union):
    _fields_ = [("key", KeyEvent), ("padding", ctypes.c_byte * 16)]


class InputRecord(ctypes.Structure):
    _fields_ = [("event_type", wintypes.WORD), ("event", EventData)]


class GameConsole:
    """A worker owns the console; unittest keeps its own console and output."""

    def __init__(self, seed=None, database_path=None):
        self.arguments = [] if seed is None else ["--seed", str(seed)]
        # Test scores must never change the player's real score history.
        self.database_path = Path(database_path) if database_path is not None else (
            PROJECT / "obj" / "e2e-data" / uuid.uuid4().hex / "scores.db"
        )
        self.arguments += ["--database", str(self.database_path)]
        self.messages = []

    def __enter__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "AttachConsole": ([wintypes.DWORD], wintypes.BOOL),
            "FreeConsole": ([], wintypes.BOOL),
            "CreateFileW": ([wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                             wintypes.HANDLE], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "GetConsoleScreenBufferInfo": ([wintypes.HANDLE, ctypes.POINTER(BufferInfo)], wintypes.BOOL),
            "ReadConsoleOutputCharacterW": ([wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                                             Coord, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "WriteConsoleInputW": ([wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "WriteConsoleOutputCharacterW": ([wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
                                              Coord, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "SetConsoleTitleW": ([wintypes.LPCWSTR], wintypes.BOOL),
            "SetConsoleScreenBufferSize": ([wintypes.HANDLE, Coord], wintypes.BOOL),
            "SetConsoleWindowInfo": ([wintypes.HANDLE, wintypes.BOOL,
                                      ctypes.POINTER(SmallRect)], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = arguments
            function.restype = result

        startup = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 5 if VISUAL else subprocess.SW_HIDE  # SW_SHOW = 5
        self.process = subprocess.Popen(
            [DOTNET, str(DLL), *self.arguments], cwd=PROJECT, startupinfo=startup,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            # The game must inherit console handles, not redirected pipes.
            stdin=None, stdout=None, stderr=None,
        )
        self.handles = []
        try:
            self.api.FreeConsole()
            deadline = time.monotonic() + 5
            while not self.api.AttachConsole(self.process.pid):
                if self.process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"Could not attach to the game's console: {ctypes.WinError(ctypes.get_last_error())}; "
                        f"game exit code: {self.process.poll()}"
                    )
                time.sleep(0.01)
            for name in ("CONIN$", "CONOUT$"):
                handle = self.api.CreateFileW(name, 0xC0000000, 3, None, 3, 0, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handles.append(handle)
            self.input, self.output = self.handles
            if VISUAL:
                title = SCENARIO_TITLES.get(CURRENT_SCENARIO, "Snake E2E")
                self.api.SetConsoleTitleW(f"Snake E2E - {title}")
                info = BufferInfo()
                if not self.api.GetConsoleScreenBufferInfo(self.output, ctypes.byref(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                # Leave room below the game's rows for a live explanation and result.
                if not self.api.SetConsoleScreenBufferSize(
                    self.output, Coord(max(info.size.x, 100), max(info.size.y, 32))
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                window = SmallRect(0, 0, 99, 31)
                if not self.api.SetConsoleWindowInfo(self.output, True, ctypes.byref(window)):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.report("TEST", title)
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def __exit__(self, error_type, error, _traceback):
        try:
            if VISUAL and len(self.handles) == 2:
                # All assertions have finished. Preserve the final board while
                # showing the result instead of letting the snake keep running.
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=5)
                if error_type is None:
                    self.report("PASS", "All checks in this game session passed.")
                else:
                    detail = str(error).splitlines()[0] if str(error) else error_type.__name__
                    self.report("FAIL", f"{error_type.__name__}: {detail}")
                # The worker stays attached so even Escape / Q results remain visible.
                time.sleep(HOLD_SECONDS)
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            for handle in self.handles:
                self.api.CloseHandle(handle)
            self.api.FreeConsole()

    def report(self, label, message):
        if VISUAL:
            entry = f"[{label}] {message}"
            self.messages.append(entry)
            print(entry, flush=True)
            self.show_status()

    def show_status(self):
        if not VISUAL:
            return
        info = BufferInfo()
        if not self.api.GetConsoleScreenBufferInfo(self.output, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Write directly into spare rows without moving the game's drawing cursor.
        lines = ["=" * 98, "AUTOMATED E2E TEST - watch only; keys are sent by the test"]
        recent = [part for message in self.messages[-6:]
                  for part in textwrap.wrap(message, width=98)]
        lines += recent[-6:]
        lines += [""] * (8 - len(lines))
        text = "".join(line[:98].ljust(info.size.x) for line in lines)
        written = wintypes.DWORD()
        if not self.api.WriteConsoleOutputCharacterW(
            self.output, text, len(text), Coord(0, 23), ctypes.byref(written)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def screen(self):
        self.show_status()
        info = BufferInfo()
        if not self.api.GetConsoleScreenBufferInfo(self.output, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        length = info.size.x * min(info.size.y, 32)
        buffer = ctypes.create_unicode_buffer(length + 1)
        read = wintypes.DWORD()
        if not self.api.ReadConsoleOutputCharacterW(
            self.output, buffer, length, Coord(0, 0), ctypes.byref(read)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return "\n".join(
            buffer[:read.value][offset:offset + info.size.x].rstrip()
            for offset in range(0, read.value, info.size.x)
        )

    def wait_for(self, predicate, description, timeout=5):
        self.report("CHECK", description)
        deadline = time.monotonic() + timeout
        last_screen = ""
        while time.monotonic() < deadline:
            last_screen = self.screen()
            if predicate(last_screen):
                state = board(last_screen)
                evidence = ""
                if state is not None:
                    evidence = f" | head={state[1]}, length={len(occupied(last_screen))}, score={score(last_screen)}"
                self.report("OK", description + evidence)
                return last_screen
            if self.process.poll() is not None:
                break
            time.sleep(0.01)
        raise AssertionError(f"Timed out waiting for {description}. Last screen:\n{last_screen}")

    def key(self, virtual_key, character="\0"):
        name = {0x25: "Left Arrow", 0x26: "Up Arrow", 0x27: "Right Arrow",
                0x28: "Down Arrow", 0x1B: "Escape"}.get(virtual_key, character.upper())
        self.report("KEY", f"Press {name}")
        records = (InputRecord * 2)()
        for record, down in zip(records, (True, False)):
            record.event_type = 1  # KEY_EVENT
            record.event.key = KeyEvent(down, 1, virtual_key, 0, character, 0)
        written = wintypes.DWORD()
        if not self.api.WriteConsoleInputW(self.input, records, 2, ctypes.byref(written)):
            raise ctypes.WinError(ctypes.get_last_error())
        assert written.value == 2, "Console did not accept both key events"


def board(screen):
    """Ignore incomplete frames while the game's draw is in progress."""
    lines = screen.splitlines()
    if len(lines) < 20 or lines[2] != "#" * 32 or lines[19] != "#" * 32:
        return None
    rows = lines[3:19]
    if any(len(row) != 32 or row[0] != "#" or row[-1] != "#" for row in rows):
        return None
    cells = [row[1:-1] for row in rows]
    heads = [(x, y) for y, row in enumerate(cells) for x, cell in enumerate(row) if cell == "@"]
    if len(heads) != 1:
        return None
    return cells, heads[0]


def startup_steering_and_quit():
    with GameConsole() as game:
        screen = game.wait_for(lambda s: board(s) is not None, "initial game board")
        cells, head = board(screen)
        assert "SNAKE | Score: 0" in screen, screen
        assert sum(row.count("o") for row in cells) == 2, screen
        assert sum(row.count("*") for row in cells) == 1, screen
        assert head[1] == 8, screen

        game.key(ord("W"), "w")
        screen = game.wait_for(
            lambda s: board(s) is not None and board(s)[1][1] <= 6,
            "W to move the snake upward by two cells",
        )
        _, turned_head = board(screen)
        # An arrow-key turn exercises a second supported input path.
        game.key(0x25)  # VK_LEFT
        screen = game.wait_for(
            lambda s: board(s) is not None and board(s)[1][0] < turned_head[0],
            "Left Arrow to turn the snake left",
        )
        assert "Game over!" not in screen, screen
        game.key(0x1B, "\x1b")  # Escape
        assert game.process.wait(timeout=3) == 0, "Escape did not exit cleanly"


def reversal_wall_collision_and_restart():
    with GameConsole() as game:
        screen = game.wait_for(lambda s: board(s) is not None, "initial game board")
        _, head = board(screen)
        game.key(ord("A"), "a")  # Opposite the initial rightward direction.
        screen = game.wait_for(
            lambda s: board(s) is not None and board(s)[1][0] > head[0],
            "snake to keep moving right after an invalid reversal",
        )
        assert board(screen)[1][1] == 8, screen
        screen = game.wait_for(lambda s: "Press R to restart" in s, "wall collision game over")
        assert "Game over!" in screen, screen
        assert re.search(r"Final score: \d+\.", screen), screen
        assert board(screen)[1] == (29, 8), screen

        game.key(ord("R"), "r")
        screen = game.wait_for(
            lambda s: board(s) is not None and "SNAKE | Score: 0" in s
            and "Game over!" not in s and board(s)[1][0] < 20,
            "R to start a fresh game",
        )
        cells, head = board(screen)
        assert head[1] == 8, screen
        assert sum(row.count("o") for row in cells) == 2, screen
        assert sum(row.count("*") for row in cells) == 1, screen
        game.key(ord("Q"), "q")
        assert game.process.wait(timeout=3) == 0, "Q did not exit cleanly"


ARROWS = {(0, -1): 0x26, (0, 1): 0x28, (-1, 0): 0x25, (1, 0): 0x27}


def occupied(screen):
    cells, _ = board(screen)
    return {(x, y) for y, row in enumerate(cells) for x, cell in enumerate(row) if cell in "@o"}


def fruit(screen):
    cells, _ = board(screen)
    positions = [(x, y) for y, row in enumerate(cells) for x, cell in enumerate(row) if cell == "*"]
    return positions[0] if len(positions) == 1 else None


def score(screen):
    match = re.search(r"SNAKE \| Score: (\d+)", screen)
    return int(match[1]) if match else None


class Player:
    """Steer using only displayed cells and real key events, never game internals."""

    def __init__(self, game):
        self.game = game
        self.screen = game.wait_for(
            lambda s: board(s) is not None and fruit(s) is not None and score(s) == 0,
            "initial board with food",
        )
        self.direction = (1, 0)

    def step(self, direction):
        before = self.screen
        head = board(before)[1]
        target = (head[0] + direction[0], head[1] + direction[1])
        eating = target == fruit(before)
        expected_length = len(occupied(before)) + int(eating)
        expected_score = score(before) + (10 if eating else 0)
        self.game.key(ARROWS[direction])

        def moved(s):
            return board(s) is not None and board(s)[1] == target and (
                len(occupied(s)) == expected_length and score(s) == expected_score
                and fruit(s) is not None
            )

        self.screen = self.game.wait_for(
            lambda s: "Game over!" in s or moved(s),
            f"arrow {direction} to move head from {head} to {target}, "
            f"length {expected_length}, score {expected_score}",
        )
        assert "Game over!" not in self.screen, self.screen
        self.direction = direction

    def eat_fruit(self):
        # Find a safe route from the visible head to the visible fruit. Occupied
        # body cells (including the tail) stay off-limits for this route.
        start = board(self.screen)[1]
        goal = fruit(self.screen)
        blocked = occupied(self.screen)
        queue = deque([(start, [])])
        visited = {start}
        while queue:
            position, path = queue.popleft()
            if position == goal:
                assert path, "Fruit must not overlap the head"
                for direction in path:
                    self.step(direction)
                return
            for direction in ARROWS:
                if not path and direction == (-self.direction[0], -self.direction[1]):
                    continue
                target = (position[0] + direction[0], position[1] + direction[1])
                if (0 <= target[0] < 30 and 0 <= target[1] < 16
                        and target not in blocked and target not in visited):
                    visited.add(target)
                    queue.append((target, path + [direction]))
        raise AssertionError(f"No safe path to fruit at {goal}:\n{self.screen}")


def assert_round_stopped(game, screen):
    game.report("CHECK", "Board and score must stay frozen for more than three movement ticks")
    assert "Game over!" in screen and "Press R to restart" in screen, screen
    frozen_board = board(screen)
    frozen_score = score(screen)
    # More than three movement ticks must pass without any movement or growth.
    deadline = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        current = game.screen()
        assert board(current) == frozen_board and score(current) == frozen_score, current
        assert game.process.poll() is None, "Round ended by terminating the app instead of waiting for restart"
        time.sleep(0.02)
    game.report("OK", "Round stopped: board and score unchanged; app is waiting for restart")


def wall_collision_stops_round():
    with GameConsole(seed=2026) as game:
        Player(game)
        screen = game.wait_for(lambda s: "Press R to restart" in s, "wall collision")
        assert board(screen)[1] == (29, 8), screen
        assert_round_stopped(game, screen)


def eating_fruit_grows_snake():
    with GameConsole(seed=2026) as game:
        player = Player(game)
        assert len(occupied(player.screen)) == 3, player.screen
        for eaten in range(1, 4):
            game.report("ACTION", f"Eat fruit {eaten}/3; expect length {3 + eaten} and score {10 * eaten}")
            old_fruit = fruit(player.screen)
            player.eat_fruit()
            assert len(occupied(player.screen)) == 3 + eaten, player.screen
            assert score(player.screen) == 10 * eaten, player.screen
            assert board(player.screen)[1] == old_fruit, player.screen
            assert fruit(player.screen) not in occupied(player.screen), player.screen
            game.report("OK", f"Fruit {eaten}/3 eaten: length={len(occupied(player.screen))}, score={score(player.screen)}; new fruit is outside snake")


def restart_after_growth():
    with GameConsole(seed=2026) as game:
        player = Player(game)
        player.eat_fruit()
        assert len(occupied(player.screen)) == 4 and score(player.screen) == 10, player.screen
        screen = game.wait_for(lambda s: "Press R to restart" in s, "grown snake to end its round")
        assert_round_stopped(game, screen)
        game.key(ord("R"), "r")
        screen = game.wait_for(
            lambda s: board(s) is not None and len(occupied(s)) == 3
            and score(s) == 0 and fruit(s) is not None and "Game over!" not in s,
            "R to reset the grown snake and score",
        )
        head = board(screen)[1]
        assert head[1] == 8 and 15 <= head[0] < 20, screen
        game.wait_for(
            lambda s: board(s) is not None and board(s)[1] == (head[0] + 1, head[1]),
            "new round to resume moving right",
        )
        game.key(ord("Q"), "q")
        assert game.process.wait(timeout=3) == 0


def self_collision_ends_round():
    with GameConsole(seed=2026) as game:
        player = Player(game)
        for _ in range(4):
            game.report("ACTION", f"Eat fruit {_ + 1}/4 to grow enough for self-collision")
            player.eat_fruit()
        assert len(occupied(player.screen)) == 7 and score(player.screen) == 40, player.screen

        # After eating four fruits, a four-step square leads into the head's
        # original cell while it is still a non-tail body segment.
        origin = board(player.screen)[1]
        route = None
        for first in ARROWS:
            if first == (-player.direction[0], -player.direction[1]):
                continue
            for turn in (-1, 1):
                direction = first
                position = origin
                candidate = []
                for _ in range(4):
                    candidate.append(direction)
                    position = (position[0] + direction[0], position[1] + direction[1])
                    if len(candidate) < 4 and (
                        not (0 <= position[0] < 30 and 0 <= position[1] < 16)
                        or position in occupied(player.screen) or position == fruit(player.screen)
                    ):
                        break
                    direction = (-turn * direction[1], turn * direction[0])
                if len(candidate) == 4:
                    route = candidate
                    break
            if route is not None:
                break
        assert route is not None, f"No clear square for self-collision:\n{player.screen}"
        for direction in route[:3]:
            player.step(direction)
        before_collision = board(player.screen)
        assert origin in occupied(player.screen), player.screen
        game.report("ACTION", f"Turn into own body at {origin}; expect game over and score 40")
        game.key(ARROWS[route[3]])
        screen = game.wait_for(lambda s: "Press R to restart" in s, "body collision to end round")
        assert board(screen) == before_collision, screen
        assert score(screen) == 40 and "Final score: 40." in screen, screen
        assert_round_stopped(game, screen)


def arrow_changes_direction(direction):
    with GameConsole(seed=2026) as game:
        player = Player(game)
        # Left/right turns begin by going up so neither is a forbidden reversal
        # or a repeat of the initial rightward direction.
        if direction[0]:
            player.step((0, -1))
        player.step(direction)
        player.step(direction)
        assert "Game over!" not in player.screen, player.screen


@unittest.skipUnless(sys.platform == "win32", "E2E driver requires the Windows console API")
class ConsoleScenarioTestCase(unittest.TestCase):
    worker_script = Path(__file__).resolve()

    @classmethod
    def setUpClass(cls):
        if DOTNET is None:
            raise RuntimeError("Install the .NET 10 SDK before running these tests")
        result = subprocess.run(
            [DOTNET, "build", str(PROJECT / "Snake.csproj"), "--nologo"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError(f"Snake build failed:\n{result.stdout}\n{result.stderr}")

    def run_scenario(self, name):
        if VISUAL:
            print(f"\n{'=' * 72}\nTEST: {SCENARIO_TITLES[name]}\n"
                  "Watch the game window; the test sends the keys automatically.", flush=True)
            self.run_visible_scenario(name)
            return
        result = subprocess.run(
            [sys.executable, str(self.worker_script), "--scenario", name],
            capture_output=True, text=True, timeout=90,
            # The worker starts detached so attaching cannot affect the test runner's console.
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_visible_scenario(self, name):
        # Keep narration connected through a pipe: attaching the worker to the
        # game's console would otherwise detach its original terminal handles.
        command = [sys.executable, "-u", str(self.worker_script),
                   "--scenario", name, "--visual", "--hold", str(HOLD_SECONDS)]
        output = []
        with subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW,
        ) as worker:
            def stream_output():
                for line in worker.stdout:
                    output.append(line)
                    print(line, end="", flush=True)

            reader = threading.Thread(target=stream_output, daemon=True)
            reader.start()
            try:
                worker.wait(timeout=90 + HOLD_SECONDS)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                # Close the worker and its game together on a hang or Ctrl+C.
                subprocess.run(
                    ["taskkill", "/PID", str(worker.pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                )
                if isinstance(error, KeyboardInterrupt):
                    raise
                self.fail(f"FAIL: {SCENARIO_TITLES[name]} timed out")
            finally:
                reader.join(timeout=5)
            self.assertEqual(worker.returncode, 0, "".join(output))

class SnakeEndToEndTests(ConsoleScenarioTestCase):
    def test_startup_steering_and_quit(self):
        self.run_scenario("startup_steering_and_quit")

    def test_reversal_wall_collision_and_restart(self):
        self.run_scenario("reversal_wall_collision_and_restart")

    def test_wall_collision_stops_round(self):
        self.run_scenario("wall_collision_stops_round")

    def test_eating_three_fruits_grows_snake_and_scores_each_time(self):
        self.run_scenario("eating_fruit_grows_snake")

    def test_r_restarts_after_growth_and_resets_score(self):
        self.run_scenario("restart_after_growth")

    def test_self_collision_ends_round_after_eating_four_fruits(self):
        self.run_scenario("self_collision_ends_round")

    def test_up_arrow_changes_direction(self):
        self.run_scenario("arrow_up")

    def test_down_arrow_changes_direction(self):
        self.run_scenario("arrow_down")

    def test_left_arrow_changes_direction(self):
        self.run_scenario("arrow_left")

    def test_right_arrow_changes_direction(self):
        self.run_scenario("arrow_right")


def run_cli(scenarios, description=__doc__):
    global VISUAL, HOLD_SECONDS, CURRENT_SCENARIO
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--visual", action="store_true", help="Show each real game console with live narration and PASS / FAIL")
    parser.add_argument("--hold", type=float, default=2.0, help="Seconds to keep each visual result on screen (default: 2)")
    parser.add_argument("--scenario", choices=scenarios, help=argparse.SUPPRESS)
    options = parser.parse_args()
    if not 0 <= options.hold <= 30:
        parser.error("--hold must be between 0 and 30 seconds")
    if options.visual and sys.platform != "win32":
        parser.error("Visual E2E tests require Windows")
    VISUAL = options.visual
    HOLD_SECONDS = options.hold
    CURRENT_SCENARIO = options.scenario or ""
    if options.scenario:
        scenarios[options.scenario]()
    else:
        unittest.main(argv=[sys.argv[0]], verbosity=2)


if __name__ == "__main__":
    run_cli({
        "startup_steering_and_quit": startup_steering_and_quit,
        "reversal_wall_collision_and_restart": reversal_wall_collision_and_restart,
        "wall_collision_stops_round": wall_collision_stops_round,
        "eating_fruit_grows_snake": eating_fruit_grows_snake,
        "restart_after_growth": restart_after_growth,
        "self_collision_ends_round": self_collision_ends_round,
        "arrow_up": lambda: arrow_changes_direction((0, -1)),
        "arrow_down": lambda: arrow_changes_direction((0, 1)),
        "arrow_left": lambda: arrow_changes_direction((-1, 0)),
        "arrow_right": lambda: arrow_changes_direction((1, 0)),
    })
