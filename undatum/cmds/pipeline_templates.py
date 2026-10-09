"""Pipeline template management module."""

import logging
import re
from pathlib import Path
from typing import Any

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

from ..common.errors import DependencyError, FileNotFoundError, PermissionError, find_similar_files
from ..common.path_utils import validate_file_path

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages pipeline templates."""

    def __init__(self):
        """Initialize template manager."""
        self.templates_dir = Path(__file__).parent.parent / "templates"

    def list_templates(self) -> list[dict[str, Any]]:
        """List all available templates.

        Returns:
            List of template metadata dictionaries
        """
        templates = []

        if not self.templates_dir.exists():
            return templates

        for template_file in self.templates_dir.glob("*.yml"):
            if template_file.name == "__init__.py":
                continue

            try:
                metadata = self._read_template_metadata(template_file)
                templates.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to read template {template_file.name}: {e}")

        return templates

    def get_template(self, name: str) -> Path | None:
        """Get template file path by name.

        Args:
            name: Template name

        Returns:
            Path to template file, or None if not found
        """
        template_path = self.templates_dir / f"{name}.yml"
        if template_path.exists():
            return template_path
        return None

    def _read_template_metadata(self, template_path: Path) -> dict[str, Any]:
        """Read metadata from template file.

        Args:
            template_path: Path to template file

        Returns:
            Template metadata dictionary
        """
        if not YAML_AVAILABLE:
            raise DependencyError(
                "pyyaml", feature="pipeline templates", install_command="pip install pyyaml"
            )

        try:
            validate_file_path(str(template_path), check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(str(template_path))
            raise FileNotFoundError(str(template_path), suggestions) from e
        except PermissionError as e:
            raise PermissionError(str(template_path), operation="read") from e

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        # Parse YAML
        yaml.safe_load(content)

        # Extract metadata from comments
        name = template_path.stem
        description = ""
        variables = []

        # Parse header comments
        lines = content.split("\n")
        for line in lines[:20]:  # Check first 20 lines
            if line.strip().startswith("# Template:"):
                description = line.split("Template:", 1)[1].strip()
            elif line.strip().startswith("# Description:"):
                description = line.split("Description:", 1)[1].strip()
            elif line.strip().startswith("# Variables:"):
                # Variables section starts
                continue
            elif line.strip().startswith("#") and ":" in line and line.strip().startswith("#   "):
                # Variable definition
                var_line = line.strip()[1:].strip()
                if ":" in var_line:
                    var_name = var_line.split(":", 1)[0].strip()
                    var_desc = var_line.split(":", 1)[1].strip()
                    variables.append(
                        {
                            "name": var_name,
                            "description": var_desc,
                            "required": "required" in var_desc.lower(),
                        }
                    )

        return {
            "name": name,
            "description": description,
            "variables": variables,
            "path": str(template_path),
        }

    def init_template(
        self,
        template_name: str,
        output_path: str,
        variables: dict[str, str] | None = None,
        interactive: bool = True,
    ) -> bool:
        """Initialize a template with variable substitution.

        Args:
            template_name: Name of template to initialize
            output_path: Path to output pipeline file
            variables: Optional variable values (if None and interactive=False, uses defaults)
            interactive: If True, prompt for missing variables

        Returns:
            True if successful, False otherwise
        """
        template_path = self.get_template(template_name)
        if not template_path:
            logger.error(f"Template '{template_name}' not found")
            return False

        try:
            # Read template
            with open(template_path, encoding="utf-8") as f:
                template_content = f.read()

            # Extract variables from template
            template_vars = self._extract_variables(template_content)

            # Collect variable values
            resolved_vars = variables or {}

            if interactive:
                # Prompt for missing variables
                for var_name, var_info in template_vars.items():
                    if var_name not in resolved_vars:
                        default = var_info.get("default", "")
                        prompt = f"{var_info.get('description', var_name)}"
                        if default:
                            prompt += f" (default: {default})"
                        prompt += ": "

                        try:
                            value = input(prompt).strip()
                            if not value and default:
                                value = default
                            if value:
                                resolved_vars[var_name] = value
                        except (EOFError, KeyboardInterrupt):
                            logger.info("\nCancelled")
                            return False

            # Substitute variables
            pipeline_content = self._substitute_template_vars(template_content, resolved_vars)

            # Write output
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(pipeline_content)

            logger.info(f"Pipeline initialized: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize template: {e}")
            return False

    def _extract_variables(self, template_content: str) -> dict[str, dict[str, str]]:
        """Extract variable definitions from template.

        Args:
            template_content: Template file content

        Returns:
            Dictionary mapping variable names to metadata
        """
        variables = {}

        # Parse variables section from comments
        lines = template_content.split("\n")
        in_variables = False

        for line in lines:
            if "# Variables:" in line:
                in_variables = True
                continue

            if in_variables and line.strip().startswith("#   "):
                var_line = line.strip()[1:].strip()
                if ":" in var_line:
                    var_name = var_line.split(":", 1)[0].strip()
                    var_desc = var_line.split(":", 1)[1].strip()

                    # Extract default value
                    default_match = re.search(r"default:\s*([^-\n]+)", var_desc)
                    default = default_match.group(1).strip() if default_match else ""

                    variables[var_name] = {
                        "description": var_desc,
                        "default": default,
                        "required": "required" in var_desc.lower() and not default,
                    }
            elif in_variables and line.strip() and not line.strip().startswith("#"):
                break

        return variables

    def _substitute_template_vars(self, content: str, variables: dict[str, str]) -> str:
        """Substitute variables in template content.

        Args:
            content: Template content
            variables: Variable values

        Returns:
            Content with variables substituted
        """

        # Replace ${var:-default} patterns
        def replace_var(match):
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                var_name = var_name.strip()
                default = default.strip()
                return variables.get(var_name, default)
            else:
                return variables.get(var_expr.strip(), match.group(0))

        pattern = r"\$\{([^}]+)\}"
        return re.sub(pattern, replace_var, content)
