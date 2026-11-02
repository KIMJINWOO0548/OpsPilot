"""Manage local accounts and revoke sessions; never pass passwords as arguments."""
import argparse
import getpass
import os
from pathlib import Path
import sqlite3
from opspilot_x import auth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.getenv('OPSPILOT_DB', './opspilot_demo.sqlite3'))
    parser.add_argument('--username', required=True)
    parser.add_argument('--action', choices=['create', 'disable', 'revoke-sessions'], default='create')
    parser.add_argument('--tenant')
    parser.add_argument('--team')
    parser.add_argument('--role', choices=['viewer', 'engineer', 'approver'])
    args = parser.parse_args()
    if args.action != 'create':
        if any((args.tenant, args.team, args.role)):
            parser.error('Scope and role are only accepted for create')
        if not Path(args.db).is_file():
            parser.error('Account database does not exist')
        try:
            auth.initialize(args.db)
            if args.action == 'disable':
                auth.disable_user(args.db, args.username)
            else:
                auth.revoke_sessions(args.db, args.username)
        except (ValueError, sqlite3.Error) as error:
            parser.error(str(error))
        print('Account disabled; sessions revoked.' if args.action == 'disable' else 'Account sessions revoked.')
        return
    if not all((args.tenant, args.team, args.role)):
        parser.error('Create requires --tenant, --team and --role')
    password = os.getenv('OPSPILOT_INITIAL_PASSWORD') or getpass.getpass('Password (12+ characters): ')
    try:
        auth.create_user(args.db, username=args.username, password=password,
                         tenant=args.tenant, team=args.team, role=args.role)
    except (ValueError, sqlite3.Error) as error:
        parser.error(str(error))
    print('Account created. No default accounts were provisioned.')


if __name__ == '__main__':
    main()
