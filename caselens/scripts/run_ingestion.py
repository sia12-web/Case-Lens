"""CLI entry point for CanLII case ingestion.

Usage:
    python -m caselens.scripts.run_ingestion --database qccs --date-after 2020-01-01
"""

import logging
import sys

import click

from caselens.canlii import CanLIIClient
from caselens.database import CaseDatabase
from caselens.embeddings import EmbeddingEngine
from caselens.ingest import CaseIngester


@click.command()
@click.option("--database", required=True, help="CanLII database ID (e.g. qccs, qcca, qccq)")
@click.option("--date-after", default=None, help="Only cases after YYYY-MM-DD")
@click.option("--date-before", default=None, help="Only cases before YYYY-MM-DD")
@click.option("--batch-size", default=100, help="Log progress every N cases")
@click.option("--dry-run", is_flag=True, help="Fetch case list and print count only")
def main(database: str, date_after: str, date_before: str,
         batch_size: int, dry_run: bool) -> None:
    """Ingest Quebec case law from CanLII into Supabase."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    canlii = CanLIIClient()
    if not canlii.api_key:
        click.echo("Error: CANLII_API_KEY not set in .env", err=True)
        sys.exit(1)

    if dry_run:
        click.echo(f"Fetching case list for {database}...")
        cases = canlii.list_all_cases(
            database,
            decision_date_after=date_after,
            decision_date_before=date_before,
        )
        if isinstance(cases, dict) and "error" in cases:
            click.echo(f"Error: {cases['message']}", err=True)
            sys.exit(1)
        click.echo(f"Found {len(cases)} cases in {database}")
        if date_after:
            click.echo(f"  after: {date_after}")
        if date_before:
            click.echo(f"  before: {date_before}")
        return

    db = CaseDatabase()
    embedder = EmbeddingEngine()
    ingester = CaseIngester(canlii, db, embedder)

    click.echo(f"Starting ingestion for {database}...")
    stats = ingester.ingest_database(
        database,
        date_after=date_after,
        date_before=date_before,
        batch_size=batch_size,
    )

    click.echo(f"\nIngestion complete:")
    click.echo(f"  Total cases:  {stats['total']}")
    click.echo(f"  Ingested:     {stats['ingested']}")
    click.echo(f"  Skipped:      {stats['skipped']}")
    click.echo(f"  Errors:       {stats['errors']}")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
