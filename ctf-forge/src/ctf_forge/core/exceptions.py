"""User-facing application errors."""


class ForgeError(Exception):
    """A predictable failure safe to explain to the CLI user."""


class TaskNotFound(ForgeError):
    """No task exists with the supplied identifier."""
