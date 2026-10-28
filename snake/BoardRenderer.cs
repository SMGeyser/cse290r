using System.Text;

namespace Snake;

public static class BoardRenderer
{
    public static string Render(SnakeGame game, ScoreSummary history)
    {
        var frame = new StringBuilder();
        frame.AppendLine($"SNAKE | Score: {game.Score} | Attempts: {history.Attempts} | Best: {history.BestScore}".PadRight(68));
        frame.AppendLine("Arrows / WASD: move | Esc / Q: quit");
        frame.AppendLine(new string('#', game.Width + 2));
        for (int y = 0; y < game.Height; y++)
        {
            frame.Append('#');
            for (int x = 0; x < game.Width; x++)
            {
                Position cell = new(x, y);
                frame.Append(cell == game.Body[0] ? '@' : game.Body.Contains(cell) ? 'o' : cell == game.Food ? '*' : ' ');
            }
            frame.AppendLine("#");
        }
        frame.AppendLine(new string('#', game.Width + 2));
        return frame.ToString();
    }

    public static string Result(SnakeGame game, ScoreSummary history)
    {
        string message = game.Status == RoundStatus.Quit ? "Game ended." :
            game.Status == RoundStatus.Won ? "You filled the board! You win!" : "Game over!";
        string prompt = game.Status == RoundStatus.Quit ? "" : " Press R to restart, or any other key to quit.";
        return $"{message}{Environment.NewLine}Final score: {game.Score}.{prompt}{Environment.NewLine}" +
            $"Score saved | Attempts: {history.Attempts} | Best: {history.BestScore}";
    }
}
