using Snake;

namespace SnakeTests;

internal sealed class SequenceRandom(params int[] indexes) : Random
{
    private readonly Queue<int> indexes = new(indexes);
    public override int Next(int maxValue)
    {
        int value = indexes.Count == 0 ? 0 : indexes.Dequeue();
        Assert.InRange(value, 0, maxValue - 1);
        return value;
    }
}

internal sealed class FixedRandom(int index) : Random
{
    public override int Next(int maxValue) => index;
}

internal static class Games
{
    public static SnakeGame Won()
    {
        var game = new SnakeGame(new SequenceRandom(2, 1, 0), 3, 2);
        game.HandleKey(ConsoleKey.UpArrow);
        game.Advance();
        game.HandleKey(ConsoleKey.LeftArrow);
        game.Advance();
        game.Advance();
        return game;
    }

    public static SnakeGame SelfCollision()
    {
        var game = new SnakeGame(new FixedRandom(253));
        for (int i = 0; i < 4; i++)
            game.Advance();
        foreach (var key in new[] { ConsoleKey.UpArrow, ConsoleKey.LeftArrow, ConsoleKey.DownArrow })
        {
            game.HandleKey(key);
            game.Advance();
        }
        return game;
    }
}

public sealed class SnakeGameTests
{
    [Fact]
    public void NewRoundHasCenteredThreeCellSnakeAndEmptyHistory()
    {
        var game = new SnakeGame();
        Assert.Equal(30, game.Width);
        Assert.Equal(16, game.Height);
        Assert.Equal(new[] { new Position(15, 8), new(14, 8), new(13, 8) }, game.Body);
        Assert.Equal(Direction.Right, game.Direction);
        Assert.Equal(RoundStatus.Running, game.Status);
        Assert.Equal(0, game.Score);
        Assert.DoesNotContain(game.Food!.Value, game.Body);
        Assert.Throws<InvalidOperationException>(() => game.Outcome);
    }

    [Theory]
    [InlineData(0, 16, "width")]
    [InlineData(2, 16, "width")]
    [InlineData(-1, 16, "width")]
    [InlineData(30, 0, "height")]
    [InlineData(30, 1, "height")]
    public void RejectsBoardsTooSmallForSnake(int width, int height, string parameter)
    {
        Assert.Equal(parameter, Assert.Throws<ArgumentOutOfRangeException>(
            () => new SnakeGame(width: width, height: height)).ParamName);
    }

    [Fact]
    public void BodyCannotBeModifiedByCaller()
    {
        var game = new SnakeGame();
        Assert.Throws<NotSupportedException>(() => ((IList<Position>)game.Body).Add(new(0, 0)));
    }

    [Fact]
    public void NormalMoveAdvancesHeadAndRemovesTailWithoutChangingScore()
    {
        var game = new SnakeGame(new SequenceRandom());
        Position? food = game.Food;
        game.Advance();
        Assert.Equal(new[] { new Position(16, 8), new(15, 8), new(14, 8) }, game.Body);
        Assert.Equal(food, game.Food);
        Assert.Equal(0, game.Score);
    }

    [Theory]
    [InlineData(ConsoleKey.UpArrow, 15, 7)]
    [InlineData(ConsoleKey.W, 15, 7)]
    [InlineData(ConsoleKey.DownArrow, 15, 9)]
    [InlineData(ConsoleKey.S, 15, 9)]
    [InlineData(ConsoleKey.LeftArrow, 14, 7)]
    [InlineData(ConsoleKey.A, 14, 7)]
    [InlineData(ConsoleKey.RightArrow, 16, 7)]
    [InlineData(ConsoleKey.D, 16, 7)]
    public void EveryArrowAndWasdKeySteers(ConsoleKey key, int x, int y)
    {
        var game = new SnakeGame(new SequenceRandom());
        if (key is ConsoleKey.LeftArrow or ConsoleKey.A or ConsoleKey.RightArrow or ConsoleKey.D)
        {
            game.HandleKey(ConsoleKey.UpArrow);
            game.Advance();
        }
        game.HandleKey(key);
        game.Advance();
        Assert.Equal(new Position(x, y), game.Body[0]);
        Assert.Equal(RoundStatus.Running, game.Status);
    }

    [Theory]
    [InlineData(ConsoleKey.RightArrow, ConsoleKey.LeftArrow, 1, 0)]
    [InlineData(ConsoleKey.UpArrow, ConsoleKey.DownArrow, 0, -1)]
    [InlineData(ConsoleKey.DownArrow, ConsoleKey.UpArrow, 0, 1)]
    [InlineData(ConsoleKey.LeftArrow, ConsoleKey.RightArrow, -1, 0)]
    public void ReversalIsRejectedInEveryDirection(ConsoleKey initial, ConsoleKey reverse, int dx, int dy)
    {
        var game = new SnakeGame(new SequenceRandom());
        if (initial == ConsoleKey.LeftArrow)
        {
            game.HandleKey(ConsoleKey.UpArrow);
            game.Advance();
        }
        game.HandleKey(initial);
        game.Advance();
        Position before = game.Body[0];
        game.HandleKey(reverse);
        game.Advance();
        Assert.Equal(new Position(before.X + dx, before.Y + dy), game.Body[0]);
    }

