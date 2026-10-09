"""AI-assisted commands backed by iterabledata's ``iterable.ai`` stack.

These commands expose capabilities provided by the iterabledata foundation that
undatum did not surface before: block-based dataset documentation with metadata
enrichment and PII-safe sampling, natural-language to filter translation,
conversion planning, and transform suggestion. Provider support (OpenAI,
Anthropic, Gemini, Azure, OpenRouter, Ollama, LM Studio, Perplexity) comes from
iterabledata directly.

Provider/model/credentials default to undatum's existing AI configuration
(``undatum.yaml`` / ``~/.undatum/config.yaml`` / environment) and can be
overridden per-invocation with CLI options.
"""

import json
import logging
from typing import Annotated

import typer
from rich.console import Console

from .common import console, enable_verbose

logger = logging.getLogger(__name__)

_stderr_console = Console(stderr=True)


def _ai_doc_progress_callback(event) -> None:
    """Print iterabledata documentation stages to stderr."""
    stage = event.stage.value if hasattr(event.stage, "value") else str(event.stage)
    detail = f" {event.detail}" if event.detail else ""
    _stderr_console.print(f"[dim]{stage} {event.progress}%{detail}[/dim]")


ai_app = typer.Typer(help="AI-assisted documentation, filtering, planning, and suggestions.")


def _source_iterableargs(
    table: str | None = None,
    start_page: int = 0,
    trust: bool = False,
    on_error: str | None = None,
    error_log: str | None = None,
    quotechar: str | None = None,
) -> dict:
    from ..common.command_utils import get_iterable_options

    options: dict = {}
    if table:
        options["table"] = table
    if start_page:
        options["start_page"] = start_page
    if trust:
        options["trust"] = True
    if on_error:
        options["on_error"] = on_error
    if error_log:
        options["error_log"] = error_log
    if quotechar:
        options["quotechar"] = quotechar
    return get_iterable_options(options)


# iterabledata DEFAULT_BLOCKS plus codebook (not in the engine default set).
DEFAULT_DOC_BLOCKS = [
    "general",
    "schema",
    "quality",
    "examples",
    "statistics",
    "agent_skill",
    "codebook",
]


def _resolve_ai(
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
) -> dict:
    """Merge CLI AI options with undatum's configured defaults.

    CLI values take precedence over config-file/environment values.
    """
    from ..ai.config import get_ai_config

    cfg = get_ai_config()
    resolved_provider = provider or cfg.get("provider") or "openai"
    resolved_model = model or cfg.get("model")
    resolved_api_key = api_key or cfg.get("api_key")
    # Provider-specific base URLs from undatum config.
    if base_url:
        resolved_base_url = base_url
    elif resolved_provider == "ollama":
        resolved_base_url = cfg.get("ollama_base_url") or cfg.get("base_url")
    elif resolved_provider == "lmstudio":
        resolved_base_url = cfg.get("lmstudio_base_url") or cfg.get("base_url")
    else:
        resolved_base_url = cfg.get("base_url")
    return {
        "provider": resolved_provider,
        "model": resolved_model,
        "api_key": resolved_api_key,
        "base_url": resolved_base_url,
    }


