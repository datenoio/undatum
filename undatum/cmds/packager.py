"""Frictionless Data Package generation command module."""

import json
import logging
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from typing import Any

from rich.console import Console

from ..ai import get_ai_service, get_fields_info, get_structured_metadata
from ..common.errors import FileNotFoundError, ValidationError, find_similar_files
from ..common.path_utils import validate_file_path
from ..common.schema_utils import field_to_frictionless_schema
from ..constants import EU_DATA_THEMES
from ..utils import get_option
from .analyzer import OBJECTS_ANALYZE_LIMIT, analyze
from .doc import (
    _build_sample_csv,
    _build_samples,
    _build_title,
    _detect_languages,
    _extract_geographic_coverage,
    _extract_keywords,
    _extract_temporal_coverage,
    _get_primary_fields,
    _guess_data_theme,
    _merge_ai_metadata,
)

logger = logging.getLogger(__name__)
console = Console()

DATA_THEME_URI_BY_LABEL = {theme["label"]: theme["uri"] for theme in EU_DATA_THEMES}

FRICTIONLESS_PROFILE = "tabular-data-package"

FORMAT_MEDIATYPE: dict[str, tuple[str, str]] = {
    "csv": ("csv", "text/csv"),
    "tsv": ("tsv", "text/tab-separated-values"),
    "json": ("json", "application/json"),
    "jsonl": ("jsonl", "application/x-ndjson"),
    "ndjson": ("jsonl", "application/x-ndjson"),
    "parquet": ("parquet", "application/parquet"),
    "xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "xls": ("xls", "application/vnd.ms-excel"),
    "xml": ("xml", "application/xml"),
    "yaml": ("yaml", "application/x-yaml"),
    "yml": ("yaml", "application/x-yaml"),
    "avro": ("avro", "application/avro"),
    "orc": ("orc", "application/orc"),
    "bson": ("bson", "application/bson"),
}


def _is_url(path: str) -> bool:
    parsed = urllib.parse.urlparse(path)
    return parsed.scheme in {"http", "https"}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "dataset"


def _parse_kv_entries(value: str | None, default_key: str) -> list[dict[str, str]]:
    if not value:
        return []
    entries = []
    for raw_item in value.split(";"):
        raw_item = raw_item.strip()
        if not raw_item:
            continue
        if "=" not in raw_item:
            entries.append({default_key: raw_item})
            continue
        entry: dict[str, str] = {}
        for part in raw_item.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                continue
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key and val:
                entry[key] = val
        if not entry:
            entry[default_key] = raw_item
        entries.append(entry)
    return entries


def _normalize_keywords(value: str | None) -> list[str] | None:
    if not value:
        return None
    keywords = [kw.strip() for kw in value.split(",") if kw.strip()]
    return keywords or None


def _download_to_temp(url: str) -> str:
    suffix = os.path.splitext(urllib.parse.urlparse(url).path)[-1]
    handle, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(handle)
    urllib.request.urlretrieve(url, temp_path)
    return temp_path


def _guess_format_mediatype(file_path: str, file_type: str | None) -> tuple[str | None, str | None]:
    if file_type and file_type in FORMAT_MEDIATYPE:
        return FORMAT_MEDIATYPE[file_type]
    ext = os.path.splitext(file_path.rsplit("?", 1)[0])[-1].lower().lstrip(".")
    return FORMAT_MEDIATYPE.get(ext, (ext or None, None))


def _resource_path(
    input_path: str,
    output_file: str,
    package_dir: str | None,
) -> str:
    if _is_url(input_path):
        return input_path
    if package_dir:
        return os.path.basename(input_path)
    output_dir = os.path.dirname(os.path.abspath(output_file)) or os.getcwd()
    input_abs = os.path.abspath(input_path)
    try:
        rel_path = os.path.relpath(input_abs, output_dir)
        if rel_path.startswith(".."):
            return os.path.basename(input_path)
        return rel_path
    except ValueError:
        return os.path.basename(input_path)


