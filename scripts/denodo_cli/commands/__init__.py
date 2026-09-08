"""Command implementations. Each returns ``(document, exit_code)``; ``cli.py`` prints."""

EXIT_OK = 0
EXIT_EXECUTION = 1   # the server (or the network) refused
EXIT_USAGE = 2       # configuration, arguments, or a refused destructive operation
EXIT_ENVIRONMENT = 3 # used by the launcher only: dependencies could not be set up
