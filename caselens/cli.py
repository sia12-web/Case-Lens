"""Command-line interface for Case Lens."""

import sys

import click
from rich.console import Console

from caselens.pdf_processor import PdfProcessor
from caselens.summarizer import Summarizer
from caselens.formatter import (
    format_terminal,
    format_verbose,
    format_error,
    format_markdown,
)

console = Console()


@click.command()
@click.argument("pdf_path", type=click.Path())
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Save summary as a markdown file at this path.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Show extraction metadata (page count, chunks).",
)
def main(pdf_path: str, output: str | None, verbose: bool) -> None:
    """Analyze a legal PDF and produce a structured summary.

    Extracts text from PDF_PATH, sends it to Claude for analysis,
    and displays a formatted summary of parties, facts, and timeline.

    \b
    Examples:
        python -m caselens document.pdf
        python -m caselens document.pdf --output summary.md
        python -m caselens document.pdf --verbose
    """
    # Step 1: Extract
    processor = PdfProcessor()

    with console.status("[bold cyan]Extracting text from PDF...[/bold cyan]", spinner="dots"):
        extraction = processor.process(pdf_path)

    if "error" in extraction:
        console.print(format_error(extraction))
        sys.exit(1)

    if verbose:
        console.print(format_verbose(extraction))

    # Step 2: Summarize
    summarizer = Summarizer()

    chunk_count = len(extraction.get("chunks", []))
    label = f"[bold cyan]Summarizing with Claude ({chunk_count} chunk{'s' if chunk_count != 1 else ''})...[/bold cyan]"

    with console.status(label, spinner="dots"):
        summary = summarizer.summarize(extraction)

    if "error" in summary:
        console.print(format_error(summary))
        sys.exit(1)

    # Step 3: Display
    console.print(format_terminal(summary))

    # Step 4: Optional markdown export
    if output:
        filename = extraction["metadata"].get("filename", "unknown")
        md_content = format_markdown(summary, filename)
        with open(output, "w", encoding="utf-8") as f:
            f.write(md_content)
        console.print(f"  [green]Saved markdown summary to:[/green] {output}\n")
