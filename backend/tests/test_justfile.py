"""The justfile finds the .NET SDK where README's no-sudo install puts it (#48).

`instances` is .NET (#42 to #45). With the SDK in `~/.dotnet` and off `PATH`, `just dev`
once failed with `dotnet: not found`. These run `just` itself, with a throwaway `HOME`,
so they check what recipes see, not the justfile's text. They skip without `just`.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = REPO_ROOT / "justfile"

pytestmark = pytest.mark.skipif(shutil.which("just") is None, reason="needs just")


def recipe_path(home: Path, path: str) -> list[str]:
    """`PATH` as a recipe sees it, for this `HOME` and shell `PATH`."""
    result = subprocess.run(  # noqa: S603 - fixed argv
        ["just", "--justfile", str(JUSTFILE), "--evaluate", "PATH"],  # noqa: S607
        env={**os.environ, "HOME": str(home), "PATH": path},
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split(":")


def shell_path() -> str:
    # `just` itself must stay reachable; drop any real ~/.dotnet from the test's PATH.
    return ":".join(p for p in os.environ["PATH"].split(":") if ".dotnet" not in p)


def test_recipes_find_the_sdk_in_home_dotnet(tmp_path: Path) -> None:
    (tmp_path / ".dotnet").mkdir()
    path = shell_path()
    assert recipe_path(tmp_path, path) == [str(tmp_path / ".dotnet"), *path.split(":")]


def test_path_is_untouched_without_home_dotnet(tmp_path: Path) -> None:
    # An apt-installed SDK is already on PATH: nothing is added in front of it.
    path = shell_path()
    assert recipe_path(tmp_path, path) == path.split(":")


def test_every_dotnet_command_runs_in_a_recipe() -> None:
    # That PATH reaches recipe bodies only, so each dotnet call must be in one.
    lines = JUSTFILE.read_text().splitlines()
    calls = [line for line in lines if re.search(r"\bdotnet (run|watch|test)\b", line)]
    assert calls, "expected the instances recipes to call dotnet"
    for line in calls:
        assert line.startswith((" ", "\t")), f"dotnet outside a recipe body: {line!r}"
