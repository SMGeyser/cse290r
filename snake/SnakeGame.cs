namespace Snake;

public readonly record struct Position(int X, int Y);
public enum Direction { Up, Down, Left, Right }
public enum RoundStatus { Running, Collision, Won, Quit }

public sealed class SnakeGame
{
    private readonly Random random;
    private readonly List<Position> body;
    private Direction pendingDirection = Direction.Right;
    private bool turned;
    public int Width { get; }
    public int Height { get; }
    public IReadOnlyList<Position> Body { get; }
    public Position? Food { get; private set; }
    public Direction Direction { get; private set; } = Direction.Right;
    public RoundStatus Status { get; private set; }
    public int Score { get; private set; }
    public string Outcome => Status switch
    {
        RoundStatus.Collision => "collision",
        RoundStatus.Won => "won",
        RoundStatus.Quit => "quit",
        _ => throw new InvalidOperationException("The round has not ended.")
    };

    public SnakeGame(Random? random = null, int width = 30, int height = 16)
    {
        if (width < 3)
            throw new ArgumentOutOfRangeException(nameof(width));
        if (height < 2)
            throw new ArgumentOutOfRangeException(nameof(height));
        Width = width;
        Height = height;
        this.random = random ?? Random.Shared;
        int x = Math.Max(2, width / 2);
        int y = height / 2;
        body = [new(x, y), new(x - 1, y), new(x - 2, y)];
        Body = body.AsReadOnly();
        Food = SpawnFood();
    }

    public void HandleKey(ConsoleKey key)
    {
        if (Status != RoundStatus.Running)
            return;
        if (key is ConsoleKey.Escape or ConsoleKey.Q)
        {
            Status = RoundStatus.Quit;
            return;
        }
        Direction? requested = key switch
        {
            ConsoleKey.UpArrow or ConsoleKey.W => Direction.Up,
            ConsoleKey.DownArrow or ConsoleKey.S => Direction.Down,
            ConsoleKey.LeftArrow or ConsoleKey.A => Direction.Left,
            ConsoleKey.RightArrow or ConsoleKey.D => Direction.Right,
            _ => null
        };
        if (turned || requested is null || requested == Direction)
            return;
        Position current = Vector(Direction);
        Position next = Vector(requested.Value);
        if (next.X == -current.X && next.Y == -current.Y)
            return;
        pendingDirection = requested.Value;
        turned = true;
    }

    public void Advance()
    {
        if (Status != RoundStatus.Running)
            return;
        Direction = pendingDirection;
        turned = false;
        Position movement = Vector(Direction);
        Position head = new(body[0].X + movement.X, body[0].Y + movement.Y);
        bool eating = head == Food;
        // The tail vacates its cell on a move unless the snake is growing.
        int occupied = eating ? body.Count : body.Count - 1;
        if (head.X < 0 || head.X >= Width || head.Y < 0 || head.Y >= Height ||
            body.Take(occupied).Contains(head))
        {
            Status = RoundStatus.Collision;
            return;
        }
        body.Insert(0, head);
        if (eating)
        {
            Score += 10;
            if (body.Count == Width * Height)
            {
                Status = RoundStatus.Won;
                Food = null;
            }
            else
                Food = SpawnFood();
        }
        else
            body.RemoveAt(body.Count - 1);
    }

    private Position SpawnFood()
    {
        var empty = new List<Position>();
        for (int y = 0; y < Height; y++)
            for (int x = 0; x < Width; x++)
                if (!body.Contains(new(x, y)))
                    empty.Add(new(x, y));
        return empty[random.Next(empty.Count)];
    }

    private static Position Vector(Direction direction) => direction switch
    {
        Direction.Up => new(0, -1),
        Direction.Down => new(0, 1),
        Direction.Left => new(-1, 0),
        _ => new(1, 0)
    };
}
