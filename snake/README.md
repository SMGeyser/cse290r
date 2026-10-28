# Snake

A simple C# console game. Requires the .NET 10 SDK and an interactive terminal
at least 70 columns wide and 24 rows tall.

From the repository root, run:

```sh
dotnet run --project snake
```

Use the arrow keys or WASD to steer. Eat `*` to grow and earn 10 points.
Avoid the walls and your own body. Press Esc or Q to quit, or R after a game
ends to restart. Fill the board to win.

For repeatable food placement, optionally pass an integer seed:

```sh
dotnet run --project snake -- --seed 2026
```

## Saved scores

Each finished round is saved in a SQLite file named `scores.db` beside the
executable. With `dotnet run`, this is normally
`snake/bin/Debug/net10.0/scores.db`. Records survive restarting rounds and
relaunching the app. The game displays the number of saved attempts and the
best score.

The `Attempts` table stores an incrementing `Id`, `Score`, `Outcome`
(`collision`, `won`, or `quit`), and a UTC `FinishedAt` timestamp. The attempt
count is `COUNT(*)` of these records, so each attempt's score is preserved.
Q and Escape save the current round before exiting. Closing or forcibly
terminating the process does not save an unfinished round.

To choose the database file (parent folders are created automatically):

```sh
dotnet run --project snake -- --database snake/my-scores.db
```

Storage uses [Microsoft.Data.Sqlite](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/).
The first build restores its NuGet dependencies.

## Unit tests and coverage

From the repository root, run the tests and enforce coverage:

```powershell
./snake/unit/run-tests.ps1
```

The command runs 85 xUnit cases, generates Cobertura XML and an HTML report,
and fails if either line coverage or branch coverage is **90% or lower**.
The first build restores xUnit and Coverlet from NuGet. No global tools are needed.

The measured coverage is **95.24% of application lines** and **95.56% of
application branches**. All C# application files are included, including the
executable entry point and the real terminal adapter. Test code and external
dependency assemblies are outside the application measurement. The unit tests
use a scripted terminal and clock to exercise round flow without waiting for
keyboard input; storage component tests use isolated, real SQLite files.

Open `snake/unit/TestResults/latest.html` for the current per-class report,
uncovered line numbers, raw coverage, and test results. Generated reports and
test databases are ignored by Git. The uncovered source lines are the entry
point and real console adapter, exercised by the separate E2E suite; E2E
coverage is not added to the unit test measurement.

The tests cover:

- Initial state, board size validation, seed reproducibility, food placement,
  regular movement, and an immutable public view of the snake.
- All arrow/WASD keys, every reverse direction, ignored/repeated keys, one turn
  per tick, subsequent turns, and immediate Q/Escape handling.
- Each wall, self-collision after growth, entering a vacated tail cell, growth
  and points per fruit, winning a full board, and frozen completed rounds.
- Board boundaries, entities, saved history, and collision/win/quit messages.
- Argument defaults, flag order, missing/unknown/invalid values, integer limits,
  repeated options, and database paths containing spaces and semicolons.
- Fresh rounds, restart after collision or victory, saved scores on quit/win/
  collision, buffered input, history preservation, and cursor restoration.
- Database creation, every outcome, UTC timestamps, zero/duplicate/maximum
  scores, reopening, constraints, SQL injection rejection, corrupt files,
  inaccessible paths, and failures when opening, reading, or saving storage.

For tests without the coverage check:

```sh
dotnet test snake/unit/unit.csproj
```

The rules and orchestration live in `SnakeGame.cs` and `SnakeApplication.cs`;
`Program.cs` connects them to the real console, clock, and score store.

## SQLite integration test

Watch the integration test, including live database checks:

```sh
python snake/integration/test_score_database.py --visual
```

Or run it headlessly:

```sh
python -m unittest discover -s snake/integration -v
```

The test plays real rounds and independently reads the SQLite file with Python's
`sqlite3` module. It verifies:

- A new database starts with zero attempts; ongoing rounds do not add records.
- A collision saves score 10 exactly once, and R preserves history.
- Q saves a second, zero-score attempt.
- Relaunching the app loads two attempts and best score 10.
- Eating two fruits and pressing Escape saves a third attempt with score 20.
- All three scores, outcomes, UTC timestamps, and SQLite integrity are valid
  after the game exits.

The test keeps its database under `snake/obj/integration/<run-id>/scores.db`
for inspection. Gameplay E2E tests use separate files under `snake/obj/e2e-data`.
Tests never write to the player's normal score file. Both test suites require
Windows for the console driver; no extra Python packages are needed.

## End-to-end tests

On Windows, with Python 3 and the .NET 10 SDK installed, watch the tests from the
repository root:

```sh
python snake/e2e/test_snake.py --visual
```

Each test opens the actual game in a visible terminal. Below the board, live
notes show which keys the test presses, what it expects, and the observed head
position, snake length, and score. A **PASS** or **FAIL** result stays on screen
for two seconds before the next test. Narration also streams to the launching
terminal, which ends with the overall test results and failure details.

Watch without pressing keys in the game window, since that would interfere
with the automated controls. To keep each result visible longer:

```sh
python snake/e2e/test_snake.py --visual --hold 5
```

For a headless automated run:

```sh
python -m unittest discover -s snake/e2e -v
```

Both modes run the same tests. The suite builds the game, launches the actual
executable in a Windows console, sends keyboard events, and reads the rendered
screen. No additional Python packages are needed. Each game process is cleaned
up even if a check fails.

The ten tests cover:

- Initial board, snake and food; WASD and arrow-key steering; Escape to quit.
- Rejected reverse direction; wall collision and game over; R to restart with
  a fresh board and zero score; Q to quit.
- Wall collision leaves the board and score frozen while the app awaits input.
- Eating three fruits grows the snake by one cell and adds 10 points each time;
  replacement fruit appears outside the snake.
- R resets a grown snake to three cells and zero score, then resumes movement.
- Eating four fruits, then turning into the body, ends and freezes the round.
- Each of the four arrow keys changes direction and continues moving that way.

Growth and self-collision scenarios use `--seed 2026` for repeatable food
placement. The driver finds routes from the rendered board and steers with real
arrow-key events; it does not inject food, alter the snake, or bypass gameplay.

The console driver is Windows-only; the tests are skipped on other platforms.
Winning is covered by the unit tests; the E2E suite does not yet fill the entire board.
