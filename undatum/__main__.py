#!/usr/bin/env python
"""The main entry point. Invoke as `undatum' or `python -m undatum`.

This module provides the CLI entry point for the undatum package.
"""

import os
import sys

from .cli.common import configure_logging
from .common.errors import UndatumError, handle_command_error
from .common.stdio import OutputClosed
from .core import app

# Conventional exit status for SIGINT (128 + 2).
EXIT_INTERRUPTED = 130


def main():
    """Main entry point for the application.

    Handles the CLI invocation and graceful shutdown on keyboard interrupt.
    Also handles UndatumError exceptions for user-friendly error messages.
    """
    configure_logging(0)
    try:
        app()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(EXIT_INTERRUPTED)
    except (OutputClosed, BrokenPipeError):
        # The reader went away (e.g. `undatum head big.csv | head -1`): stop quietly.
        # Point stdout at devnull so the interpreter's final flush does not fail again.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    except UndatumError as e:
        exit_code = handle_command_error(e, verbose=False)
        sys.exit(exit_code)
    except Exception as e:
        # For other exceptions, try to format them nicely
        exit_code = handle_command_error(e, verbose=False)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