    [Fact]
    public void OnlyOneTurnPerTickIsAcceptedAndNextTickCanTurnAgain()
    {
        var game = new SnakeGame(new SequenceRandom());
        game.HandleKey(ConsoleKey.UpArrow);
        game.HandleKey(ConsoleKey.LeftArrow);
        game.Advance();
        Assert.Equal(new Position(15, 7), game.Body[0]);
        game.HandleKey(ConsoleKey.LeftArrow);
        game.Advance();
        Assert.Equal(new Position(14, 7), game.Body[0]);
    }

    [Theory]
    [InlineData(ConsoleKey.Spacebar)]
    [InlineData(ConsoleKey.R)]
    [InlineData(ConsoleKey.RightArrow)]
    [InlineData(ConsoleKey.LeftArrow)]
    public void IgnoredKeysDoNotConsumeTheAvailableTurn(ConsoleKey ignored)
    {
        var game = new SnakeGame(new SequenceRandom());
        game.HandleKey(ignored);
        game.HandleKey(ConsoleKey.UpArrow);
        game.Advance();
        Assert.Equal(new Position(15, 7), game.Body[0]);
    }

    [Theory]
    [InlineData(ConsoleKey.UpArrow, 15, 0)]
    [InlineData(ConsoleKey.DownArrow, 15, 15)]
    [InlineData(ConsoleKey.LeftArrow, 0, 7)]
    [InlineData(ConsoleKey.RightArrow, 29, 8)]
    public void EveryWallStopsRoundWithoutMovingOutsideBoard(ConsoleKey key, int x, int y)
    {
        var game = new SnakeGame(new SequenceRandom());
        if (key == ConsoleKey.LeftArrow)
        {
            game.HandleKey(ConsoleKey.UpArrow);
            game.Advance();
        }
        game.HandleKey(key);
        for (int tick = 0; tick < 40 && game.Status == RoundStatus.Running; tick++)
            game.Advance();
        Assert.Equal(RoundStatus.Collision, game.Status);
        Assert.Equal("collision", game.Outcome);
        Assert.Equal(new Position(x, y), game.Body[0]);
        var frozen = game.Body.ToArray();
        game.HandleKey(ConsoleKey.Q);
        game.Advance();
        Assert.Equal(frozen, game.Body);
        Assert.Equal(RoundStatus.Collision, game.Status);
    }

    [Fact]
    public void EachFruitGrowsExactlyOneCellAndAwardsTenPoints()
    {
        var game = new SnakeGame(new FixedRandom(253));
        for (int fruit = 1; fruit <= 4; fruit++)
        {
            Position target = game.Food!.Value;
            game.Advance();
            Assert.Equal(target, game.Body[0]);
            Assert.Equal(3 + fruit, game.Body.Count);
            Assert.Equal(10 * fruit, game.Score);
            Assert.DoesNotContain(game.Food!.Value, game.Body);
            Assert.Equal(RoundStatus.Running, game.Status);
        }
    }

    [Fact]
    public void SelfCollisionEndsRoundAndPreservesEarnedScore()
    {
        var game = Games.SelfCollision();
        Assert.Equal(RoundStatus.Collision, game.Status);
        Assert.Equal("collision", game.Outcome);
        Assert.Equal(7, game.Body.Count);
        Assert.Equal(40, game.Score);
        Assert.Equal(new Position(18, 7), game.Body[0]);
        game.Advance();
        Assert.Equal(new Position(18, 7), game.Body[0]);
    }

    [Fact]
    public void MovingIntoTheTailCellIsLegalWhenTailVacatesIt()
    {
        var game = new SnakeGame(new SequenceRandom(2, 0), 3, 2);
        game.HandleKey(ConsoleKey.UpArrow);
        game.Advance();
        game.HandleKey(ConsoleKey.LeftArrow);
        game.Advance();
        Position tail = game.Body[^1];
        game.HandleKey(ConsoleKey.DownArrow);
        game.Advance();
        Assert.Equal(tail, game.Body[0]);
        Assert.Equal(RoundStatus.Running, game.Status);
        Assert.Equal(4, game.Body.Distinct().Count());
        Assert.Equal(10, game.Score);
    }

    [Fact]
    public void FillingBoardWinsWithoutTryingToSpawnAnotherFruit()
    {
        var game = Games.Won();
        Assert.Equal(RoundStatus.Won, game.Status);
        Assert.Equal("won", game.Outcome);
        Assert.Equal(6, game.Body.Count);
        Assert.Equal(30, game.Score);
        Assert.Null(game.Food);
        game.HandleKey(ConsoleKey.Q);
        game.Advance();
        Assert.Equal(RoundStatus.Won, game.Status);
    }

    [Theory]
    [InlineData(ConsoleKey.Q)]
    [InlineData(ConsoleKey.Escape)]
    public void QuitEndsImmediatelyEvenWithAPendingTurn(ConsoleKey key)
    {
        var game = new SnakeGame(new SequenceRandom());
        var before = game.Body.ToArray();
        game.HandleKey(ConsoleKey.UpArrow);
        game.HandleKey(key);
        game.Advance();
        Assert.Equal(RoundStatus.Quit, game.Status);
        Assert.Equal("quit", game.Outcome);
        Assert.Equal(before, game.Body);
    }

    [Fact]
    public void SeedReproducesFoodPlacementAndFirstAndLastEmptyCellsAreEligible()
    {
        Assert.Equal(new Position(0, 0), new SnakeGame(new SequenceRandom()).Food);
        Assert.Equal(new Position(29, 15), new SnakeGame(new FixedRandom(476)).Food);
        Assert.Equal(new SnakeGame(new Random(2026)).Food, new SnakeGame(new Random(2026)).Food);
    }
}
