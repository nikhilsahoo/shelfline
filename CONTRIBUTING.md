# Contributing to Shelfline

Thanks for helping make Shelfline better. This project is a Python/Textual TUI
for browsing OPDS 1.x catalogs, downloading books, managing a local library, and
reading EPUB text in the terminal.

## Setup

Use Python 3.11 or newer. From the repository root:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -v
python -m shelfline --help
```

On Linux or macOS shells, quote the editable install like this:

```shell
python -m pip install -e '.[dev]'
```

## Running the App

Run Shelfline with either command:

```powershell
shelfline
python -m shelfline
```

To test with a specific config file:

```powershell
python -m shelfline --config .\config.json
```

Use a disposable library directory and test OPDS catalog when exercising
download, delete, credential, or reader flows.

## Running Tests

Run the full test suite before submitting a change:

```powershell
python -m pytest -v
```

For focused work, run the smallest relevant tests first, then the full suite
when practical.

## Coding Style

- Keep changes small, readable, and focused on one behavior or documentation
  area.
- Prefer existing Shelfline patterns over new abstractions.
- Keep user-facing text clear and terminal-friendly.
- Avoid adding dependencies unless the benefit is clear and documented.
- Do not commit generated caches, local configs, downloaded books, or private
  catalog data.

## TUI and Design Expectations

Shelfline should feel fast, predictable, and usable in a terminal. Preserve
keyboard-first workflows, readable labels, stable layout, and useful status
messages. When changing Textual screens, check narrow and wide terminal sizes
and make sure errors remain visible long enough to act on.

## Documentation Expectations

Update `README.md` when commands, configuration, supported formats, or key
bindings change. Add focused docs for contributor-only details that would make
the README too long. Keep examples accurate to the current package name and
commands: `shelfline` and `python -m shelfline`.

## Good First Issue Ideas

- Improve README examples or add tested catalog setup notes.
- Add or polish screenshots.
- Improve empty states and recoverable error messages.
- Add focused tests around CLI, config, storage, or parser behavior.
- Clarify manual smoke-test steps for catalog, library, and reader flows.

## Branches, Commits, and Pull Requests

- Create a topic branch for your change.
- Use clear commit messages that describe the user-visible change.
- Keep pull requests focused; split unrelated work into separate PRs.
- Include the tests or manual checks you ran.
- Add screenshots or terminal recordings for visible TUI changes when helpful.
- Mention follow-up work separately instead of bundling it into an unrelated PR.
