namespace Snake;

public sealed record GameOptions(int? Seed, string DatabasePath)
{
    public const string Usage = "Usage: Snake [--seed <integer>] [--database <path>]";
    public static GameOptions Parse(string[] args)
    {
        int? seed = null;
        string database = Path.Combine(AppContext.BaseDirectory, "scores.db");
        for (int index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length)
                throw new ArgumentException(Usage);
            if (args[index] == "--seed" && int.TryParse(args[index + 1], out int value))
                seed = value;
            else if (args[index] == "--database" && !string.IsNullOrWhiteSpace(args[index + 1]))
                database = args[index + 1];
            else
                throw new ArgumentException(Usage);
        }
        return new GameOptions(seed, database);
    }
}
