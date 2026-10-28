using Microsoft.Data.Sqlite;
using Snake;

namespace SnakeTests;

internal sealed class FakeTerminal : IGameTerminal
{
    public bool IsRedirected { get; set; }
    public bool CursorVisible { get; set; } = true;
    public Queue<ConsoleKey> Input { get; } = new();
    public Queue<ConsoleKey[]> Ticks { get; } = new();
    public Queue<ConsoleKey> Responses { get; } = new();
    public List<string> Frames { get; } = [];
    public List<string> Lines { get; } = [];
    public List<string> Errors { get; } = [];
    public bool BufferKeysAtRoundEnd { get; set; }
    public int ClearCount { get; private set; }
    public int BufferedKeysRead { get; private set; }
    public bool KeyAvailable => Input.Count > 0;
    public ConsoleKey ReadKey()
    {
        if (Input.TryDequeue(out var key))
        {
            BufferedKeysRead++;
            return key;
        }
        return Responses.Dequeue();
    }
    public void Clear() => ClearCount++;
    public void WriteFrame(string frame) => Frames.Add(frame);
    public void WriteError(string text) => Errors.Add(text);
    public void WriteLine(string text)
    {
        Lines.Add(text);
        if (BufferKeysAtRoundEnd && text.StartsWith("Game over!"))
        {
            Input.Enqueue(ConsoleKey.UpArrow);
            Input.Enqueue(ConsoleKey.DownArrow);
        }
    }
}

internal sealed class FakeClock(FakeTerminal terminal) : IGameClock
{
    public bool IsTickPending { get; private set; }
    public void StartTick()
    {
        IsTickPending = true;
        if (terminal.Ticks.TryDequeue(out var keys))
            foreach (var key in keys)
                terminal.Input.Enqueue(key);
    }
    public void WaitForInput() => IsTickPending = false;
}

internal sealed class FakeStore : IScoreStore
{
    public ScoreSummary Summary { get; set; } = new(0, 0);
    public List<(int Score, string Outcome)> Attempts { get; } = [];
    public Exception? ReadError { get; set; }
    public Exception? SaveError { get; set; }
    public ScoreSummary GetSummary() => ReadError is null ? Summary : throw ReadError;
    public ScoreSummary RecordAttempt(int score, string outcome)
    {
        if (SaveError is not null)
            throw SaveError;
        Attempts.Add((score, outcome));
        Summary = new(Summary.Attempts + 1, Math.Max(Summary.BestScore, score));
        return Summary;
    }
}

