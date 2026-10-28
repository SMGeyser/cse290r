using Microsoft.Data.Sqlite;

namespace Snake;

public sealed class SnakeApplication(
    IGameTerminal terminal, IGameClock clock, Func<string, IScoreStore> createStore,
    Func<Random, SnakeGame>? createGame = null)
{
    public int Run(string[] args)
    {
        GameOptions options;
        try
        {
            options = GameOptions.Parse(args);
        }
        catch (ArgumentException)
        {
            terminal.WriteError(GameOptions.Usage);
            return 1;
        }
        if (terminal.IsRedirected)
        {
            terminal.WriteLine("Run Snake in an interactive terminal: dotnet run --project snake");
            return 0;
        }
        bool cursorVisible = terminal.CursorVisible;
        try
        {
            IScoreStore store = createStore(options.DatabasePath);
            ScoreSummary history = store.GetSummary();
            Random random = options.Seed.HasValue ? new Random(options.Seed.Value) : Random.Shared;
            terminal.CursorVisible = false;
            bool playAgain;
            do
            {
                SnakeGame game = createGame is null ? new SnakeGame(random) : createGame(random);
                terminal.Clear();
                terminal.WriteFrame(BoardRenderer.Render(game, history));
                while (game.Status == RoundStatus.Running)
                {
                    clock.StartTick();
                    while (clock.IsTickPending && game.Status == RoundStatus.Running)
                    {
                        while (terminal.KeyAvailable)
                        {
                            game.HandleKey(terminal.ReadKey());
                            if (game.Status == RoundStatus.Quit)
                                break;
                        }
                        clock.WaitForInput();
                    }
                    game.Advance();
                    if (game.Status is RoundStatus.Running or RoundStatus.Won)
                        terminal.WriteFrame(BoardRenderer.Render(game, history));
                }
                history = store.RecordAttempt(game.Score, game.Outcome);
                terminal.WriteLine(BoardRenderer.Result(game, history));
                if (game.Status == RoundStatus.Quit)
                    return 0;
                while (terminal.KeyAvailable)
                    terminal.ReadKey();
                playAgain = terminal.ReadKey() == ConsoleKey.R;
            } while (playAgain);
        }
        catch (Exception error) when (error is SqliteException or IOException or UnauthorizedAccessException)
        {
            terminal.WriteError($"Could not read or save score history: {error.Message}");
            return 1;
        }
        finally
        {
            terminal.CursorVisible = cursorVisible;
            terminal.WriteLine("");
        }
        return 0;
    }
}
