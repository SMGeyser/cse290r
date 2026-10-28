"""Verify real gameplay writes a real SQLite file and survives relaunch.

Watch: python snake/integration/test_score_database.py --visual
Headless: python -m unittest discover -s snake/integration -v
"""

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))
import test_snake as game


SCENARIO = "sqlite_persistence"
game.SCENARIO_TITLES[SCENARIO] = "SQLite: save three attempts, restart, relaunch, verify stored scores"


def read_attempts(database):
    assert database.is_file(), f"SQLite file was not created: {database}"
    # This is a separate SQLite implementation, not ScoreStore or a mock.
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        rows = connection.execute(
            "SELECT Id, Score, Outcome, FinishedAt FROM Attempts ORDER BY Id"
        ).fetchall()
        count, best = connection.execute(
            "SELECT COUNT(*), COALESCE(MAX(Score), 0) FROM Attempts"
        ).fetchone()
        assert count == len(rows)
        assert best == max((row[1] for row in rows), default=0)
    for row in rows:
        timestamp = datetime.fromisoformat(row[3])
        assert timestamp.utcoffset() == timedelta(0), f"Timestamp must be UTC: {row}"
    return rows


def verify_attempts(console, database, expected):
    actual = read_attempts(database)
    assert [row[:3] for row in actual] == expected, f"Expected {expected}, got {actual} in {database}"
    console.report("DB OK", f"SQLite rows (attempt, score, outcome): {expected}")


def sqlite_persistence():
    # Preserve the resulting file as a build artifact for manual inspection.
    database = game.PROJECT / "obj" / "integration" / uuid.uuid4().hex / "scores.db"
    with game.GameConsole(seed=2026, database_path=database) as console:
        player = game.Player(console)
        console.report("CHECK", "Fresh SQLite database must have zero attempts")
        verify_attempts(console, database, [])
        assert "Attempts: 0 | Best: 0" in player.screen, player.screen

        console.report("ACTION", "Eat one fruit, then hit the wall; expect attempt 1 with score 10")
        player.eat_fruit()
        assert game.score(player.screen) == 10, player.screen
        verify_attempts(console, database, [])  # No partial or duplicate attempt.
        screen = console.wait_for(
            lambda s: "Score saved | Attempts: 1 | Best: 10" in s,
            "first round to save its score to SQLite",
        )
        assert "Game over!" in screen and "Final score: 10." in screen, screen
        verify_attempts(console, database, [(1, 10, "collision")])
        game.assert_round_stopped(console, screen)
        verify_attempts(console, database, [(1, 10, "collision")])

        console.report("ACTION", "Press R; confirm history remains, then Q saves a zero-score attempt")
        console.key(ord("R"), "r")
        screen = console.wait_for(
            lambda s: game.board(s) is not None and game.score(s) == 0
            and "Attempts: 1 | Best: 10" in s and "Game over!" not in s,
            "restart to preserve saved history while resetting current score",
        )
        verify_attempts(console, database, [(1, 10, "collision")])
        console.key(ord("Q"), "q")
        assert console.process.wait(timeout=5) == 0, "Q failed to save and exit cleanly"
        verify_attempts(console, database, [(1, 10, "collision"), (2, 0, "quit")])

    with game.GameConsole(seed=2026, database_path=database) as console:
        player = game.Player(console)
        console.report("CHECK", "New game process must load two attempts and best score 10")
        assert "Attempts: 2 | Best: 10" in player.screen, player.screen
        verify_attempts(console, database, [(1, 10, "collision"), (2, 0, "quit")])
        console.report("ACTION", "Eat two fruits, then Escape; expect attempt 3 with score 20")
        player.eat_fruit()
        player.eat_fruit()
        assert game.score(player.screen) == 20, player.screen
        console.key(0x1B, "\x1b")
        assert console.process.wait(timeout=5) == 0, "Escape failed to save and exit cleanly"
        # Both game processes have exited: read the committed file from disk.
        verify_attempts(console, database, [(1, 10, "collision"), (2, 0, "quit"), (3, 20, "quit")])
        console.report("DB OK", f"Verified database retained at: {database}")


class ScoreDatabaseIntegrationTests(game.ConsoleScenarioTestCase):
    worker_script = Path(__file__).resolve()

    def test_sqlite_saves_each_attempt_and_persists_across_restarts(self):
        self.run_scenario(SCENARIO)


if __name__ == "__main__":
    game.run_cli({SCENARIO: sqlite_persistence}, description=__doc__)
