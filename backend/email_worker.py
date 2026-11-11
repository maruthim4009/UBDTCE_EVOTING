"""Process a bounded batch of queued student activation invitations.

Run this command from the backend directory through a scheduler or a separate
worker process. It never prints recipients, credentials, or activation links.
"""

import argparse
import time

from app import process_pending_activation_emails


def main():
    parser = argparse.ArgumentParser(
        description="Deliver queued UBDTCE student activation emails."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum queued messages to process (1-500; default: 25).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep one bounded worker process running and poll for queued jobs.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=30,
        help="Polling interval in watch mode (5-300; default: 30).",
    )
    args = parser.parse_args()
    if not 5 <= args.interval_seconds <= 300:
        parser.error("--interval-seconds must be between 5 and 300.")

    try:
        while True:
            summary = process_pending_activation_emails(args.limit)
            print(
                "Activation email worker batch completed: "
                f"attempted={summary['attempted']} "
                f"sent={summary['sent']} "
                f"failed={summary['failed']} "
                f"skipped={summary['skipped']}"
            )
            if not args.watch:
                break
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("Activation email worker stopped.")


if __name__ == "__main__":
    main()