@ai_app.command()
def doc(
    filename: Annotated[str, typer.Argument(help="Input data file or source to document.")],
    output: Annotated[
        str, typer.Option(help="Output file path. Prints to stdout if not given.")
    ] = None,
    output_format: Annotated[
        str, typer.Option("--format", help="Output format: markdown, json, yaml, html, text.")
    ] = "markdown",
    blocks: Annotated[
        str,
        typer.Option(help="Comma-separated documentation blocks (e.g. 'general,schema,quality')."),
    ] = None,
    language: Annotated[str, typer.Option(help="Language for generated content.")] = "English",
    pii_detect: Annotated[
        bool, typer.Option(help="Detect PII fields (requires metacrafter).")
    ] = False,
    pii_mask_samples: Annotated[
        bool,
        typer.Option(
            "--pii-mask-samples",
            help="Mask detected PII in sample rows sent to the LLM.",
        ),
    ] = False,
    semantic_types: Annotated[
        bool, typer.Option(help="Detect semantic types (requires metacrafter).")
    ] = False,
    tables: Annotated[
        str | None,
        typer.Option(
            "--tables",
            help="Comma-separated table/sheet names for multi-table sources.",
        ),
    ] = None,
    cache: Annotated[
        bool,
        typer.Option("--cache", help="Cache generated documentation by content hash."),
    ] = False,
    include_field_descriptions: Annotated[
        bool,
        typer.Option(
            "--include-field-descriptions",
            help="Generate per-field descriptions (non-block generate path).",
        ),
    ] = False,
    validate_output: Annotated[
        bool,
        typer.Option(
            "--validate-output",
            help="Validate JSON documentation against Pydantic models.",
        ),
    ] = False,
    context: Annotated[
        str | None,
        typer.Option(
            "--context",
            help='JSON object of extra prompt context, e.g. \'{"title": "Sales"}\'.',
        ),
    ] = None,
    progress: Annotated[
        bool,
        typer.Option(
            "--progress",
            help="Print documentation generation stages to stderr.",
        ),
    ] = False,
    sample_size: Annotated[
        int | None,
        typer.Option(
            "--sample-size",
            help="Override sample row count for documentation (engine default if omitted).",
        ),
    ] = None,
    detect_constraints: Annotated[
        bool,
        typer.Option(
            "--detect-constraints/--no-detect-constraints",
            help="Detect min/max/length/enum constraints during schema inference (block path).",
        ),
    ] = True,
    include_statistics: Annotated[
        bool,
        typer.Option(
            "--statistics/--no-statistics",
            help="Compute statistics used by statistics/quality/codebook blocks.",
        ),
    ] = True,
    temperature: Annotated[
        float | None,
        typer.Option(
            "--temperature",
            help="LLM sampling temperature (engine default if omitted).",
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            help="Maximum tokens per LLM documentation block (engine default if omitted).",
        ),
    ] = None,
    job_id: Annotated[
        str | None,
        typer.Option(
            "--job-id",
            help="Stable job identifier for documentation progress and JSON results.",
        ),
    ] = None,
    provider: Annotated[str, typer.Option(help="LLM provider override.")] = None,
    model: Annotated[str, typer.Option(help="Model name override.")] = None,
    api_key: Annotated[str, typer.Option(help="API key override.")] = None,
    base_url: Annotated[str, typer.Option(help="Base URL override (local providers).")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Generate AI dataset documentation using iterabledata's block-based engine.

    Supports metadata enrichment (keywords, geographic/temporal coverage,
    language, themes), PII-safe sampling, and many providers (OpenAI, Anthropic,
    Gemini, Azure, OpenRouter, Ollama, LM Studio, Perplexity).

    Examples:
        undatum ai doc data.csv
        undatum ai doc data.parquet --format json --blocks general,schema,quality
        undatum ai doc data.csv --provider anthropic --model claude-3-5-sonnet-latest
        undatum ai doc workbook.xlsx --tables Sheet2 --pii-mask-samples --cache
        undatum ai doc data.csv --progress
        undatum ai doc data.csv --sample-size 20 --no-detect-constraints
        undatum ai doc data.csv --temperature 0.2 --max-tokens 2048
        undatum ai doc data.csv --job-id run-42 --progress

    Default blocks: general, schema, quality, examples, statistics, agent_skill, codebook.
    """
    if verbose:
        enable_verbose()

    from iterable.ai import doc as ai_doc

    from ..ai.doc_enrichment import (
        enrich_blocks_result,
        prepare_doc_source,
        restore_source_filename,
    )

    resolved = _resolve_ai(provider, model, api_key, base_url)
    block_list = (
        [b.strip() for b in blocks.split(",") if b.strip()] if blocks else list(DEFAULT_DOC_BLOCKS)
    )
    table_list = [part.strip() for part in tables.split(",") if part.strip()] if tables else None
    context_obj = None
    if context:
        from ..common.errors import ValidationError

        try:
            parsed = json.loads(context)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"Could not parse --context as JSON: {exc}",
                field="context",
            ) from exc
        if not isinstance(parsed, dict):
            raise ValidationError("--context must be a JSON object.", field="context")
        context_obj = parsed

    progress_cb = _ai_doc_progress_callback if progress else None
    llm_overrides = {}
    if temperature is not None:
        llm_overrides["temperature"] = temperature
    if max_tokens is not None:
        llm_overrides["max_tokens"] = max_tokens
    if job_id is not None:
        llm_overrides["job_id"] = job_id

    doc_path, cleanup, field_hints, field_names = prepare_doc_source(filename)
    try:
        if block_list and "schema" in block_list:
            result = ai_doc.generate_blocks(
                doc_path,
                blocks=block_list,
                provider=resolved["provider"],
                model=resolved["model"],
                api_key=resolved["api_key"],
                base_url=resolved["base_url"],
                language=language,
                pii_detect=pii_detect,
                semantic_types=semantic_types,
                tables=table_list,
                context=context_obj,
                progress=progress_cb,
                sample_size=sample_size,
                detect_constraints=detect_constraints,
                include_statistics=include_statistics,
                **llm_overrides,
            )
            restore_source_filename(result, filename, doc_path)
            enrich_blocks_result(
                result,
                field_hints,
                known_names=field_names,
                requested_blocks=block_list,
            )
            if output_format != "json":
                result = result["full_document_markdown"]
        else:
            generate_kwargs = {
                "provider": resolved["provider"],
                "model": resolved["model"],
                "api_key": resolved["api_key"],
                "base_url": resolved["base_url"],
                "format": output_format,
                "language": language,
                "pii_detect": pii_detect,
                "semantic_types": semantic_types,
                "pii_mask_samples": pii_mask_samples,
                "cache": cache,
                "blocks": block_list,
                "tables": table_list,
                "include_field_descriptions": include_field_descriptions,
                "validate_output": validate_output,
                "context": context_obj,
                "progress": progress_cb,
                "include_statistics": include_statistics,
            }
            if sample_size is not None:
                generate_kwargs["sample_size"] = sample_size
            generate_kwargs.update(llm_overrides)
            result = ai_doc.generate(doc_path, **generate_kwargs)
    finally:
        cleanup()

    if isinstance(result, (dict, list)):
        text = json.dumps(result, indent=2, default=str)
    else:
        text = str(result)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        console.print(f"[green]Documentation written to {output}[/green]")
    else:
        print(text)


@ai_app.command(name="filter")
def ai_filter(
    expression: Annotated[
        str, typer.Argument(help="Natural-language or DSL filter (e.g. 'rows where age > 30').")
    ],
    filename: Annotated[
        str, typer.Argument(help="Optional data file (used for schema context and --apply).")
    ] = None,
    apply: Annotated[
        bool, typer.Option(help="Apply the translated filter and output matching rows as JSONL.")
    ] = False,
    output: Annotated[str, typer.Option(help="Output file for --apply (default stdout).")] = None,
    provider: Annotated[str, typer.Option(help="LLM provider override.")] = None,
    model: Annotated[str, typer.Option(help="Model name override.")] = None,
    api_key: Annotated[str, typer.Option(help="API key override.")] = None,
    base_url: Annotated[str, typer.Option(help="Base URL override (local providers).")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    table: Annotated[
        str | None,
        typer.Option(
            "--table",
            "--sheet",
            help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
        ),
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: Annotated[
        bool,
        typer.Option(
            "--trust",
            help="Acknowledge pickle deserialization risk when reading pickle sources.",
        ),
    ] = False,
    on_error: Annotated[
        str | None,
        typer.Option(
            "--on-error",
            help="Parse-error policy: raise (default), skip, or warn.",
        ),
    ] = None,
    error_log: Annotated[
        str | None,
        typer.Option(
            "--error-log",
            help="Append parse errors as JSONL (use with --on-error skip or warn).",
        ),
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
    sample_size: Annotated[
        int | None,
        typer.Option(
            "--sample-size",
            help="Rows to sample when inferring schema context for a file (engine default 10000).",
        ),
    ] = None,
    flatten_nested: Annotated[
        bool,
        typer.Option(
            "--flatten-nested",
            help="Unfold nested dict / array-of-dict fields into dotted paths for schema context and --apply.",
        ),
    ] = False,
    max_nested_depth: Annotated[
        int | None,
        typer.Option(
            "--max-nested-depth",
            help="With --flatten-nested, maximum nest depth to unfold (engine default 5).",
        ),
    ] = None,
    keep_nested_parents: Annotated[
        bool,
        typer.Option(
            "--keep-nested-parents/--no-keep-nested-parents",
            help="With --flatten-nested, keep parent dict/array fields alongside dotted children.",
        ),
    ] = True,
):
    """Translate natural language (or simple DSL) into a filter expression.

    Simple DSL (e.g. ``age > 30``) is parsed without an LLM; natural language
    requires a configured provider. With ``--apply`` and a file, the filter is
    executed and matching rows are written as JSONL.

    Examples:
        undatum ai filter "status == 'active'"
        undatum ai filter "rows where amount over 1000" data.csv --provider openai
        undatum ai filter "age > 30" data.csv --apply --output adults.jsonl
        undatum ai filter "age > 30" data.csv --sample-size 500
        undatum ai filter "lat > 40" nested.jsonl --flatten-nested --apply
        undatum ai filter "lat > 40" nested.jsonl --flatten-nested --max-nested-depth 2 --no-keep-nested-parents
    """
    if verbose:
        enable_verbose()

    from iterable.ai import filter as ai_flt

    schema = None
    if filename:
        try:
            from iterable.ops import schema as schema_ops

            from ..common.s3_iterable import open_path

            iterableargs = _source_iterableargs(
                table, start_page, trust, on_error, error_log, quotechar
            )
            infer_kwargs = {"detect_constraints": False}
            if sample_size is not None:
                infer_kwargs["sample_size"] = sample_size
            if flatten_nested:
                infer_kwargs["flatten_nested"] = True
                infer_kwargs["keep_nested_parents"] = keep_nested_parents
                if max_nested_depth is not None:
                    infer_kwargs["max_nested_depth"] = max_nested_depth
            if iterableargs:
                source = open_path(filename, mode="r", iterableargs=iterableargs)
                try:
                    schema = schema_ops.infer(source, **infer_kwargs)
                finally:
                    if hasattr(source, "close"):
                        source.close()
            else:
                schema = schema_ops.infer(filename, **infer_kwargs)
        except Exception as e:  # noqa: BLE001
            logger.debug("Schema inference failed for %s: %s", filename, e)

    resolved = _resolve_ai(provider, model, api_key, base_url)
    result = ai_flt.translate_filter(
        expression,
        schema,
        provider=resolved["provider"] if (provider or expression) else None,
        model=resolved["model"],
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
    )

    if not apply:
        console.print_json(json.dumps(result, default=str))
        return

    if not filename:
        console.print("[red]--apply requires a data file argument[/red]")
        raise typer.Exit(code=1)

    from ..common.s3_iterable import open_path

    ast = result["ast"]
    out_file = open(output, "w", encoding="utf-8") if output else None
    try:
        import sys

        sink = out_file or sys.stdout
        source = open_path(
            filename,
            mode="r",
            iterableargs=_source_iterableargs(
                table, start_page, trust, on_error, error_log, quotechar
            ),
        )
        try:
            count = 0
            rows = source
            if flatten_nested:
                from ..common.command_utils import iter_projected_rows

                rows = iter_projected_rows(
                    source,
                    True,
                    keep_parents=keep_nested_parents,
                    max_depth=max_nested_depth,
                )
            for row in ai_flt.apply_ast(rows, ast):
                sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                count += 1
        finally:
            if hasattr(source, "close"):
                source.close()
        logger.info("Filtered %d rows", count)
    finally:
        if out_file:
            out_file.close()


@ai_app.command()
def plan(
    source: Annotated[str, typer.Argument(help="Source file/path.")],
    target: Annotated[str, typer.Argument(help="Target file/path.")],
    use_llm: Annotated[
        bool, typer.Option(help="Use LLM reasoning in addition to catalog metadata.")
    ] = False,
    provider: Annotated[str, typer.Option(help="LLM provider override.")] = None,
    model: Annotated[str, typer.Option(help="Model name override.")] = None,
    api_key: Annotated[str, typer.Option(help="API key override.")] = None,
    base_url: Annotated[str, typer.Option(help="Base URL override (local providers).")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Produce a declarative conversion plan between two formats (no conversion).

    Examples:
        undatum ai plan data.csv data.parquet
        undatum ai plan data.json data.geojson --use-llm
    """
    if verbose:
        enable_verbose()

    from iterable.ai import plan as ai_plan

    resolved = _resolve_ai(provider, model, api_key, base_url)
    result = ai_plan.plan_conversion(
        source,
        target,
        use_llm=use_llm,
        provider=resolved["provider"],
        model=resolved["model"],
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
    )
    console.print_json(json.dumps(result, default=str))


@ai_app.command()
def suggest(
    filename: Annotated[str, typer.Argument(help="Input data file.")],
    goal: Annotated[
        str, typer.Argument(help="Natural-language description of the desired result.")
    ],
    provider: Annotated[str, typer.Option(help="LLM provider override.")] = None,
    model: Annotated[str, typer.Option(help="Model name override.")] = None,
    api_key: Annotated[str, typer.Option(help="API key override.")] = None,
    base_url: Annotated[str, typer.Option(help="Base URL override (local providers).")] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply the suggested spec and write transformed rows."),
    ] = False,
    output: Annotated[
        str, typer.Option(help="Output file for --apply (JSONL; default stdout).")
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Do not prompt before applying the transform."),
    ] = False,
    sample_size: Annotated[
        int | None,
        typer.Option(
            "--sample-size",
            help="Override sample row count sent to the suggestion engine (default 5).",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    table: Annotated[
        str | None,
        typer.Option(
            "--table",
            "--sheet",
            help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
        ),
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: Annotated[
        bool,
        typer.Option(
            "--trust",
            help="Acknowledge pickle deserialization risk when reading pickle sources.",
        ),
    ] = False,
    on_error: Annotated[
        str | None,
        typer.Option(
            "--on-error",
            help="Parse-error policy: raise (default), skip, or warn.",
        ),
    ] = None,
    error_log: Annotated[
        str | None,
        typer.Option(
            "--error-log",
            help="Append parse errors as JSONL (use with --on-error skip or warn).",
        ),
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
):
    """Suggest a declarative transform spec for a dataset and goal.

    With ``--apply``, runs ``iterable.ops.transform.apply_spec`` and writes JSONL.
    Prompts for confirmation unless ``--yes`` is passed.

    Examples:
        undatum ai suggest data.csv "drop empty columns and rename id to user_id"
        undatum ai suggest data.csv "rename id to user_id" --apply --yes --output out.jsonl
        undatum ai suggest data.csv "normalize phone numbers" --sample-size 20
    """
    if verbose:
        enable_verbose()

    from iterable.ai import suggest as ai_suggest

    resolved = _resolve_ai(provider, model, api_key, base_url)
    iterableargs = _source_iterableargs(table, start_page, trust, on_error, error_log, quotechar)
    suggest_source = filename
    opened = None
    if iterableargs:
        from ..common.s3_iterable import open_path

        opened = open_path(filename, mode="r", iterableargs=iterableargs)
        suggest_source = opened
    try:
        result = ai_suggest.suggest_transform(
            suggest_source,
            goal,
            provider=resolved["provider"],
            model=resolved["model"],
            api_key=resolved["api_key"],
            base_url=resolved["base_url"],
            **({"sample_size": sample_size} if sample_size is not None else {}),
        )
    finally:
        if opened is not None and hasattr(opened, "close"):
            opened.close()
    if not apply:
        console.print_json(json.dumps(result, default=str))
        return

    if not yes:
        target = output or "stdout"
        if not typer.confirm(f"Apply transform spec and write to {target}?"):
            raise typer.Exit()

    from iterable.ops.transform import apply_spec

    from ..common.s3_iterable import open_path

    out_file = open(output, "w", encoding="utf-8") if output else None
    try:
        import sys

        sink = out_file or sys.stdout
        source = open_path(
            filename,
            mode="r",
            iterableargs=_source_iterableargs(
                table, start_page, trust, on_error, error_log, quotechar
            ),
        )
        try:
            count = 0
            for row in apply_spec(source, result):
                sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                count += 1
        finally:
            if hasattr(source, "close"):
                source.close()
        logger.info("Applied transform spec to %d rows", count)
        if output:
            console.print(f"[green]Wrote {count} rows to {output}[/green]")
    finally:
        if out_file:
            out_file.close()
