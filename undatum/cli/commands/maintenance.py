"""Commands that maintain scripts calling undatum."""

from typing import Annotated

import typer

from ._app import data_app


@data_app.command("migrate-script")
def migrate_script(
    paths: Annotated[
        list[str],
        typer.Argument(help="Scripts, pipeline YAML, Makefiles or directories to scan."),
    ],
    write: Annotated[
        bool, typer.Option("--write", help="Rewrite the files in place (default: show a diff).")
    ] = False,
    check: Annotated[
        bool,
        typer.Option("--check", help="Exit with 1 when a file needs changes or review (for CI)."),
    ] = False,
):
    """Rewrite deprecated undatum commands and options to their canonical names.

    Scans scripts, Makefiles, CI files, Markdown and pipeline YAML for undatum calls.

    Old spellings (--filetype, --outtype, --n, --engine iterable, profile, scheme) become current.

    Without --write it prints a diff; places that need a person are listed on stderr.

    Text marked with a migrate-script: ignore comment (# or <!-- -->) is left alone.

    Examples:
        undatum migrate-script scripts/ pipelines/
        undatum migrate-script etl.sh --write
        undatum migrate-script . --check
    """
    from ...cmds.migrate import migrate_files, write_migration

    migrations = migrate_files(paths)
    changed = [m for m in migrations if m.changed]
    findings = [f for m in migrations for f in m.findings]
    for migration in changed:
        if write:
            write_migration(migration)
        else:
            typer.echo(migration.diff(), nl=False)
    for finding in findings:
        typer.echo(f"{finding.path}:{finding.line}: {finding.message}", err=True)
    action = "rewrote" if write else "would rewrite"
    typer.echo(
        f"{action} {len(changed)} of {len(migrations)} files; {len(findings)} places need review",
        err=True,
    )
    if check and (changed or findings):
        raise typer.Exit(1)
