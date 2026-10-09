"""Pipeline execution module for running declarative workflows."""

import logging
import os
import tempfile
from typing import Any

from typer.main import get_command

from ..common.errors import FileNotFoundError, PermissionError, ValidationError
from ..common.pipeline_parser import (
    PipelineSpec,
    validate_pipeline,
)

logger = logging.getLogger(__name__)

_ARG_ALIASES = {
    "input_file": ("input_file", "input", "fromfile", "from"),
    "input_files": ("input_files", "input", "inputs", "fromfile"),
    "output": ("output", "output_file", "tofile", "to"),
    "query": ("query", "sql", "query_expr"),
    "key_fields": ("key_fields", "keys", "key"),
    "filter_expr": ("filter_expr", "filter"),
}


def _pop_aliased(args: dict[str, Any], name: str) -> Any:
    """Pop a value for a Click parameter, accepting pipeline aliases."""
    if name in args:
        return args.pop(name)
    for alias in _ARG_ALIASES.get(name, ()):
        if alias in args:
            return args.pop(alias)
    return None


def _click_root():
    from ..core import app

    return get_command(app)


def _click_command(name: str):
    """The Click command for ``name``; ``"db load"`` names a group's subcommand."""
    root = _click_root()
    ctx = root.make_context("undatum", [], resilient_parsing=True)
    first, *rest = name.split()
    command = root.get_command(ctx, first)
    for part in rest:
        command = getattr(command, "commands", {}).get(part)
    return command


def build_pipeline_argv(command: str, args: dict[str, Any]) -> list[str]:
    """Build a Typer argv list from a pipeline step's command and args.

    Maps ``input``/``output`` aliases onto each command's positional arguments
    and options so ``convert`` gets ``undatum convert in.csv out.jsonl`` rather
    than invalid ``--input`` flags.
    """
    remaining = dict(args)
    cmd = _click_command(command)
    argv = command.split()
    if cmd is None:
        for key, value in remaining.items():
            if value is None:
                continue
            option = key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    argv.append(f"--{option}")
            else:
                argv.extend([f"--{option}", str(value)])
        return argv

    for param in cmd.params:
        kind = getattr(param, "param_type_name", None)
        if kind == "argument":
            value = _pop_aliased(remaining, param.name or "")
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                argv.extend(str(item) for item in value)
            else:
                argv.append(str(value))
            continue
        if kind != "option":
            continue
        value = _pop_aliased(remaining, param.name or "")
        if value is None:
            continue
        flags = [opt for opt in param.opts if opt.startswith("--")]
        flag = flags[0] if flags else (param.opts[0] if param.opts else f"--{param.name}")
        if isinstance(value, bool) or getattr(param, "is_flag", False):
            if value:
                argv.append(flag)
            else:
                no_flags = [
                    opt
                    for opt in (getattr(param, "secondary_opts", None) or [])
                    if str(opt).startswith("--")
                ]
                if no_flags:
                    argv.append(no_flags[0])
            continue
        if isinstance(value, (list, tuple)):
            if param.name and "field" in param.name:
                argv.extend([flag, ",".join(str(item) for item in value)])
            else:
                for item in value:
                    argv.extend([flag, str(item)])
            continue
        argv.extend([flag, str(value)])

    for key, value in remaining.items():
        if value is None:
            continue
        option = key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                argv.append(f"--{option}")
        elif isinstance(value, (list, tuple)):
            argv.extend([f"--{option}", ",".join(str(item) for item in value)])
        else:
            argv.extend([f"--{option}", str(value)])
    return argv


def _command_accepts_output(command: str) -> bool:
    cmd = _click_command(command)
    if cmd is None:
        return False
    return any(getattr(param, "name", None) in {"output", "output_file"} for param in cmd.params)


