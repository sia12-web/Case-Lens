"""Format summary dicts into terminal output and markdown."""

from datetime import datetime

DISCLAIMER = (
    "This summary is AI-generated and may contain errors. "
    "All facts, dates, and amounts should be verified against "
    "the source document before use in legal proceedings."
)

# Role display labels
ROLE_LABELS = {
    "petitioner": "Petitioner / Demandeur(esse)",
    "respondent": "Respondent / Défendeur(esse)",
    "child": "Child / Enfant",
    "judge": "Judge / Juge",
    "expert": "Expert",
    "lawyer": "Lawyer / Avocat(e)",
    "other": "Other / Autre",
}

CASE_TYPE_LABELS = {
    "custody": "Custody / Garde",
    "divorce": "Divorce",
    "support": "Support / Pension alimentaire",
    "mixed": "Mixed / Mixte",
    "other": "Other / Autre",
}


def format_terminal(summary: dict) -> str:
    """Format a summary dict into rich-compatible terminal markup.

    Args:
        summary: Successful summary dict from Summarizer.

    Returns:
        String with rich console markup for styled terminal output.
    """
    lines: list[str] = []

    metadata = summary.get("metadata", {})
    filename = metadata.get("filename", "unknown")
    case_type = summary.get("case_type", "unknown")
    case_label = CASE_TYPE_LABELS.get(case_type, case_type)

    # Header
    lines.append("")
    lines.append(f"[bold cyan]{'=' * 60}[/bold cyan]")
    lines.append(f"[bold cyan]  CASE LENS — Summary[/bold cyan]")
    lines.append(f"[bold cyan]{'=' * 60}[/bold cyan]")
    lines.append(f"  [dim]File:[/dim] {filename}")
    lines.append(f"  [dim]Type:[/dim] {case_label}")
    lines.append("")

    # Parties
    parties = summary.get("parties", [])
    if parties:
        lines.append("[bold yellow]  PARTIES[/bold yellow]")
        lines.append(f"  [dim]{'─' * 56}[/dim]")
        for party in parties:
            name = party.get("name", "Unknown")
            role = party.get("role", "other")
            role_label = ROLE_LABELS.get(role, role)
            aliases = party.get("aliases", [])
            alias_str = f" [dim](aka {', '.join(aliases)})[/dim]" if aliases else ""
            cite = _format_cite(party.get("source_pages", []))
            lines.append(f"  [bold]{name}[/bold] — [italic]{role_label}[/italic]{alias_str}{cite}")
        lines.append("")

    # Summary
    summary_text = summary.get("summary", "")
    if summary_text:
        lines.append("[bold green]  SUMMARY[/bold green]")
        lines.append(f"  [dim]{'─' * 56}[/dim]")
        for paragraph in summary_text.split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                lines.append(f"  {paragraph}")
        lines.append("")

    # Key Facts
    facts = summary.get("key_facts", [])
    if facts:
        lines.append("[bold magenta]  KEY FACTS[/bold magenta]")
        lines.append(f"  [dim]{'─' * 56}[/dim]")
        for i, fact in enumerate(facts, 1):
            text, pages = _extract_fact(fact)
            cite = _format_cite(pages)
            lines.append(f"  {i}. {text}{cite}")
        lines.append("")

    # Timeline
    timeline = summary.get("timeline", [])
    if timeline:
        lines.append("[bold blue]  TIMELINE[/bold blue]")
        lines.append(f"  [dim]{'─' * 56}[/dim]")
        for entry in timeline:
            date = entry.get("date", "?")
            event = entry.get("event", "")
            cite = _format_cite(entry.get("pages", []))
            lines.append(f"  [bold]{date}[/bold]  {event}{cite}")
        lines.append("")

    # Verification checklist
    checklist = _build_checklist(summary)
    if checklist:
        lines.append("[bold white]  VERIFICATION CHECKLIST[/bold white]")
        lines.append(f"  [dim]{'─' * 56}[/dim]")
        for item in checklist:
            lines.append(f"  □ {item}")
        lines.append("")

    # Disclaimer
    lines.append(f"  [dim italic]{DISCLAIMER}[/dim italic]")
    lines.append("")

    # Footer
    model = metadata.get("model", "")
    chunks = metadata.get("chunks_processed", 0)
    lines.append(f"  [dim]Model: {model} | Chunks processed: {chunks}[/dim]")
    lines.append(f"[bold cyan]{'=' * 60}[/bold cyan]")
    lines.append("")

    return "\n".join(lines)


def format_verbose(extraction: dict) -> str:
    """Format extraction metadata for --verbose output.

    Args:
        extraction: Output dict from PdfProcessor.process().

    Returns:
        String with rich markup showing extraction details.
    """
    meta = extraction.get("metadata", {})
    chunks = extraction.get("chunks", [])

    lines = [
        "",
        "[dim]  Extraction details:[/dim]",
        f"  [dim]  Pages: {meta.get('total_pages', '?')}[/dim]",
        f"  [dim]  Chunks: {len(chunks)}[/dim]",
        f"  [dim]  Chunked: {meta.get('is_chunked', False)}[/dim]",
    ]
    if chunks:
        total_chars = sum(c.get("char_count", 0) for c in chunks)
        lines.append(f"  [dim]  Total chars: {total_chars:,}[/dim]")
    lines.append("")
    return "\n".join(lines)


