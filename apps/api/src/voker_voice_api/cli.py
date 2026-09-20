import argparse

from voker_voice_api.bootstrap import ensure_development_seed
from voker_voice_api.database import SessionLocal


def seed() -> None:
    with SessionLocal.begin() as db:
        ensure_development_seed(db)
    print("Development seed is ready")


def main() -> None:
    parser = argparse.ArgumentParser(description="Voker Voice API maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="Create the idempotent development seed")
    args = parser.parse_args()

    if args.command == "seed":
        seed()


if __name__ == "__main__":
    main()
