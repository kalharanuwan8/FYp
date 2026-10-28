"""
Optional CLI wrapper around app.services.default_accounts.

Default admin / teacher / student accounts are also created automatically
when the backend starts (SEED_DEFAULT_ACCOUNTS=true). Use this script to
re-run the same idempotent seed without restarting the server.
"""

from app import create_app
from app.services.default_accounts import DEFAULT_ACCOUNTS, ensure_default_data


def seed_database():
    app = create_app()
    with app.app_context():
        # create_app may already have seeded; ensure_default_data is idempotent
        result = ensure_default_data()

        print("Seeded Grade Levels (Grade 1 - 12)")
        created = set(result.get("accounts_created") or [])
        for acct in DEFAULT_ACCOUNTS:
            status = "Created" if acct["email"] in created else "Already present"
            print(
                f"{status}: {acct['email']} / {acct['password']} ({acct['role']})"
            )
        print("Database seeding completed successfully!")


if __name__ == "__main__":
    seed_database()
