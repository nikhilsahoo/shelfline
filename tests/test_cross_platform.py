from pathlib import Path, PureWindowsPath

from shelfline.config import default_config_path
from shelfline.downloads import partial_download_path, safe_replace
from shelfline.tui.widgets import CoverDisplay


def test_default_config_path_windows_shape(tmp_path: Path) -> None:
    path = default_config_path(env={"APPDATA": str(tmp_path)}, platform_name="nt")
    assert path == tmp_path / "shelfline" / "config.json"


def test_default_config_path_linux_shape(tmp_path: Path) -> None:
    path = default_config_path(env={}, platform_name="posix", home=tmp_path / "home")
    assert path == tmp_path / "home" / ".config" / "shelfline" / "config.json"


def test_partial_download_path_stays_in_destination_directory() -> None:
    destination = PureWindowsPath("C:/Users/Ada/Books")
    partial = partial_download_path(destination, "Book.epub")
    assert partial == PureWindowsPath("C:/Users/Ada/Books/Book.epub.part")


def test_safe_replace_moves_file_to_final_path(tmp_path: Path) -> None:
    partial = tmp_path / "book.epub.part"
    final = tmp_path / "book.epub"
    partial.write_bytes(b"book")
    result = safe_replace(partial, final)
    assert final.read_bytes() == b"book"
    assert not partial.exists()
    assert result is None


def test_cover_display_falls_back_without_terminal_graphics(tmp_path: Path) -> None:
    missing_image = tmp_path / "missing.jpg"
    widget = CoverDisplay(title="Portable Book", authors=["Ada Writer"], image_path=missing_image)
    assert "Portable Book" in widget.renderable
