using Snake;

namespace SnakeTests;

public sealed class OptionsAndRenderingTests
{
    [Fact]
    public void DefaultsUseRandomSeedAndDatabaseBesideExecutable()
    {
        var options = GameOptions.Parse([]);
        Assert.Null(options.Seed);
        Assert.Equal(Path.Combine(AppContext.BaseDirectory, "scores.db"), options.DatabasePath);
    }

    [Theory]
    [InlineData("0", 0)]
    [InlineData("-1", -1)]
    [InlineData("2147483647", int.MaxValue)]
    [InlineData("-2147483648", int.MinValue)]
    public void ParsesIntegerSeeds(string text, int seed)
        => Assert.Equal(seed, GameOptions.Parse(["--seed", text]).Seed);

    [Theory]
    [InlineData("--seed")]
    [InlineData("--database")]
    [InlineData("--unknown")]
    public void MissingValueIsRejected(string flag)
        => Assert.Throws<ArgumentException>(() => GameOptions.Parse([flag]));

    [Theory]
    [InlineData("--seed", "abc")]
    [InlineData("--seed", "2147483648")]
    [InlineData("--seed", "1.5")]
    [InlineData("--database", "")]
    [InlineData("--database", "  ")]
    [InlineData("--unknown", "value")]
    public void InvalidOptionIsRejected(string flag, string value)
        => Assert.Contains("Usage:", Assert.Throws<ArgumentException>(() => GameOptions.Parse([flag, value])).Message);

    [Fact]
    public void BothOptionOrdersAndPathsWithSpacesAreAccepted()
    {
        var first = GameOptions.Parse(["--seed", "42", "--database", "data/my scores;2026.db"]);
        var second = GameOptions.Parse(["--database", "data/my scores;2026.db", "--seed", "42"]);
        Assert.Equal(first, second);
        Assert.Equal(42, first.Seed);
        Assert.Equal("data/my scores;2026.db", first.DatabasePath);
    }

    [Fact]
    public void RepeatedOptionsUseLastValue()
    {
        var options = GameOptions.Parse(["--seed", "1", "--seed", "2", "--database", "a.db", "--database", "b.db"]);
        Assert.Equal(new GameOptions(2, "b.db"), options);
    }

    [Fact]
    public void BoardContainsExactBoundariesControlsEntitiesAndHistory()
    {
        var game = new SnakeGame(new SequenceRandom());
        string output = BoardRenderer.Render(game, new(7, 40));
        var lines = output.Split(Environment.NewLine);
        Assert.Equal("SNAKE | Score: 0 | Attempts: 7 | Best: 40", lines[0].TrimEnd());
        Assert.Contains("WASD", lines[1]);
        Assert.Contains("Esc / Q", lines[1]);
        Assert.Equal(new string('#', 32), lines[2]);
        Assert.Equal(new string('#', 32), lines[19]);
        Assert.All(lines[3..19], line =>
        {
            Assert.Equal(32, line.Length);
            Assert.StartsWith("#", line);
            Assert.EndsWith("#", line);
        });
        Assert.Equal('@', lines[11][16]);
        Assert.Equal('o', lines[11][15]);
        Assert.Equal('*', lines[3][1]);
        Assert.Equal(1, output.Count(c => c == '@'));
        Assert.Equal(2, string.Concat(lines[3..19]).Count(c => c == 'o'));
    }

    [Fact]
    public void WinningBoardHasNoFoodAndWinningResultIncludesScoreAndRestart()
    {
        var game = Games.Won();
        Assert.DoesNotContain('*', BoardRenderer.Render(game, new(1, 30)));
        string result = BoardRenderer.Result(game, new(1, 30));
        Assert.Contains("You win!", result);
        Assert.Contains("Final score: 30.", result);
        Assert.Contains("Press R to restart", result);
        Assert.Contains("Attempts: 1 | Best: 30", result);
    }

    [Fact]
    public void CollisionResultShowsGameOverAndQuitResultOmitsRestart()
    {
        Assert.Contains("Game over!", BoardRenderer.Result(Games.SelfCollision(), new(1, 40)));
        var game = new SnakeGame();
        game.HandleKey(ConsoleKey.Q);
        string result = BoardRenderer.Result(game, new(2, 40));
        Assert.Contains("Game ended.", result);
        Assert.Contains("Final score: 0.", result);
        Assert.DoesNotContain("Press R", result);
        Assert.Equal(3, result.Split(Environment.NewLine).Length);
    }
}