def format_error(error: dict) -> str:
    """Format an error dict for terminal display.

    Args:
        error: Error dict with 'error' and 'message' keys.

    Returns:
        String with rich markup for error display.
    """
    code = error.get("error", "unknown_error")
    message = error.get("message", "An unknown error occurred.")
    return f"\n[bold red]  Error: {code}[/bold red]\n  {message}\n"


def format_markdown(summary: dict, filename: str) -> str:
    """Format a summary dict into a markdown document.

    Args:
        summary: Successful summary dict from Summarizer.
        filename: Original PDF filename for the header.

    Returns:
        Markdown string suitable for writing to a .md file.
    """
    lines: list[str] = []
    case_type = summary.get("case_type", "unknown")
    case_label = CASE_TYPE_LABELS.get(case_type, case_type)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"# Case Lens Summary: {filename}")
    lines.append("")
    lines.append(f"**Case Type:** {case_label}  ")
    lines.append(f"**Generated:** {now}  ")
    metadata = summary.get("metadata", {})
    if metadata:
        lines.append(f"**Model:** {metadata.get('model', 'N/A')}  ")
        lines.append(f"**Chunks Processed:** {metadata.get('chunks_processed', 'N/A')}  ")
    lines.append("")

    # Parties
    parties = summary.get("parties", [])
    if parties:
        lines.append("## Parties")
        lines.append("")
        lines.append("| Name | Role | Aliases | Source |")
        lines.append("|------|------|---------|--------|")
        for party in parties:
            name = party.get("name", "Unknown")
            role = ROLE_LABELS.get(party.get("role", "other"), party.get("role", "other"))
            aliases = ", ".join(party.get("aliases", [])) or "—"
            source = _format_cite_plain(party.get("source_pages", []))
            lines.append(f"| {name} | {role} | {aliases} | {source} |")
        lines.append("")

    # Summary
    summary_text = summary.get("summary", "")
    if summary_text:
        lines.append("## Summary")
        lines.append("")
        lines.append(summary_text)
        lines.append("")

    # Key Facts
    facts = summary.get("key_facts", [])
    if facts:
        lines.append("## Key Facts")
        lines.append("")
        for fact in facts:
            text, pages = _extract_fact(fact)
            cite = _format_cite_plain(pages)
            lines.append(f"- {text}{cite}")
        lines.append("")

    # Timeline
    timeline = summary.get("timeline", [])
    if timeline:
        lines.append("## Timeline")
        lines.append("")
        lines.append("| Date | Event | Source |")
        lines.append("|------|-------|--------|")
        for entry in timeline:
            date = entry.get("date", "?")
            event = entry.get("event", "")
            source = _format_cite_plain(entry.get("pages", []))
            lines.append(f"| {date} | {event} | {source} |")
        lines.append("")

    # Verification checklist
    checklist = _build_checklist(summary)
    if checklist:
        lines.append("## Verification Checklist")
        lines.append("")
        for item in checklist:
            lines.append(f"- [ ] {item}")
        lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append(f"*{DISCLAIMER}*")
    lines.append("")
    lines.append(f"*Generated by Case Lens v0.8.0*")
    lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _extract_fact(fact) -> tuple[str, list[int]]:
    """Extract text and pages from a key_fact (str or dict)."""
    if isinstance(fact, str):
        return fact, []
    return fact.get("text", ""), fact.get("pages", [])


def _format_cite(pages: list[int]) -> str:
    """Format page numbers as a rich-markup citation, e.g. ' [dim](p. 1, 3)[/dim]'."""
    if not pages:
        return ""
    return f" [dim](p. {', '.join(map(str, pages))})[/dim]"


def _format_cite_plain(pages: list[int]) -> str:
    """Format page numbers as plain text, e.g. 'p. 1, 3'."""
    if not pages:
        return ""
    return f"p. {', '.join(map(str, pages))}"


def _build_checklist(summary: dict) -> list[str]:
    """Build verification checklist items from structured summary data."""
    items: list[str] = []

    # Parties
    parties = summary.get("parties", [])
    if parties:
        names_with_pages = []
        for p in parties:
            name = p.get("name", "Unknown")
            pages = p.get("source_pages", [])
            if pages:
                names_with_pages.append(f"{name} (p. {', '.join(map(str, pages))})")
            else:
                names_with_pages.append(name)
        items.append(f"Verify parties: {', '.join(names_with_pages)}")

    # Dates from timeline
    timeline = summary.get("timeline", [])
    if timeline:
        dates_with_pages = []
        for e in timeline:
            date = e.get("date", "?")
            pages = e.get("pages", [])
            if pages:
                dates_with_pages.append(f"{date} (p. {', '.join(map(str, pages))})")
            else:
                dates_with_pages.append(date)
        items.append(f"Verify dates: {', '.join(dates_with_pages)}")

    # Key facts count
    facts = summary.get("key_facts", [])
    if facts:
        items.append(f"Verify {len(facts)} key facts against source pages")

    return items
