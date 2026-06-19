from django.core.management.base import BaseCommand

from apps.analytics.services import process_spool, prune_processed_spool, unprocessed_backlog


class Command(BaseCommand):
    help = (
        "Process queued RawTelemetryEvent rows into Visitor / VisitorSession / "
        "PageVisit / TelemetryEvent. Run on a schedule (e.g. cPanel cron every minute)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--prune-days", type=int, default=7,
                            help="Delete processed spool rows older than this many days.")

    def handle(self, *args, **options):
        backlog = unprocessed_backlog()
        if not backlog:
            self.stdout.write("Telemetry spool is empty.")

        total = 0
        # Drain in batches; stop when a pass clears nothing (prevents looping on
        # poison rows that haven't yet hit the retry cap).
        while True:
            cleared = process_spool(batch_size=options["batch_size"])
            total += cleared
            if cleared == 0:
                break

        pruned = prune_processed_spool(days=options["prune_days"])
        self.stdout.write(self.style.SUCCESS(
            f"Processed {total} telemetry event(s); pruned {pruned} old row(s)."
        ))
