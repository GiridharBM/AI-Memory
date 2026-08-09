import os
from pathlib import Path

CWD = os.getcwd()
HOME = Path.home()


def greet(name):
    """Greet someone by name."""
    return f"Hello, {name}"


class Greeter:
    """A friendly greeter."""

    def __init__(self, prefix="Hello"):
        self.prefix = prefix

    def greet(self, name):
        return f"{self.prefix}, {name}"
