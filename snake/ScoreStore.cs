using System.Globalization;
using Microsoft.Data.Sqlite;

namespace Snake;

public sealed record ScoreSummary(long Attempts, int BestScore);

public interface IScoreStore
{
    ScoreSummary GetSummary();
    ScoreSummary RecordAttempt(int score, string outcome);
}

public sealed class ScoreStore : IScoreStore
{
    private readonly string connectionString;

    public ScoreStore(string databasePath)
    {
        string fullPath = Path.GetFullPath(databasePath);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = fullPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false
        }.ToString();

        using var connection = OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            CREATE TABLE IF NOT EXISTS Attempts (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Score INTEGER NOT NULL CHECK (Score >= 0),
                Outcome TEXT NOT NULL CHECK (Outcome IN ('collision', 'won', 'quit')),
                FinishedAt TEXT NOT NULL
            );
            """;
        command.ExecuteNonQuery();
    }

    public ScoreSummary GetSummary()
    {
        using var connection = OpenConnection();
        return ReadSummary(connection);
    }

    public ScoreSummary RecordAttempt(int score, string outcome)
    {
        using var connection = OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO Attempts (Score, Outcome, FinishedAt)
            VALUES ($score, $outcome, $finishedAt);
            """;
        command.Parameters.AddWithValue("$score", score);
        command.Parameters.AddWithValue("$outcome", outcome);
        command.Parameters.AddWithValue("$finishedAt", DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture));
        command.ExecuteNonQuery();
        return ReadSummary(connection);
    }

    private SqliteConnection OpenConnection()
    {
        var connection = new SqliteConnection(connectionString);
        try
        {
            connection.Open();
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    private static ScoreSummary ReadSummary(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT COUNT(*), COALESCE(MAX(Score), 0) FROM Attempts;";
        using var reader = command.ExecuteReader();
        reader.Read();
        return new ScoreSummary(reader.GetInt64(0), reader.GetInt32(1));
    }
}
