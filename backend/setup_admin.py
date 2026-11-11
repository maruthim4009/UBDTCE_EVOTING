
import getpass

from werkzeug.security import generate_password_hash

from db import get_db_connection


def main():
    print("\n=== UBDTCE Secure E-Voting: Principal Setup ===\n")

    email = input("Enter Principal email: ").strip().lower()

    if not email or "@" not in email:
        print("Invalid email address.")
        return

    password = getpass.getpass("Create a strong password: ")
    confirm = getpass.getpass("Confirm password: ")

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    if password != confirm:
        print("Passwords do not match.")
        return

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO accounts (email, role)
                    VALUES (%s, 'PRINCIPAL')
                    ON CONFLICT (email) DO NOTHING
                    RETURNING id;
                    """,
                    (email,),
                )

                result = cur.fetchone()

                if result is None:
                    print("An account with this email already exists.")
                    return

                account_id = result[0]

                cur.execute(
                    """
                    INSERT INTO account_credentials
                        (account_id, password_hash)
                    VALUES (%s, %s);
                    """,
                    (account_id, password_hash),
                )

        print("Principal account created successfully.")
        print("Keep your email and password secure.")

    except Exception:
        print("Principal setup failed. Check the backend terminal logs.")
        raise


if __name__ == "__main__":
    main()
