using System.Globalization;
using Microsoft.Data.Sqlite;
using Snake;

namespace SnakeTests;

public sealed class ScoreStoreTests : IDisposable
{
    private readonly string root = Path.Combine(AppContext.BaseDirectory, "test-data", Guid.NewGuid().ToString("N"));
    private string Database => Path.Combine(root, "nested folder", "scores;history.db");

    [Fact]
    public void CreatesParentFoldersAndValidEmptySQLiteFile()
    {
        var store = new ScoreStore(Database);
        Assert.True(File.Exists(Database));
        Assert.Equal(new ScoreSummary(0, 0), store.GetSummary());
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA integrity_check";
        Assert.Equal("ok", command.ExecuteScalar());
    }

    [Theory]
    [InlineData("collision")]
    [InlineData("won")]
    [InlineData("quit")]
    public void SavesEachOutcomeScoreAndUtcTimestamp(string outcome)
    {
        var store = new ScoreStore(Database);
        DateTimeOffset before = DateTimeOffset.UtcNow;
        Assert.Equal(new ScoreSummary(1, 20), store.RecordAttempt(20, outcome));
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Id, Score, Outcome, FinishedAt FROM Attempts";
        using var reader = command.ExecuteReader();
        Assert.True(reader.Read());
        Assert.Equal(1, reader.GetInt64(0));
        Assert.Equal(20, reader.GetInt32(1));
        Assert.Equal(outcome, reader.GetString(2));
        var timestamp = DateTimeOffset.Parse(reader.GetString(3), CultureInfo.InvariantCulture);
        Assert.Equal(TimeSpan.Zero, timestamp.Offset);
        Assert.InRange(timestamp, before, DateTimeOffset.UtcNow);
        Assert.False(reader.Read());
    }

    [Fact]
    public void ReopeningPreservesEveryAttemptIncludingZeroDuplicateAndMaximumScore()
    {
        var store = new ScoreStore(Database);
        store.RecordAttempt(0, "quit");
        store.RecordAttempt(10, "collision");
        store.RecordAttempt(10, "collision");
        store.RecordAttempt(int.MaxValue, "won");
        var reopened = new ScoreStore(Database);
        Assert.Equal(new ScoreSummary(4, int.MaxValue), reopened.GetSummary());
        Assert.Equal(new ScoreSummary(5, int.MaxValue), reopened.RecordAttempt(0, "quit"));
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Id, Score FROM Attempts ORDER BY Id";
        using var reader = command.ExecuteReader();
        var scores = new List<int>();
        while (reader.Read())
        {
            Assert.Equal(scores.Count + 1, reader.GetInt64(0));
            scores.Add(reader.GetInt32(1));
        }
        Assert.Equal([0, 10, 10, int.MaxValue, 0], scores);
    }

    [Theory]
    [InlineData(-1, "quit")]
    [InlineData(int.MinValue, "collision")]
    [InlineData(10, "")]
    [InlineData(10, "unknown")]
    [InlineData(10, "quit'); DROP TABLE Attempts;--")]
    public void InvalidRecordsFailAtomicallyWithoutDamagingHistory(int score, string outcome)
    {
        var store = new ScoreStore(Database);
        store.RecordAttempt(40, "collision");
        Assert.Equal(19, Assert.Throws<SqliteException>(() => store.RecordAttempt(score, outcome)).SqliteErrorCode);
        Assert.Equal(new ScoreSummary(1, 40), store.GetSummary());
        Assert.Equal(new ScoreSummary(2, 40), store.RecordAttempt(0, "quit"));
    }

    [Fact]
    public void CannotUseDirectoryAsDatabaseAndFailedConnectionIsDisposed()
    {
        var store = new ScoreStore(Database);
        File.Delete(Database);
        Directory.CreateDirectory(Database);
        Assert.Throws<SqliteException>(() => store.GetSummary());
        Assert.Throws<SqliteException>(() => store.RecordAttempt(0, "quit"));
        Directory.Delete(Database);
        Assert.Equal(new ScoreSummary(0, 0), new ScoreStore(Database).GetSummary());
    }

    [Fact]
    public void CorruptDatabaseFailsWithoutOverwritingFile()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Database)!);
        File.WriteAllText(Database, "This is not SQLite");
        Assert.Throws<SqliteException>(() => new ScoreStore(Database));
        Assert.Equal("This is not SQLite", File.ReadAllText(Database));
    }

    [Fact]
    public void ParentFileCannotBeUsedAsDirectory()
    {
        Directory.CreateDirectory(root);
        string parentFile = Path.Combine(root, "blocked");
        File.WriteAllText(parentFile, "keep");
        Assert.Throws<IOException>(() => new ScoreStore(Path.Combine(parentFile, "scores.db")));
        Assert.Equal("keep", File.ReadAllText(parentFile));
    }

    private SqliteConnection Open()
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = Database, Pooling = false
        }.ToString());
        connection.Open();
        return connection;
    }

    public void Dispose()
    {
        string allowedRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "test-data")) + Path.DirectorySeparatorChar;
        string target = Path.GetFullPath(root);
        if (!target.StartsWith(allowedRoot, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Cleanup must stay inside test-data.");
        if (Directory.Exists(target))
            Directory.Delete(target, recursive: true);
    }
}
