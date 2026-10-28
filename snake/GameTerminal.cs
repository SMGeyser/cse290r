using System.Diagnostics;

namespace Snake;

public interface IGameTerminal
{
    bool IsRedirected { get; }
    bool CursorVisible { get; set; }
    bool KeyAvailable { get; }
    ConsoleKey ReadKey();
    void Clear();
    void WriteFrame(string frame);
    void WriteLine(string text);
    void WriteError(string text);
}

public sealed class ConsoleTerminal : IGameTerminal
{
    public bool IsRedirected => Console.IsInputRedirected || Console.IsOutputRedirected;
    public bool CursorVisible
    {
        get => !OperatingSystem.IsWindows() || Console.CursorVisible;
        set => Console.CursorVisible = value;
    }
    public bool KeyAvailable => Console.KeyAvailable;
    public ConsoleKey ReadKey() => Console.ReadKey(intercept: true).Key;
    public void Clear() => Console.Clear();
    public void WriteFrame(string frame)
    {
        Console.SetCursorPosition(0, 0);
        Console.Write(frame);
    }
    public void WriteLine(string text) => Console.WriteLine(text);
    public void WriteError(string text) => Console.Error.WriteLine(text);
}

public interface IGameClock
{
    void StartTick();
    bool IsTickPending { get; }
    void WaitForInput();
}

public sealed class GameClock : IGameClock
{
    private readonly Stopwatch timer = new();
    public void StartTick() => timer.Restart();
    public bool IsTickPending => timer.ElapsedMilliseconds < 120;
    public void WaitForInput() => Thread.Sleep(5);
}
