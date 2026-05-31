from pathlib import Path
import tomllib

from epub_tui import __version__


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"


def test_textual_css_is_included_as_package_data() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert "tui/*.tcss" in package_data["epub_tui"]
