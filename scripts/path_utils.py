#!/usr/bin/env python

try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path


def find_project_root(start_file):
    """Walk upwards from a script file until the project assets directory is found."""
    current_dir = Path(start_file).resolve().parent

    while not (current_dir / "assets").exists() and current_dir.parent != current_dir:
        current_dir = current_dir.parent

    if not (current_dir / "assets").exists():
        raise RuntimeError("Could not locate the project root containing the 'assets' directory.")

    return current_dir


def list_relative_files(root_dir, pattern):
    """Return sorted relative file paths under root_dir that match the pattern."""
    root_dir = Path(root_dir)
    if not root_dir.exists():
        return []

    return sorted(
        path.relative_to(root_dir).as_posix()
        for path in root_dir.rglob(pattern)
        if path.is_file()
    )


def resolve_under(root_dir, user_path):
    """Resolve absolute or root-relative user input into a filesystem path."""
    candidate = Path(user_path)
    if candidate.is_absolute():
        return candidate

    return Path(root_dir) / candidate
