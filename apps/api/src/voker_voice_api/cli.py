import argparse
import uuid

from voker_voice_api.bootstrap import create_ingest_key, ensure_development_seed, seed_demo_sessions
from voker_voice_api.database import SessionLocal
from voker_voice_api.session_logs import backfill_session_log
from voker_voice_api.worker import expire_recordings, reconcile_stale_sessions, run_once


def seed() -> None:
    with SessionLocal.begin() as db:
        ensure_development_seed(db)
    print("Development seed is ready")


def seed_demo(count: int) -> None:
    with SessionLocal.begin() as db:
        created = seed_demo_sessions(db, count=count)
    print(f"Demo sessions ready: {created} created (existing sessions were preserved)")


def create_key(label: str) -> None:
    with SessionLocal.begin() as db:
        _, project, environment, _ = ensure_development_seed(db)
        generated = create_ingest_key(db, project=project, environment=environment, label=label)
    print("Copy this key now; it is not stored in plaintext:")
    print(generated.raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voker Voice API maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="Create the idempotent development seed")
    demo_parser = subparsers.add_parser(
        "seed-demo", help="Create realistic dashboard demo sessions"
    )
    demo_parser.add_argument("--count", type=int, default=20, choices=range(1, 101))
    create_key_parser = subparsers.add_parser(
        "create-ingest-key", help="Create a development ingest key"
    )
    create_key_parser.add_argument("--label", default="Local development")
    worker_parser = subparsers.add_parser("worker-once", help="Process due durable analysis jobs")
    worker_parser.add_argument("--limit", type=int, default=10)
    subparsers.add_parser("expire-recordings", help="Revoke expired recording references")
    reconcile_parser = subparsers.add_parser(
        "reconcile-sessions", help="Mark stalled sessions incomplete and queue their analysis"
    )
    reconcile_parser.add_argument("--session-id", help="Limit reconciliation to one session UUID")
    log_parser = subparsers.add_parser(
        "export-session-log", help="Backfill a session diagnostic JSONL file from persisted evidence"
    )
    log_parser.add_argument("--session-id", required=True, help="Session UUID")
    args = parser.parse_args()

    if args.command == "seed":
        seed()
    if args.command == "seed-demo":
        seed_demo(args.count)
    if args.command == "create-ingest-key":
        create_key(args.label)
    if args.command == "worker-once":
        print(f"Processed {run_once(limit=args.limit)} jobs")
    if args.command == "expire-recordings":
        with SessionLocal.begin() as db:
            print(f"Expired {expire_recordings(db)} recordings")
    if args.command == "reconcile-sessions":
        with SessionLocal.begin() as db:
            print(
                "Reconciled "
                f"{reconcile_stale_sessions(db, session_id=uuid.UUID(args.session_id) if args.session_id else None)} stalled sessions"
            )
    if args.command == "export-session-log":
        with SessionLocal.begin() as db:
            print(f"Wrote {backfill_session_log(db, args.session_id)} historical events to session log")


if __name__ == "__main__":
    main()