class PipelineRunner:
    """Pipeline execution engine."""

    def __init__(self, dry_run: bool = False):
        """Initialize pipeline runner.

        Args:
            dry_run: If True, validate only without executing
        """
        self.dry_run = dry_run
        self.working_dir = os.getcwd()
        self.temp_files = []
        self.step_outputs = {}  # Track outputs from each step
        self.last_output = None

    def run(self, spec: PipelineSpec, variables: dict[str, str] | None = None) -> bool:
        """Execute pipeline specification.

        Args:
            spec: PipelineSpec to execute
            variables: Optional variable overrides

        Returns:
            True if all steps succeeded, False otherwise
        """
        # Resolve variables
        resolved_spec = spec.resolve_variables(overrides=variables)

        # Validate pipeline
        validation_errors = validate_pipeline(resolved_spec)
        if validation_errors:
            logger.error("Pipeline validation failed:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            return False

        if self.dry_run:
            logger.info("Dry run mode: validation passed, skipping execution")
            return True

        # Execute steps
        try:
            for i, step in enumerate(resolved_spec.steps):
                step_name = step.get("name", f"step_{i + 1}")
                logger.info(f"Executing step {i + 1}/{len(resolved_spec.steps)}: {step_name}")

                success = self._execute_step(step, step_name)
                if not success:
                    logger.error(f"Step '{step_name}' failed")
                    return False

                logger.info(f"Step '{step_name}' completed successfully")

            logger.info("Pipeline execution completed successfully")
            return True

        finally:
            # Cleanup temporary files
            self._cleanup()

    def _execute_step(self, step: dict[str, Any], step_name: str) -> bool:
        """Execute a single pipeline step.

        Args:
            step: Step definition
            step_name: Step name for logging

        Returns:
            True if step succeeded, False otherwise
        """
        command = step.get("command")
        args = step.get("args", {})

        if command == "package":
            return self._execute_package_step(args, step_name)

        resolved_args = self._resolve_paths(args, step_name, command=command)
        try:
            return self._execute_via_cli(command, resolved_args)
        except FileNotFoundError as e:
            logger.error(f"Step '{step_name}' failed: {e}")
            return False
        except PermissionError as e:
            logger.error(f"Step '{step_name}' failed: {e}")
            return False
        except ValidationError as e:
            logger.error(f"Step '{step_name}' failed: {e}")
            return False
        except Exception as e:
            from ..common.errors import format_error_message

            error_msg = format_error_message(e, verbose=False)
            logger.error(f"Step '{step_name}' failed: {error_msg}")
            return False

    def _execute_package_step(self, args: dict[str, Any], step_name: str) -> bool:
        """Execute a package pipeline step via Packager."""
        from .packager import Packager

        resolved = dict(args)
        subcommand = resolved.pop("subcommand", "create")
        input_files = resolved.pop("input_files", None) or resolved.pop("input", None)
        if isinstance(input_files, str):
            input_files = [input_files]
        if not input_files:
            logger.error("Step '%s': package step requires 'input' or 'input_files'", step_name)
            return False

        packager = Packager()
        try:
            if subcommand == "create":
                packager.create(input_files, resolved)
            elif subcommand == "add-resource":
                package_file = resolved.pop("package_file", None) or resolved.pop("output", None)
                if not package_file:
                    logger.error(
                        "Step '%s': package add-resource requires 'package_file' or 'output'",
                        step_name,
                    )
                    return False
                packager.add_resource(package_file, input_files, resolved)
            elif subcommand == "validate":
                package_file = resolved.pop("package_file", None) or resolved.pop("output", None)
                if not package_file:
                    logger.error(
                        "Step '%s': package validate requires 'package_file' or 'output'",
                        step_name,
                    )
                    return False
                packager.validate(package_file, resolved)
            else:
                logger.error("Step '%s': unknown package subcommand '%s'", step_name, subcommand)
                return False
            return True
        except Exception as exc:
            from ..common.errors import format_error_message

            logger.error(
                "Step '%s' failed: %s", step_name, format_error_message(exc, verbose=False)
            )
            return False

    def _execute_via_cli(self, command: str, args: dict[str, Any]) -> bool:
        """Execute a command in-process through the Typer app.

        Args:
            command: Command name
            args: Command arguments

        Returns:
            True if command succeeded, False otherwise
        """
        from typer.testing import CliRunner

        from ..core import app

        argv = build_pipeline_argv(command, args)
        result = CliRunner().invoke(app, argv)
        if result.exit_code != 0:
            logger.error("Command failed: undatum %s", " ".join(argv))
            err = (result.stderr or "") + (result.stdout or "")
            if result.exception:
                from ..common.errors import format_error_message

                err = (err + "\n" + format_error_message(result.exception, verbose=False)).strip()
            if err:
                logger.error("Error output: %s", err)
            return False
        if result.stdout:
            logger.debug("Command output: %s", result.stdout)
        return True

    def _resolve_paths(
        self, args: dict[str, Any], step_name: str, command: str | None = None
    ) -> dict[str, Any]:
        """Resolve input/output paths, handling step dependencies.

        Args:
            args: Step arguments
            step_name: Step name
            command: Pipeline command name (used to decide whether to inject output)

        Returns:
            Resolved arguments with paths updated
        """
        resolved = dict(args)

        # Check for input path
        input_keys = ("input", "input_file", "fromfile", "from", "input_files", "inputs")
        found_input = False
        for input_key in input_keys:
            if input_key in resolved:
                found_input = True
                input_path = resolved[input_key]
                # Check if this references a previous step's output
                if (
                    isinstance(input_path, str)
                    and input_path.startswith("$")
                    and input_path[1:] in self.step_outputs
                ):
                    resolved[input_key] = self.step_outputs[input_path[1:]]
                break
        if not found_input and self.last_output:
            resolved["input"] = self.last_output

        # Check for output path
        output_path = None
        for output_key in ("output", "output_file", "tofile", "to"):
            if output_key in resolved:
                output_path = resolved[output_key]
                break

        if (
            not output_path
            and "output" not in resolved
            and command
            and _command_accepts_output(command)
        ):
            output_path = self._create_temp_file(step_name)
            resolved["output"] = output_path

        # Store output for next steps
        if output_path:
            self.step_outputs[step_name] = output_path
            self.last_output = output_path

        return resolved

    def _create_temp_file(self, step_name: str) -> str:
        """Create temporary file for step output.

        Args:
            step_name: Step name (for file naming)

        Returns:
            Temporary file path
        """
        temp_fd, temp_path = tempfile.mkstemp(suffix=".jsonl", prefix=f"{step_name}_")
        os.close(temp_fd)
        self.temp_files.append(temp_path)
        return temp_path

    def _cleanup(self):
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError as e:
                logger.warning(f"Failed to remove temporary file {temp_file}: {e}")
