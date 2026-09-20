import argparse

from voker_voice_api.bootstrap import create_ingest_key, ensure_development_seed
from voker_voice_api.database import SessionLocal


def seed() -> None:
    with SessionLocal.begin() as db:
        ensure_development_seed(db)
    print("Development seed is ready")


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
    create_key_parser = subparsers.add_parser(
        "create-ingest-key", help="Create a development ingest key"
    )
    create_key_parser.add_argument("--label", default="Local development")
    args = parser.parse_args()

    if args.command == "seed":
        seed()
    if args.command == "create-ingest-key":
        create_key(args.label)


if __name__ == "__main__":
    main()
