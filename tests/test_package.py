from pathlib import Path
import tomllib

from shelfline import __version__


def test_package_has_version() -> None:
    assert __version__ == "0.2.0"


def test_textual_css_is_included_as_package_data() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert pyproject["project"]["name"] == "shelfline"
    assert pyproject["project"]["scripts"] == {
        "shelfline": "shelfline.__main__:main",
    }
    assert "tui/*.tcss" in package_data["shelfline"]


def test_textual_image_support_is_optional() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert not any(dependency.startswith("textual-image") for dependency in dependencies)
    assert "textual-image>=0.8" in optional_dependencies["images"]