public sealed class ApplicationTests
{
    [Fact]
    public void BadArgumentsFailBeforeOpeningDatabaseOrChangingCursor()
    {
        var terminal = new FakeTerminal();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => throw new Exception("Must not open"));
        Assert.Equal(1, app.Run(["--seed", "bad"]));
        Assert.Equal([GameOptions.Usage], terminal.Errors);
        Assert.True(terminal.CursorVisible);
        Assert.Empty(terminal.Frames);
    }

    [Fact]
    public void RedirectedTerminalExplainsHowToRunWithoutOpeningDatabase()
    {
        var terminal = new FakeTerminal { IsRedirected = true };
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => throw new Exception("Must not open"));
        Assert.Equal(0, app.Run([]));
        Assert.Contains("interactive terminal", Assert.Single(terminal.Lines));
        Assert.Empty(terminal.Errors);
    }

    [Theory]
    [InlineData(ConsoleKey.Q, true)]
    [InlineData(ConsoleKey.Escape, false)]
    public void QuitSavesOnceRestoresCursorAndDoesNotAdvance(ConsoleKey key, bool cursorVisible)
    {
        var terminal = new FakeTerminal { CursorVisible = cursorVisible };
        terminal.Ticks.Enqueue([key]);
        var store = new FakeStore();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => store);
        Assert.Equal(0, app.Run([]));
        Assert.Equal([(0, "quit")], store.Attempts);
        Assert.Equal(cursorVisible, terminal.CursorVisible);
        Assert.Single(terminal.Frames);
        Assert.Contains("Score saved | Attempts: 1 | Best: 0", terminal.Lines[0]);
        Assert.Equal("", terminal.Lines[^1]);
    }

    [Fact]
    public void OptionsReachDatabaseFactoryAndSeededRandomReachesGame()
    {
        var terminal = new FakeTerminal();
        terminal.Ticks.Enqueue([ConsoleKey.Q]);
        var store = new FakeStore { Summary = new(4, 90) };
        string? requestedPath = null;
        var app = new SnakeApplication(terminal, new FakeClock(terminal), path =>
        {
            requestedPath = path;
            return store;
        }, random =>
        {
            Assert.Equal(new Random(2026).Next(), random.Next());
            return new SnakeGame(random);
        });
        Assert.Equal(0, app.Run(["--seed", "2026", "--database", "my history.db"]));
        Assert.Equal("my history.db", requestedPath);
        Assert.Contains("Attempts: 4 | Best: 90", terminal.Frames[0]);
        Assert.Contains("Attempts: 5 | Best: 90", terminal.Lines[0]);
    }

    [Fact]
    public void CollisionSavesExactlyOnceAndDrainsBufferedKeysBeforeExitChoice()
    {
        var terminal = new FakeTerminal { BufferKeysAtRoundEnd = true };
        terminal.Responses.Enqueue(ConsoleKey.Spacebar);
        var store = new FakeStore();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => store,
            _ => new SnakeGame(new SequenceRandom()));
        Assert.Equal(0, app.Run([]));
        Assert.Equal([(0, "collision")], store.Attempts);
        Assert.Equal(2, terminal.BufferedKeysRead);
        Assert.Equal(15, terminal.Frames.Count); // Initial board plus 14 valid moves.
        Assert.Contains("Game over!", terminal.Lines[0]);
    }

    [Fact]
    public void RestartStartsFreshRoundWhilePreservingHistory()
    {
        var terminal = new FakeTerminal();
        for (int i = 0; i < 15; i++)
            terminal.Ticks.Enqueue([]);
        terminal.Ticks.Enqueue([ConsoleKey.Q]);
        terminal.Responses.Enqueue(ConsoleKey.R);
        var store = new FakeStore();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => store,
            _ => new SnakeGame(new SequenceRandom()));
        Assert.Equal(0, app.Run([]));
        Assert.Equal([(0, "collision"), (0, "quit")], store.Attempts);
        Assert.Equal(2, terminal.ClearCount);
        Assert.Contains("Score: 0 | Attempts: 1 | Best: 0", terminal.Frames[^1]);
    }

    [Fact]
    public void QuittingAfterEatingSavesEarnedScore()
    {
        var terminal = new FakeTerminal();
        terminal.Ticks.Enqueue([ConsoleKey.UpArrow]);
        terminal.Ticks.Enqueue([ConsoleKey.Q]);
        var store = new FakeStore();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => store,
            _ => new SnakeGame(new SequenceRandom(2, 0), 3, 2));
        Assert.Equal(0, app.Run([]));
        Assert.Equal([(10, "quit")], store.Attempts);
        Assert.Contains("Score: 10", terminal.Frames[^1]);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void WinningSavesFinalScoreAndCanRestart(bool restart)
    {
        var terminal = new FakeTerminal();
        terminal.Ticks.Enqueue([ConsoleKey.UpArrow]);
        terminal.Ticks.Enqueue([ConsoleKey.LeftArrow]);
        terminal.Ticks.Enqueue([]);
        terminal.Responses.Enqueue(restart ? ConsoleKey.R : ConsoleKey.Spacebar);
        if (restart)
            terminal.Ticks.Enqueue([ConsoleKey.Q]);
        var store = new FakeStore();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => store,
            _ => new SnakeGame(new SequenceRandom(2, 1, 0), 3, 2));
        Assert.Equal(0, app.Run([]));
        Assert.Equal((30, "won"), store.Attempts[0]);
        Assert.Equal(restart ? 2 : 1, store.Attempts.Count);
        Assert.Contains("You win!", terminal.Lines[0]);
        if (restart)
        {
            Assert.Equal((0, "quit"), store.Attempts[1]);
            Assert.Contains("Score: 0 | Attempts: 1 | Best: 30", terminal.Frames[^1]);
        }
    }

    [Theory]
    [InlineData("open", "io")]
    [InlineData("read", "sqlite")]
    [InlineData("save", "denied")]
    [InlineData("save", "io")]
    [InlineData("save", "sqlite")]
    public void StorageFailuresAreReportedAndCursorRestored(string stage, string kind)
    {
        Exception error = kind switch
        {
            "io" => new IOException("Disk failure"),
            "denied" => new UnauthorizedAccessException("Access denied"),
            _ => new SqliteException("Database failure", 14)
        };
        var terminal = new FakeTerminal();
        terminal.Ticks.Enqueue([ConsoleKey.Q]);
        var store = new FakeStore
        {
            ReadError = stage == "read" ? error : null,
            SaveError = stage == "save" ? error : null
        };
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => stage == "open" ? throw error : store);
        Assert.Equal(1, app.Run([]));
        Assert.Contains(error.Message, Assert.Single(terminal.Errors));
        Assert.True(terminal.CursorVisible);
        Assert.DoesNotContain(terminal.Lines, line => line.Contains("Score saved"));
        Assert.Empty(store.Attempts);
    }

    [Fact]
    public void UnexpectedFailuresPropagateButStillRestoreCursor()
    {
        var terminal = new FakeTerminal();
        var app = new SnakeApplication(terminal, new FakeClock(terminal), _ => throw new InvalidOperationException("Bug"));
        Assert.Throws<InvalidOperationException>(() => app.Run([]));
        Assert.True(terminal.CursorVisible);
        Assert.Equal("", terminal.Lines[^1]);
    }

    [Fact]
    public void RealClockFinishesTickAndCanRestart()
    {
        var clock = new GameClock();
        clock.StartTick();
        Assert.True(clock.IsTickPending);
        var deadline = System.Diagnostics.Stopwatch.StartNew();
        while (clock.IsTickPending && deadline.Elapsed < TimeSpan.FromSeconds(5))
            clock.WaitForInput();
        Assert.False(clock.IsTickPending);
        clock.StartTick();
        Assert.True(clock.IsTickPending);
    }
}
