# SPDX-License-Identifier: Apache-2.0
"""
Host tooling consistency checks for the #146 developer environment.

Two properties are checked here that no other host check can see:

* every tool pinned in ``[dependency-groups].dev`` matches the revision of its own repository in
  ``.pre-commit-config.yaml``; and
* the runtime harnesses in ``scripts/`` import only the standard library and sibling runtime
  modules.

The pre-commit scanner is deliberately narrow. It understands the block-style ``repos:`` list this
repository uses, not YAML in general: flow-style mappings, anchors, and other constructs raise
instead of being guessed at, and comments are removed with a small quote-aware scanner so the check
needs no third-party parser. Each revision is associated with the repository that declares it and
compared as a complete string, so swapped repositories, a longer version that shares a prefix, and a
revision that appears only in a comment all fail.

The import audit is static. It follows ``import`` and ``from ... import`` statements, so a dynamic
import such as ``importlib.import_module("numpy")`` is invisible to it.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

RUNTIME_SCRIPTS: Final = (
    Path("scripts/battery_protocol.py"),
    Path("scripts/battery_report.py"),
    Path("scripts/device_layer.py"),
    Path("scripts/device_qualification.py"),
    Path("scripts/device_smoke.py"),
)

HOOK_REPOSITORIES: Final = {
    "ruff": "https://github.com/astral-sh/ruff-pre-commit",
    "ty": "https://github.com/astral-sh/ty-pre-commit",
    "codespell": "https://github.com/codespell-project/codespell",
}

_DEV_PIN: Final = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[A-Za-z0-9_.+-]+)$")
_REPO_ITEM: Final = re.compile(r"^(?P<indent> *)- repo:(?P<value>.*)$")
_MAPPING_KEY: Final = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_-]+):(?P<value>.*)$")


def _skip_quoted(line: str, start: int) -> int:
    """Return the index just past the quoted scalar that begins at ``start``."""
    quote = line[start]
    index = start + 1
    while index < len(line):
        character = line[index]
        if quote == '"' and character == "\\":
            index += 2
            continue
        if character == quote:
            if quote == "'" and index + 1 < len(line) and line[index + 1] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return index


def _strip_comment(line: str) -> str:
    """
    Remove a YAML comment from one line, respecting quoted scalars.

    A ``#`` starts a comment only at column 0 or after whitespace. A ``#`` inside a single- or
    double-quoted scalar is preserved. This is a scanner for the shapes this repository writes, not
    a YAML parser.
    """
    index = 0
    while index < len(line):
        character = line[index]
        if character in {'"', "'"}:
            index = _skip_quoted(line, index)
            continue
        if character == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index].rstrip()
        index += 1
    return line.rstrip()


def _unquote(value: str) -> str:
    """Strip surrounding single or double quotes from a scalar value."""
    value = value.strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in {'"', "'"}:
        inner = value[1:-1]
        if value[0] == "'":
            return inner.replace("''", "'")
        return inner
    return value


def _format_error(line_number: int, detail: str) -> ValueError:
    """Build a parser error that names the offending configuration line."""
    return ValueError(f".pre-commit-config.yaml line {line_number}: {detail}")


@dataclass
class _RepoState:
    """Scanner state for one pass over the ``repos:`` block."""

    entries: list[tuple[str, str | None]] = field(default_factory=list)
    item_indent: int | None = None
    current_repo: str | None = None
    current_rev: str | None = None

    def finish(self) -> None:
        """Record the open repository entry, except the legitimate ``local`` form."""
        if self.current_repo is None:
            return
        if self.current_repo != "local":
            self.entries.append((self.current_repo, self.current_rev))
        self.current_repo = None
        self.current_rev = None


def _enter_top_level(content: str, line_number: int) -> bool:
    """Handle a column-0 line and report whether the ``repos:`` block is now open."""
    key, separator, value = content.partition(":")
    if not separator or not key.strip():
        raise _format_error(line_number, f"unsupported content {content!r}")
    key = key.strip()
    if key == "rev":
        raise _format_error(line_number, "rev before any repo")
    if key != "repos":
        return False
    if value.strip():
        raise _format_error(line_number, "flow-style repos are not supported")
    return True


def _consume_repo_item(match: re.Match[str], line_number: int, state: _RepoState) -> None:
    """Start a repository entry from a ``- repo:`` list item."""
    indent = len(match.group("indent"))
    if state.item_indent is None:
        state.item_indent = indent
    elif indent != state.item_indent:
        raise _format_error(line_number, "inconsistent repo indentation")
    state.finish()
    repository = _unquote(match.group("value"))
    if not repository:
        raise _format_error(line_number, "empty repo value")
    state.current_repo = repository


def _consume_key(match: re.Match[str], line_number: int, state: _RepoState) -> None:
    """Attach a sibling ``rev:`` to the open repository and ignore other keys."""
    key_indent = len(match.group("indent"))
    if state.item_indent is not None and key_indent < state.item_indent:
        raise _format_error(line_number, "key outside any repo entry")
    key = match.group("key")
    if key != "rev":
        return
    attach_indent = None if state.item_indent is None else state.item_indent + 2
    if key_indent != attach_indent:
        if state.current_repo is None:
            raise _format_error(line_number, "rev before any repo")
        return
    if state.current_repo is None:
        raise _format_error(line_number, "rev before any repo")
    if state.current_rev is not None:
        raise _format_error(line_number, "duplicate rev for the same repository")
    value = _unquote(match.group("value"))
    if not value:
        raise _format_error(line_number, "empty rev value")
    state.current_rev = value


def _consume_repos_line(line: str, line_number: int, state: _RepoState) -> None:
    """Consume one indented line inside the ``repos:`` block."""
    indent = len(line) - len(line.lstrip(" "))
    repo_match = _REPO_ITEM.match(line)
    if repo_match is not None:
        _consume_repo_item(repo_match, line_number, state)
        return
    if line.strip().startswith("-"):
        if state.item_indent is not None and indent > state.item_indent:
            return
        raise _format_error(line_number, f"unsupported list item {line.strip()!r}")
    key_match = _MAPPING_KEY.match(line)
    if key_match is None:
        raise _format_error(line_number, f"unsupported content {line.strip()!r}")
    _consume_key(key_match, line_number, state)


def _revision_entries(text: str) -> list[tuple[str, str | None]]:
    """Return ``(repository, revision)`` pairs from a block-style ``repos:`` list."""
    state = _RepoState()
    repos_started = False
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        leading = line[: len(line) - len(line.lstrip())]
        if "\t" in leading:
            raise _format_error(line_number, "tab indentation is not supported")
        indent = len(leading)
        if indent == 0:
            state.finish()
            repos_started = _enter_top_level(line.strip(), line_number)
            continue
        if not repos_started:
            raise _format_error(line_number, "indented content outside the repos block")
        _consume_repos_line(line, line_number, state)
    state.finish()
    return state.entries


def parse_pre_commit_revisions(text: str) -> dict[str, str]:
    """
    Parse repository revisions from the repository's ``.pre-commit-config.yaml``.

    The result maps each repository URL to its revision. A ``local`` repository is skipped because
    it legitimately has no revision. Duplicate repositories, duplicate revisions, a revision before
    any repository, and a repository without a revision are rejected with ``ValueError``; so are
    formats this narrow scanner does not understand.
    """
    revisions: dict[str, str] = {}
    owners: dict[str, str] = {}
    for repository, revision in _revision_entries(text):
        if repository in revisions:
            message = f".pre-commit-config.yaml lists repository {repository!r} more than once"
            raise ValueError(message)
        if revision is None:
            message = f".pre-commit-config.yaml repository {repository!r} has no rev"
            raise ValueError(message)
        if revision in owners:
            message = f".pre-commit-config.yaml uses rev {revision!r} for both {owners[revision]!r} and {repository!r}"
            raise ValueError(message)
        revisions[repository] = revision
        owners[revision] = repository
    if not revisions:
        message = ".pre-commit-config.yaml declares no repository revisions"
        raise ValueError(message)
    return revisions


def _dev_pins(pyproject_text: str) -> tuple[dict[str, str], list[str]]:
    """Return the exact ``[dependency-groups].dev`` pins and any configuration problems."""
    try:
        document = tomllib.loads(pyproject_text)
    except ValueError as error:
        return {}, [f"pyproject.toml is not valid TOML: {error}"]
    groups = document.get("dependency-groups")
    if not isinstance(groups, dict):
        return {}, ["pyproject.toml has no [dependency-groups] table"]
    dev = groups.get("dev")
    if not isinstance(dev, list):
        return {}, ["pyproject.toml has no [dependency-groups].dev list"]
    pins: dict[str, str] = {}
    problems: list[str] = []
    for requirement in dev:
        if not isinstance(requirement, str):
            problems.append(f"dev dependency {requirement!r} is not a string")
            continue
        match = _DEV_PIN.match(requirement)
        if match is None:
            problems.append(f"dev dependency {requirement!r} is not an exact name==version pin")
            continue
        pins[match.group("name")] = match.group("version")
    return pins, problems


def _compare_pins(pins: dict[str, str], revisions: dict[str, str]) -> list[str]:
    """Compare each known tool pin with the revision of that tool's own repository."""
    problems: list[str] = []
    for tool, repository in HOOK_REPOSITORIES.items():
        if tool not in pins:
            problems.append(f"pyproject.toml has no {tool} pin in [dependency-groups].dev")
            continue
        if repository not in revisions:
            problems.append(f".pre-commit-config.yaml has no {repository!r} repository")
            continue
        expected = f"v{pins[tool]}"
        if revisions[repository] != expected:
            problems.append(
                f".pre-commit-config.yaml revision {revisions[repository]!r} for "
                f"{repository!r} does not match the {tool} pin {expected!r}"
            )
    return problems


