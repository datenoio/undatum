"""Data plotting module for generating visualizations."""

import logging
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg")  # Use non-interactive backend by default
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

from ..common.command_utils import get_iterable_options, iter_command_rows
from ..common.filter import match_filter
from ..common.progress import progress
from ..common.s3_iterable import open_iterable_with_s3

logger = logging.getLogger(__name__)


class Plotter:
    """Generate data visualizations from data files."""

    def __init__(self):
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError(
                "matplotlib is required for plotting. Install with: pip install matplotlib"
            )

    def plot(
        self,
        fromfile: str,
        field: str,
        plot_type: str = "auto",
        output: str | None = None,
        output_format: str | None = None,
        title: str | None = None,
        xlabel: str | None = None,
        ylabel: str | None = None,
        width: float = 10,
        height: float = 6,
        dpi: int = 100,
        color: str | None = None,
        **options,
    ):
        """Generate a plot from data file.

        Args:
            fromfile: Path to input file
            field: Field name(s) to plot (comma-separated for multiple)
            plot_type: Plot type ('histogram', 'bar', 'scatter', 'line', 'auto')
            output: Output file path (None for display)
            output_format: Output format ('png', 'svg', 'pdf', None for auto-detect)
            title: Plot title
            xlabel: X-axis label
            ylabel: Y-axis label
            width: Figure width in inches
            height: Figure height in inches
            dpi: Resolution for raster formats
            color: Color scheme name
            **options: Additional options (filter, aggregate, value_field, top_n)
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError(
                "matplotlib is required for plotting. Install with: pip install matplotlib"
            )

        style = options.get("style")
        if style:
            plt.style.use(style)

        # Parse field names
        fields = [f.strip() for f in field.split(",")]

        # Auto-detect plot type if needed
        if plot_type == "auto":
            plot_type = self._detect_plot_type(fromfile, fields, options)

        # Determine output format
        if output_format is None and output:
            output_format = self._detect_output_format(output)
        elif output_format is None:
            output_format = "png"  # Default format

        # Read data
        data = self._read_data(fromfile, fields, options)
        data = self._filter_data(data, options.get("filter"))
        data = self._aggregate_data(data, fields, options, plot_type)

        # Generate plot
        if plot_type == "histogram":
            self._plot_histogram(
                data,
                fields,
                output,
                output_format,
                title,
                xlabel,
                ylabel,
                width,
                height,
                dpi,
                color,
            )
        elif plot_type == "bar":
            self._plot_bar(
                data,
                fields,
                output,
                output_format,
                title,
                xlabel,
                ylabel,
                width,
                height,
                dpi,
                color,
            )
        elif plot_type == "scatter":
            self._plot_scatter(
                data,
                fields,
                output,
                output_format,
                title,
                xlabel,
                ylabel,
                width,
                height,
                dpi,
                color,
            )
        elif plot_type == "line":
            self._plot_line(
                data,
                fields,
                output,
                output_format,
                title,
                xlabel,
                ylabel,
                width,
                height,
                dpi,
                color,
            )
        else:
            raise ValueError(f"Unsupported plot type: {plot_type}")

    def _detect_plot_type(self, fromfile: str, fields: list[str], options: dict[str, Any]) -> str:
        """Auto-detect appropriate plot type based on field types."""
        # Sample data to detect types
        try:
            iterable_context = open_iterable_with_s3(
                fromfile, mode="r", iterableargs=get_iterable_options(options)
            )
            iterable = iterable_context.__enter__()
            try:
                sample = next(iter_command_rows(iterable, options), None)
                if isinstance(sample, dict):
                    # Check field types
                    for field in fields:
                        value = sample.get(field)
                        if value is None:
                            continue
                        # If numeric, suggest histogram
                        if isinstance(value, (int, float)):
                            return "histogram"
                        # If string/categorical, suggest bar
                        elif isinstance(value, str):
                            return "bar"
            finally:
                iterable.close()
                iterable_context.__exit__(None, None, None)
        except Exception:
            # Best effort: never fail the command because of this step.
            logging.getLogger(__name__).debug(
                "plot type detection failed; defaulting to histogram", exc_info=True
            )

        # Default to histogram
        return "histogram"

    def _detect_output_format(self, output: str) -> str:
        """Detect output format from file extension."""
        ext = output.lower().split(".")[-1]
        if ext in ("png", "jpg", "jpeg"):
            return "png"
        elif ext == "svg":
            return "svg"
        elif ext == "pdf":
            return "pdf"
        else:
            return "png"  # Default

    def _read_data(
        self, fromfile: str, fields: list[str], options: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Read data from file for plotting."""
        data = []
        extra_fields = []
        value_field = options.get("value_field")
        if value_field and value_field not in fields:
            extra_fields.append(value_field)
        keep_all = bool(options.get("filter"))
        iterable_context = open_iterable_with_s3(
            fromfile, mode="r", iterableargs=get_iterable_options(options)
        )
        iterable = iterable_context.__enter__()

        try:
            for record in progress(iter_command_rows(iterable, options), desc="Reading data"):
                if isinstance(record, dict):
                    if keep_all:
                        data.append(record)
                    else:
                        keys = list(fields) + extra_fields
                        data.append({f: record.get(f) for f in keys})
                # Handle non-dict records
                elif len(fields) == 1 and len(record) > 0:
                    data.append(
                        {fields[0]: record[0] if isinstance(record, (list, tuple)) else record}
                    )
        finally:
            iterable.close()
            iterable_context.__exit__(None, None, None)

        return data

    def _filter_data(
        self, data: list[dict[str, Any]], filter_expr: str | None
    ) -> list[dict[str, Any]]:
        """Apply an optional filter expression before plotting."""
        if not filter_expr:
            return data
        return [record for record in data if match_filter(record, filter_expr)]

    def _aggregate_data(
        self,
        data: list[dict[str, Any]],
        fields: list[str],
        options: dict[str, Any],
        plot_type: str,
    ) -> list[dict[str, Any]]:
        """Aggregate records for bar charts (count/sum/mean).

        ``aggregate`` defaults to ``count`` (frequency of the plotted field).
        ``sum`` and ``mean`` require ``value_field``. ``top_n`` keeps the highest
        aggregated groups for bar charts. Histogram/scatter/line plots skip
        aggregation so raw values are preserved.
        """
        from collections import defaultdict

        aggregate = (options.get("aggregate") or "count").lower()
        value_field = options.get("value_field")
        top_n = options.get("top_n")
        if plot_type != "bar" or aggregate == "none":
            return data
        if aggregate not in {"count", "sum", "mean", "none"}:
            raise ValueError(f"Unsupported aggregate: {aggregate}")
        if aggregate in {"sum", "mean"} and not value_field:
            raise ValueError("--value-field is required for sum/mean aggregation")

        group_field = fields[0]
        grouped: dict[Any, list[float]] = defaultdict(list)
        for record in data:
            key = record.get(group_field)
            if key is None:
                continue
            if aggregate == "count":
                grouped[key].append(1.0)
            else:
                raw = record.get(value_field)
                try:
                    grouped[key].append(float(raw))
                except (TypeError, ValueError):
                    continue

        aggregated = []
        for key, values in grouped.items():
            if aggregate == "count":
                metric = float(len(values))
            elif aggregate == "sum":
                metric = sum(values)
            else:
                metric = sum(values) / len(values) if values else 0.0
            aggregated.append({group_field: key, "_count": metric})

        if top_n:
            aggregated.sort(key=lambda row: row.get("_count") or 0, reverse=True)
            aggregated = aggregated[: int(top_n)]
        return aggregated

    def _plot_histogram(
        self,
        data: list[dict[str, Any]],
        fields: list[str],
        output: str | None,
        output_format: str,
        title: str | None,
        xlabel: str | None,
        ylabel: str | None,
        width: float,
        height: float,
        dpi: int,
        color: str | None,
    ):
        """Generate histogram plot."""
        fig, axes = plt.subplots(1, len(fields), figsize=(width, height), squeeze=False)
        axes = axes.flatten()

        for idx, field in enumerate(fields):
            ax = axes[idx]
            values = [r.get(field) for r in data if r.get(field) is not None]
            numeric_values = [v for v in values if isinstance(v, (int, float))]

            if not numeric_values:
                logger.warning(f"Field {field} has no numeric values, skipping")
                continue

            ax.hist(numeric_values, bins=30, color=color, edgecolor="black", alpha=0.7)
            ax.set_xlabel(xlabel or field)
            ax.set_ylabel(ylabel or "Frequency")
            ax.set_title(title or f"Distribution of {field}")
            ax.grid(True, alpha=0.3)

        # Hide unused subplots
        for idx in range(len(fields), len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        self._save_or_show(output, output_format, dpi)

    def _plot_bar(
        self,
        data: list[dict[str, Any]],
        fields: list[str],
        output: str | None,
        output_format: str,
        title: str | None,
        xlabel: str | None,
        ylabel: str | None,
        width: float,
        height: float,
        dpi: int,
        color: str | None,
    ):
        """Generate bar chart plot."""
        fig, axes = plt.subplots(1, len(fields), figsize=(width, height), squeeze=False)
        axes = axes.flatten()

        for idx, field in enumerate(fields):
            ax = axes[idx]
            values = [r.get(field) for r in data if r.get(field) is not None]

            if data and "_count" in data[0]:
                categories = [r.get(field) for r in data if r.get(field) is not None]
                frequencies = [r.get("_count") or 0 for r in data if r.get(field) is not None]
            else:
                from collections import Counter

                counts = Counter(values)
                categories = list(counts.keys())
                frequencies = list(counts.values())

            # Sort by frequency (descending)
            sorted_pairs = sorted(
                zip(categories, frequencies, strict=False), key=lambda x: x[1], reverse=True
            )
            categories, frequencies = zip(*sorted_pairs, strict=False) if sorted_pairs else ([], [])

            ax.bar(range(len(categories)), frequencies, color=color)
            ax.set_xticks(range(len(categories)))
            ax.set_xticklabels(categories, rotation=45, ha="right")
            ax.set_xlabel(xlabel or field)
            ax.set_ylabel(ylabel or "Frequency")
            ax.set_title(title or f"Frequency of {field}")
            ax.grid(True, alpha=0.3, axis="y")

        # Hide unused subplots
        for idx in range(len(fields), len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        self._save_or_show(output, output_format, dpi)

    def _plot_scatter(
        self,
        data: list[dict[str, Any]],
        fields: list[str],
        output: str | None,
        output_format: str,
        title: str | None,
        xlabel: str | None,
        ylabel: str | None,
        width: float,
        height: float,
        dpi: int,
        color: str | None,
    ):
        """Generate scatter plot."""
        if len(fields) < 2:
            raise ValueError("Scatter plot requires at least 2 fields")

        fig, ax = plt.subplots(1, 1, figsize=(width, height))

        x_field = fields[0]
        y_field = fields[1]

        x_values = [r.get(x_field) for r in data if r.get(x_field) is not None]
        y_values = [r.get(y_field) for r in data if r.get(y_field) is not None]

        # Filter to numeric pairs
        pairs = [
            (x, y)
            for x, y in zip(x_values, y_values, strict=False)
            if isinstance(x, (int, float)) and isinstance(y, (int, float))
        ]
        if pairs:
            x_vals, y_vals = zip(*pairs, strict=False)
            ax.scatter(x_vals, y_vals, color=color, alpha=0.6)

        ax.set_xlabel(xlabel or x_field)
        ax.set_ylabel(ylabel or y_field)
        ax.set_title(title or f"{x_field} vs {y_field}")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        self._save_or_show(output, output_format, dpi)

    def _plot_line(
        self,
        data: list[dict[str, Any]],
        fields: list[str],
        output: str | None,
        output_format: str,
        title: str | None,
        xlabel: str | None,
        ylabel: str | None,
        width: float,
        height: float,
        dpi: int,
        color: str | None,
    ):
        """Generate line plot."""
        fig, ax = plt.subplots(1, 1, figsize=(width, height))

        for field in fields:
            values = [r.get(field) for r in data if r.get(field) is not None]
            numeric_values = [v for v in values if isinstance(v, (int, float))]

            if numeric_values:
                ax.plot(numeric_values, label=field, color=color, alpha=0.7)

        ax.set_xlabel(xlabel or "Index")
        ax.set_ylabel(ylabel or "Value")
        ax.set_title(title or "Line Plot")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        self._save_or_show(output, output_format, dpi)

    def _save_or_show(self, output: str | None, output_format: str, dpi: int):
        """Save plot to file or display it."""
        if output:
            plt.savefig(output, format=output_format, dpi=dpi, bbox_inches="tight")
            logger.info(f"Plot saved to {output}")
        else:
            # Try to use interactive backend for display
            try:
                matplotlib.use("TkAgg")  # Try TkAgg backend
                plt.show()
            except Exception:
                logger.warning(
                    "Could not display plot interactively. Specify --output to save to file."
                )
                # Save to temporary file as fallback
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    plt.savefig(tmp.name, format="png", dpi=dpi, bbox_inches="tight")
                    logger.info(f"Plot saved to temporary file: {tmp.name}")

        plt.close()
