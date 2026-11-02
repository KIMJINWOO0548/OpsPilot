"""Create or restore a validated SQLite database copy in a new file."""
import argparse
import sqlite3
import sys

from opspilot_x.database_backup import backup_database, restore_database


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    operation = backup_database if args.command == "backup" else restore_database
    try:
        result = operation(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"{args.command.title()} failed: {exc}", file=sys.stderr)
        return 1
    print(f"{args.command.title()} complete; validated {result['tables_validated']} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
