"""Every `undatum ...` example in the docs uses commands and options that exist."""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_spec_commands", ROOT / "scripts" / "check_spec_commands.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_examples_match_cli():
    checker = _checker()
    files = sorted((ROOT / "docs" / "docs").rglob("*.md")) + [ROOT / "README.md"]
    problems = [p for p in checker.check(files) if "deprecated" not in p]
    assert problems == []


def test_docs_use_canonical_option_names():
    checker = _checker()
    files = sorted((ROOT / "docs" / "docs").rglob("*.md")) + [ROOT / "README.md"]
    # The page of a deprecated command, the migration guide and the migrate-script page
    # may show old names; everything else uses canonical names.
    allowed = (
        "commands/ingest.md",
        "commands/migrate-script.md",
        "getting-started/migrating-to-2.md",
    )
    deprecated = [
        p for p in checker.check(files) if "deprecated" in p and not any(a in p for a in allowed)
    ]
    assert deprecated == []


def _reference_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_cli_reference", ROOT / "scripts" / "generate_cli_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_command_reference_is_current():
    """Command pages match the CLI; run scripts/generate_cli_reference.py after CLI changes."""
    generator = _reference_generator()
    stale = []
    for path, block in generator.render_pages().items():
        current = path.read_text(encoding="utf8") if path.exists() else ""
        if generator.apply_block(current, block).rstrip("\n") != current.rstrip("\n"):
            stale.append(path.name)
    assert stale == []


def test_generated_rule_reference_is_current():
    """The rule reference page matches the catalogue; run scripts/generate_rule_reference.py."""
    spec = importlib.util.spec_from_file_location(
        "generate_rule_reference", ROOT / "scripts" / "generate_rule_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0


def test_generated_sdk_reference_is_current():
    """The SDK reference page matches the docstrings; run scripts/generate_sdk_reference.py."""
    spec = importlib.util.spec_from_file_location(
        "generate_sdk_reference", ROOT / "scripts" / "generate_sdk_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.render_page() == module.PAGE.read_text(encoding="utf8")
