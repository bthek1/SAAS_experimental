"""Agent instruction files stay wired up (#49).

Every AGENTS.md has a CLAUDE.md beside it that only imports it, since Claude Code
reads CLAUDE.md and other agents read AGENTS.md. The root AGENTS.md lists every
nested one.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


def _files(name: str) -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob(name)
        if not SKIP_DIRS.intersection(p.relative_to(REPO_ROOT).parts)
    )


def test_every_agents_md_has_a_claude_md_that_imports_it() -> None:
    for agents in _files("AGENTS.md"):
        claude = agents.with_name("CLAUDE.md")
        assert claude.is_file(), f"{claude.relative_to(REPO_ROOT)} is missing"
        rel = claude.relative_to(REPO_ROOT)
        assert claude.read_text().strip() == "@AGENTS.md", (
            f"{rel} must hold only '@AGENTS.md'; rules go in AGENTS.md"
        )


def test_every_claude_md_sits_beside_an_agents_md() -> None:
    for claude in _files("CLAUDE.md"):
        assert claude.with_name("AGENTS.md").is_file(), (
            f"{claude.relative_to(REPO_ROOT)} has no AGENTS.md beside it"
        )


def test_root_agents_md_lists_every_nested_file() -> None:
    root = (REPO_ROOT / "AGENTS.md").read_text()
    for agents in _files("AGENTS.md"):
        rel = agents.relative_to(REPO_ROOT).as_posix()
        if rel != "AGENTS.md":
            assert f"]({rel})" in root, f"root AGENTS.md does not link {rel}"