def check_pin_parity(pyproject_text: str, pre_commit_text: str) -> list[str]:
    """Return every mismatch between development pins and pre-commit hook revisions."""
    pins, problems = _dev_pins(pyproject_text)
    try:
        revisions = parse_pre_commit_revisions(pre_commit_text)
    except ValueError as error:
        problems.append(f"invalid .pre-commit-config.yaml: {error}")
        return problems
    problems.extend(_compare_pins(pins, revisions))
    return problems


def check_runtime_imports(paths: Sequence[Path]) -> list[str]:
    """Return every non-stdlib import in the runtime harnesses under ``paths``."""
    problems: list[str] = []
    allowed = set(sys.stdlib_module_names) | {path.stem for path in paths}
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as error:
            problems.append(f"cannot parse runtime harness {path}: {error}")
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".", 1)[0]]
            problems.extend(
                f"Non-stdlib import {top!r} in runtime harness {path}" for top in names if top not in allowed
            )
    return problems


def main() -> None:
    """Run every host tooling check, exiting non-zero with all problems joined by newlines."""
    try:
        pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")
        pre_commit_text = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    except OSError as error:
        message = f"cannot read host tooling configuration: {error}"
        raise SystemExit(message) from error
    problems = check_pin_parity(pyproject_text, pre_commit_text)
    problems.extend(check_runtime_imports(RUNTIME_SCRIPTS))
    if problems:
        raise SystemExit("\n".join(problems))


if __name__ == "__main__":
    main()
