"""Examples command for managing and executing recipe libraries."""

import logging
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


_CONDITIONAL = re.compile(r"\$\{(\w+):\+((?:[^{}]|\$\{\w+\})*)\}")
_PLACEHOLDER = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def build_recipe_argv(template: str, variables: dict[str, str]) -> list[str]:
    """Turn a recipe command template into an argument list without using a shell.

    The template is split into arguments *before* variables are substituted, so a
    value such as ``data.csv; rm -rf ~`` stays one literal argument. ``${var}`` and
    ``$var`` are replaced inside arguments, and ``${var:+text}`` keeps ``text`` only
    when ``var`` is set and non-empty (as in POSIX shells).

    Args:
        template: Command line from a recipe, e.g. ``undatum convert ${input} ${output}``.
        variables: Variable values.

    Returns:
        Argument list; a leading ``undatum`` runs the current interpreter's undatum.
    """

    def conditional(match: re.Match) -> str:
        return match.group(2) if variables.get(match.group(1)) else ""

    expanded = _CONDITIONAL.sub(conditional, template)

    def substitute(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return str(variables.get(name, match.group(0)))

    argv = [_PLACEHOLDER.sub(substitute, token) for token in shlex.split(expanded)]
    if argv and argv[0] == "undatum":
        argv = [sys.executable, "-m", "undatum", *argv[1:]]
    return argv


def _display_argv(argv: list[str]) -> str:
    shown = ["undatum", *argv[3:]] if argv[:3] == [sys.executable, "-m", "undatum"] else argv
    return shlex.join(shown)


class RecipeManager:
    """Manage and execute recipe libraries."""

    def __init__(self, recipes_dir: str | None = None):
        """Initialize recipe manager.

        Args:
            recipes_dir: Directory containing recipe files
                (default: recipes bundled with the undatum package)
        """
        if recipes_dir is None:
            # Recipes bundled with the installed package
            recipes_dir = Path(__file__).parent.parent / "recipes"
            self.recipes_dir = Path(recipes_dir)
        else:
            self.recipes_dir = Path(recipes_dir)
            self.recipes_dir.mkdir(parents=True, exist_ok=True)

    def list_recipes(
        self, category: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]:
        """List available recipes.

        Args:
            category: Filter by category
            tag: Filter by tag

        Returns:
            List of recipe metadata dictionaries
        """
        recipes = []

        if not self.recipes_dir.exists():
            return recipes

        for recipe_file in self.recipes_dir.glob("*.yml"):
            try:
                recipe = self._load_recipe(recipe_file)
                if recipe:
                    # Apply filters
                    if category and recipe.get("category") != category:
                        continue
                    if tag and tag not in recipe.get("tags", []):
                        continue
                    recipes.append(recipe)
            except Exception as e:
                logger.warning(f"Failed to load recipe {recipe_file}: {e}")

        # Sort by name
        recipes.sort(key=lambda x: x.get("name", ""))
        return recipes

    def get_recipe(self, name: str) -> dict[str, Any] | None:
        """Get a specific recipe by name.

        Args:
            name: Recipe name

        Returns:
            Recipe dictionary or None if not found
        """
        recipe_file = self.recipes_dir / f"{name}.yml"
        if not recipe_file.exists():
            return None

        return self._load_recipe(recipe_file)

    def _load_recipe(self, recipe_file: Path) -> dict[str, Any] | None:
        """Load a recipe from file.

        Args:
            recipe_file: Path to recipe file

        Returns:
            Recipe dictionary or None if invalid
        """
        from ..common.errors import FileNotFoundError, PermissionError, find_similar_files
        from ..common.path_utils import validate_file_path

        try:
            validate_file_path(str(recipe_file), check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(str(recipe_file))
            raise FileNotFoundError(str(recipe_file), suggestions) from e
        except PermissionError as e:
            raise PermissionError(str(recipe_file), operation="read") from e

        try:
            with open(recipe_file, encoding="utf-8") as f:
                recipe = yaml.safe_load(f)

            if not recipe:
                return None

            # Add name from filename if not present
            if "name" not in recipe:
                recipe["name"] = recipe_file.stem

            return recipe
        except Exception as e:
            logger.error(f"Failed to load recipe {recipe_file}: {e}")
            return None

    def show_recipe(self, name: str):
        """Display recipe details.

        Args:
            name: Recipe name
        """
        from ..common.errors import ValidationError

        recipe = self.get_recipe(name)
        if not recipe:
            available = [r["name"] for r in self.list_recipes()]
            suggestions = []
            if available:
                from ..common.errors import find_similar_field_names

                suggestions = find_similar_field_names(name, available)
            raise ValidationError(
                f"Recipe '{name}' not found", field="name", suggestions=suggestions
            )

        # Display recipe information
        console.print(f"\n[bold cyan]Recipe: {recipe.get('name', name)}[/bold cyan]")

        if "description" in recipe:
            console.print(f"\n[bold]Description:[/bold] {recipe['description']}")

        if "category" in recipe:
            console.print(f"[bold]Category:[/bold] {recipe['category']}")

        if "tags" in recipe:
            tags = ", ".join(recipe["tags"])
            console.print(f"[bold]Tags:[/bold] {tags}")

        # Display variables
        if "variables" in recipe:
            console.print("\n[bold]Variables:[/bold]")
            var_table = Table(show_header=True, header_style="bold")
            var_table.add_column("Variable")
            var_table.add_column("Description")
            var_table.add_column("Default")
            var_table.add_column("Required")

            for var_name, var_def in recipe["variables"].items():
                if isinstance(var_def, dict):
                    desc = var_def.get("description", "")
                    default = var_def.get("default", "")
                    required = "Yes" if var_def.get("required", False) else "No"
                else:
                    desc = ""
                    default = var_def if var_def else ""
                    required = "No"

                var_table.add_row(var_name, desc, str(default), required)

            console.print(var_table)

        # Display commands
        if "commands" in recipe:
            console.print("\n[bold]Commands:[/bold]")
            for i, cmd in enumerate(recipe["commands"], 1):
                if isinstance(cmd, dict):
                    cmd_text = cmd.get("command", "")
                    cmd_desc = cmd.get("description", "")
                else:
                    cmd_text = cmd
                    cmd_desc = ""

                console.print(f"\n[bold]{i}. {cmd_desc if cmd_desc else 'Command'}[/bold]")
                console.print(f"   [dim]{cmd_text}[/dim]")

        # Display example
        if "example" in recipe:
            console.print("\n[bold]Example:[/bold]")
            console.print(f"   [dim]{recipe['example']}[/dim]")

    def run_recipe(
        self,
        name: str,
        variables: dict[str, str] | None = None,
        dry_run: bool = False,
        interactive: bool = False,
    ):
        """Execute a recipe.

        Args:
            name: Recipe name
            variables: Variable values dictionary
            dry_run: If True, only show commands without executing
            interactive: If True, prompt for variable values
        """
        from ..common.errors import ValidationError

        recipe = self.get_recipe(name)
        if not recipe:
            available = [r["name"] for r in self.list_recipes()]
            suggestions = []
            if available:
                from ..common.errors import find_similar_field_names

                suggestions = find_similar_field_names(name, available)
            raise ValidationError(
                f"Recipe '{name}' not found", field="name", suggestions=suggestions
            )

        variables = variables or {}

        # Get variables from recipe
        recipe_vars = recipe.get("variables", {})

        # Interactive mode: prompt for variables
        if interactive:
            console.print(f"\n[bold]Recipe: {recipe.get('name', name)}[/bold]")
            if "description" in recipe:
                console.print(f"[dim]{recipe['description']}[/dim]\n")

            for var_name, var_def in recipe_vars.items():
                if var_name in variables:
                    continue  # Skip if already provided

                if isinstance(var_def, dict):
                    desc = var_def.get("description", "")
                    default = var_def.get("default", "")
                    required = var_def.get("required", False)
                else:
                    desc = ""
                    default = var_def if var_def else ""
                    required = False

                prompt = f"{var_name}"
                if desc:
                    prompt += f" ({desc})"
                if default:
                    prompt += f" [default: {default}]"
                if required:
                    prompt += " [required]"
                prompt += ": "

                value = input(prompt).strip()
                if not value and default:
                    value = default
                elif not value and required:
                    console.print(f"[red]Variable '{var_name}' is required[/red]")
                    sys.exit(1)

                if value:
                    variables[var_name] = value

        # Substitute variables in commands
        commands = recipe.get("commands", [])
        if not commands:
            console.print("[yellow]Recipe has no commands[/yellow]")
            return

        # Show preview
        console.print("\n[bold]Commands to execute:[/bold]")
        for i, cmd in enumerate(commands, 1):
            if isinstance(cmd, dict):
                cmd_text = cmd["command"]
                cmd_desc = cmd.get("description", "")
            else:
                cmd_text = cmd
                cmd_desc = ""

            # Substitute variables
            substituted_cmd = _display_argv(build_recipe_argv(cmd_text, variables))

            if cmd_desc:
                console.print(f"\n[bold]{i}. {cmd_desc}[/bold]")
            console.print(f"   [dim]{substituted_cmd}[/dim]")

        if dry_run:
            console.print("\n[yellow]Dry-run mode: commands not executed[/yellow]")
            return

        # Confirm execution
        if not interactive:
            try:
                response = input("\nExecute these commands? [y/N]: ").strip().lower()
                if response not in ("y", "yes"):
                    console.print("[yellow]Cancelled[/yellow]")
                    return
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Cancelled[/yellow]")
                return

        # Execute commands
        for i, cmd in enumerate(commands, 1):
            if isinstance(cmd, dict):
                cmd_text = cmd["command"]
            else:
                cmd_text = cmd

            # Build the argument list; no shell ever sees the substituted values.
            argv = build_recipe_argv(cmd_text, variables)

            console.print(f"\n[bold]Executing command {i}/{len(commands)}:[/bold]")
            console.print(f"[dim]{_display_argv(argv)}[/dim]")

            try:
                result = subprocess.run(argv, shell=False, check=False, capture_output=False)

                if result.returncode != 0:
                    console.print(f"[red]Command failed with exit code {result.returncode}[/red]")
                    sys.exit(1)
            except Exception as e:
                console.print(f"[red]Error executing command: {e}[/red]")
                sys.exit(1)

        console.print("\n[green]Recipe executed successfully[/green]")

    def _substitute_variables(self, text: str, variables: dict[str, str]) -> str:
        """Substitute variables in text.

        Args:
            text: Text with variable placeholders
            variables: Variable values dictionary

        Returns:
            Text with variables substituted
        """
        result = text
        for var_name, var_value in variables.items():
            # Replace ${var} and $var patterns
            result = result.replace(f"${{{var_name}}}", var_value)
            result = result.replace(f"${var_name}", var_value)

        return result
