using Snake;

return new SnakeApplication(new ConsoleTerminal(), new GameClock(), path => new ScoreStore(path)).Run(args);