def _build_resource_schema(
    table,
    field_descriptions: dict[str, str] | None = None,
) -> dict[str, Any]:
    fields = []
    for field in table.fields or []:
        if field_descriptions and field.name in field_descriptions:
            field.description = field_descriptions[field.name]
        fields.append(field_to_frictionless_schema(field))
    return {"fields": fields}


def _resources_from_report(
    report,
    input_path: str,
    resource_path: str,
    field_descriptions: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    tables = report.tables or []
    if not tables:
        return resources

    file_format, mediatype = _guess_format_mediatype(input_path, report.file_type)
    encoding = (report.metadata or {}).get("encoding")

    if len(tables) == 1:
        table = tables[0]
        resource_name = os.path.splitext(os.path.basename(input_path))[0] or "resource"
        resource: dict[str, Any] = {
            "name": resource_name,
            "path": resource_path,
            "schema": _build_resource_schema(table, field_descriptions),
        }
        if file_format:
            resource["format"] = file_format
        if mediatype:
            resource["mediatype"] = mediatype
        if encoding:
            resource["encoding"] = encoding
        if report.file_size and os.path.exists(input_path) and not _is_url(input_path):
            resource["bytes"] = report.file_size
        resources.append(resource)
        return resources

    for idx, table in enumerate(tables):
        name = table.id or f"resource_{idx + 1}"
        slug = _slugify(str(name))
        resource = {
            "name": slug,
            "title": str(name),
            "path": resource_path,
            "schema": _build_resource_schema(table, field_descriptions),
        }
        if file_format:
            resource["format"] = file_format
        if mediatype:
            resource["mediatype"] = mediatype
        if encoding:
            resource["encoding"] = encoding
        resources.append(resource)
    return resources


def _apply_ai_field_descriptions(
    reports: list[Any],
    options: dict[str, Any],
) -> dict[str, str]:
    if not options.get("autodoc"):
        return {}
    try:
        ai_config = options.get("ai_config") or {}
        ai_service = get_ai_service(provider=options.get("ai_provider"), config=ai_config)
        field_names: list[str] = []
        for report in reports:
            field_names.extend(_get_primary_fields(report))
        field_names = list(dict.fromkeys(field_names))
        if not field_names:
            return {}
        return get_fields_info(
            field_names,
            language=options.get("lang", "English"),
            ai_service=ai_service,
        )
    except Exception as exc:
        logger.warning("package: failed to generate AI field descriptions: %s", exc)
        return {}


def _build_package_metadata(report, samples: list[Any], options: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(report.metadata or {})
    field_names = _get_primary_fields(report)
    metadata.setdefault("title", _build_title(report.filename))
    keywords = _extract_keywords(field_names)
    metadata.setdefault("keywords", keywords)
    metadata.setdefault("geographic_coverage", _extract_geographic_coverage(samples, field_names))
    metadata.setdefault("temporal_coverage", _extract_temporal_coverage(samples, field_names))
    metadata.setdefault("languages", _detect_languages(samples, field_names))
    metadata.setdefault("data_theme", _guess_data_theme(field_names, keywords))
    if not metadata.get("description"):
        table = report.tables[0] if report.tables else None
        if table and table.description:
            metadata["description"] = table.description
    if options.get("autodoc"):
        try:
            ai_config = options.get("ai_config") or {}
            ai_service = get_ai_service(provider=options.get("ai_provider"), config=ai_config)
            sample_csv = _build_sample_csv(samples, field_names)
            if sample_csv:
                ai_metadata = get_structured_metadata(
                    sample_csv,
                    field_names,
                    language=options.get("lang", "English"),
                    ai_service=ai_service,
                )
                if ai_metadata and isinstance(ai_metadata.get("data_theme"), dict):
                    label = ai_metadata["data_theme"].get("label")
                    if label in DATA_THEME_URI_BY_LABEL and not ai_metadata["data_theme"].get(
                        "uri"
                    ):
                        ai_metadata["data_theme"]["uri"] = DATA_THEME_URI_BY_LABEL.get(label)
                    if label not in DATA_THEME_URI_BY_LABEL:
                        ai_metadata["data_theme"] = None
                _merge_ai_metadata(metadata, ai_metadata)
            else:
                logger.debug("package: AI metadata skipped (no sample CSV)")
        except Exception as exc:
            logger.warning("package: failed to generate AI metadata: %s", exc)
    return metadata


def _merge_package_metadata(package: dict[str, Any], metadata: dict[str, Any]) -> None:
    for key in ("geographic_coverage", "temporal_coverage", "languages", "data_theme"):
        value = metadata.get(key)
        if value:
            package[key] = value


def _analyze_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "filetype": get_option(options, "format_in"),
        "objects_limit": get_option(options, "objects_limit") or OBJECTS_ANALYZE_LIMIT,
        "encoding": get_option(options, "encoding"),
        "delimiter": get_option(options, "delimiter"),
        "engine": get_option(options, "engine") or "auto",
        "table_name": get_option(options, "table") or get_option(options, "sheet"),
        "start_page": get_option(options, "start_page") or 0,
        "trust": bool(get_option(options, "trust")),
    }


def _validate_local_input(input_path: str) -> None:
    if _is_url(input_path):
        return
    try:
        validate_file_path(input_path, check_read=True)
    except FileNotFoundError as exc:
        suggestions = find_similar_files(input_path)
        raise FileNotFoundError(input_path, suggestions) from exc


def _write_package_file(package: dict[str, Any], output_file: str) -> None:
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf8") as output_stream:
        output_stream.write(json.dumps(package, indent=2, ensure_ascii=False))
        output_stream.write("\n")


def _maybe_zip_package(package_dir: str, zip_path: str | None) -> str | None:
    if not zip_path:
        return None
    archive_base = zip_path
    if archive_base.endswith(".zip"):
        archive_base = archive_base[:-4]
    archive_path = shutil.make_archive(archive_base, "zip", package_dir)
    return archive_path


class Packager:
    """Frictionless Data Package command handler."""

    def _build_resources(
        self,
        input_files: list[str],
        options: dict[str, Any],
        output_file: str,
        package_dir: str | None,
    ) -> tuple[list[dict[str, Any]], Any]:
        """Analyze input files and return Frictionless resource descriptors."""
        analyze_opts = _analyze_options(options)
        resources: list[dict[str, Any]] = []
        analyzed_reports: list[Any] = []
        temp_files: list[str] = []

        for input_path in input_files:
            _validate_local_input(input_path)

        try:
            for input_path in input_files:
                working_path = input_path
                if _is_url(input_path):
                    working_path = _download_to_temp(input_path)
                    temp_files.append(working_path)

                report = analyze(
                    working_path,
                    filetype=analyze_opts["filetype"],
                    objects_limit=analyze_opts["objects_limit"],
                    encoding=analyze_opts["encoding"],
                    delimiter=analyze_opts["delimiter"],
                    engine=analyze_opts["engine"],
                    autodoc=False,
                    table_name=analyze_opts["table_name"],
                    start_page=analyze_opts["start_page"],
                    trust=analyze_opts["trust"],
                    options=options,
                )
                analyzed_reports.append(report)
                report.filename = input_path

                resource_path = input_path
                if package_dir and os.path.exists(input_path) and not _is_url(input_path):
                    dest_path = os.path.join(package_dir, os.path.basename(input_path))
                    if os.path.abspath(input_path) != os.path.abspath(dest_path):
                        shutil.copy2(input_path, dest_path)
                    resource_path = os.path.basename(dest_path)
                else:
                    resource_path = _resource_path(input_path, output_file, package_dir)

                resources.extend(_resources_from_report(report, input_path, resource_path))
        finally:
            for temp_path in temp_files:
                try:
                    os.remove(temp_path)
                except OSError:
                    continue

        field_descriptions = _apply_ai_field_descriptions(analyzed_reports, options)
        if field_descriptions:
            for resource in resources:
                schema = resource.get("schema", {})
                for field in schema.get("fields", []):
                    name = field.get("name")
                    if name in field_descriptions:
                        field["description"] = field_descriptions[name]
        primary_report = analyzed_reports[0] if analyzed_reports else None
        if primary_report:
            primary_report.filename = input_files[0]
        return resources, primary_report

    def create(
        self, input_files: list[str], options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Generate a Frictionless Data Package descriptor.

        Args:
            input_files: Local paths or HTTP(S) URLs to package.
            options: Command options (output, metadata, autodoc, etc.).

        Returns:
            The generated package descriptor dictionary.

        Raises:
            ValidationError: When inputs are missing or processing fails.
            FileNotFoundError: When a local input file does not exist.
        """
        if options is None:
            options = {}
        if not input_files:
            raise ValidationError("No input files provided.")

        package_dir = get_option(options, "package_dir")
        output_file = get_option(options, "output")
        if package_dir:
            os.makedirs(package_dir, exist_ok=True)
            if output_file:
                output_file = os.path.join(package_dir, os.path.basename(output_file))
            else:
                output_file = os.path.join(package_dir, "datapackage.json")
        elif output_file is None:
            output_file = os.path.join(os.getcwd(), "datapackage.json")

        elif output_file is None:
            output_file = os.path.join(os.getcwd(), "datapackage.json")

        resources, primary_report = self._build_resources(
            input_files, options, output_file, package_dir
        )
        if primary_report is None or not resources:
            raise ValidationError("Failed to generate package resources.")

        samples = _build_samples(primary_report.filename, options)
        metadata = _build_package_metadata(primary_report, samples, options)

        name = get_option(options, "name") or _slugify(
            metadata.get("title") or primary_report.filename
        )
        title = get_option(options, "title") or metadata.get("title")
        description = get_option(options, "description") or metadata.get("description")
        keywords = _normalize_keywords(get_option(options, "keywords")) or metadata.get("keywords")

        package: dict[str, Any] = {
            "profile": FRICTIONLESS_PROFILE,
            "name": name,
            "resources": resources,
        }
        if title:
            package["title"] = title
        if description:
            package["description"] = description
        if keywords:
            package["keywords"] = keywords

        licenses = _parse_kv_entries(get_option(options, "licenses"), "name")
        if licenses:
            package["licenses"] = licenses

        sources = _parse_kv_entries(get_option(options, "sources"), "title")
        if sources:
            package["sources"] = sources

        contributors = _parse_kv_entries(get_option(options, "contributors"), "title")
        if contributors:
            package["contributors"] = contributors

        version = get_option(options, "version")
        if version:
            package["version"] = version

        _merge_package_metadata(package, metadata)
        _write_package_file(package, output_file)

        zip_path = get_option(options, "zip")
        archive_path = None
        if zip_path and package_dir:
            archive_path = _maybe_zip_package(package_dir, zip_path)

        if not options.get("quiet"):
            field_count = sum(len(r.get("schema", {}).get("fields", [])) for r in resources)
            console.print(
                f"[green]✓[/green] Created Frictionless Data Package ([cyan]{output_file}[/cyan])"
            )
            console.print(
                f"  Resources: {len(resources)} | Fields: {field_count} | Profile: {FRICTIONLESS_PROFILE}"
            )
            if archive_path:
                console.print(f"  Archive: [cyan]{archive_path}[/cyan]")

        result = {"package": package, "output_file": output_file}
        if archive_path:
            result["archive_path"] = archive_path
        return result

    def add_resource(
        self,
        package_file: str,
        input_files: list[str],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add resources to an existing Frictionless Data Package descriptor.

        Args:
            package_file: Path to an existing ``datapackage.json``.
            input_files: New files to append as resources.
            options: Additional packaging options.

        Returns:
            Updated package descriptor dictionary.
        """
        if options is None:
            options = {}
        if not input_files:
            raise ValidationError("No input files provided.")
        if not os.path.exists(package_file):
            suggestions = find_similar_files(package_file)
            raise FileNotFoundError(package_file, suggestions)

        with open(package_file, encoding="utf8") as stream:
            package = json.load(stream)

        package_dir = get_option(options, "package_dir") or os.path.dirname(
            os.path.abspath(package_file)
        )
        options = dict(options)
        options["package_dir"] = package_dir
        options["output"] = package_file
        options["quiet"] = True

        existing_paths = {
            resource.get("path")
            for resource in package.get("resources", [])
            if resource.get("path")
        }
        new_inputs = []
        for input_path in input_files:
            candidate = os.path.basename(input_path) if not _is_url(input_path) else input_path
            if candidate in existing_paths:
                logger.warning("package: skipping duplicate resource path %s", candidate)
                continue
            new_inputs.append(input_path)
        if not new_inputs:
            raise ValidationError("All input files are already present in the package.")

        created = self._build_resources(new_inputs, options, package_file, package_dir)
        new_resources, _primary = created
        package.setdefault("resources", []).extend(new_resources)
        _write_package_file(package, package_file)

        if not options.get("quiet"):
            console.print(
                f"[green]✓[/green] Added {len(new_resources)} resource(s) to "
                f"[cyan]{package_file}[/cyan]"
            )
        return {"package": package, "output_file": package_file}

    def validate(self, package_file: str, options: dict[str, Any] | None = None) -> bool:
        """Validate a Frictionless Data Package descriptor.

        Uses the optional ``frictionless`` library when installed; otherwise
        performs basic structural checks.

        Args:
            package_file: Path to ``datapackage.json``.
            options: Validation options (``limit_rows``, ``check_data``).

        Returns:
            True when validation passes.

        Raises:
            FileNotFoundError: When the package file does not exist.
            ValidationError: When validation fails.
        """
        if options is None:
            options = {}
        if not os.path.exists(package_file):
            suggestions = find_similar_files(package_file)
            raise FileNotFoundError(package_file, suggestions)

        try:
            from frictionless import validate as frictionless_validate
        except ImportError as exc:
            return self._validate_basic(package_file, exc, options=options)

        limit_rows = get_option(options, "limit_rows")
        validate_kwargs: dict[str, Any] = {"type": "package"}
        if limit_rows is not None:
            validate_kwargs["limit_rows"] = limit_rows
        if options.get("check_data") is False:
            validate_kwargs["checklist"] = "metadata"

        report = frictionless_validate(package_file, **validate_kwargs)
        if report.valid:
            if not options.get("quiet"):
                console.print(f"[green]✓[/green] Package is valid: [cyan]{package_file}[/cyan]")
            return True

        if not options.get("quiet"):
            console.print(f"[red]✗[/red] Package validation failed: [cyan]{package_file}[/cyan]")
            console.print(str(report))
        raise ValidationError(f"Package validation failed: {package_file}")

    def _validate_basic(
        self,
        package_file: str,
        import_error: Exception,
        options: dict[str, Any] | None = None,
    ) -> bool:
        if options is None:
            options = {}
        with open(package_file, encoding="utf8") as stream:
            package = json.load(stream)

        errors: list[str] = []
        if not package.get("name"):
            errors.append("Missing required field 'name'")
        resources = package.get("resources")
        if not isinstance(resources, list) or not resources:
            errors.append("'resources' must be a non-empty list")
        else:
            for idx, resource in enumerate(resources, start=1):
                if not resource.get("name"):
                    errors.append(f"Resource #{idx} is missing 'name'")
                if not resource.get("path"):
                    errors.append(f"Resource #{idx} is missing 'path'")

        if errors:
            message = "Package validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValidationError(message)

        if not options.get("quiet"):
            console.print(
                f"[yellow]![/yellow] Basic validation passed for [cyan]{package_file}[/cyan]. "
                "Install optional dependency for full checks: pip install undatum[frictionless]"
            )
            logger.debug("frictionless import failed: %s", import_error)
        return True
