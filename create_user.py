#!/usr/bin/env python3
"""
create_user.py — CLI helper to create CampusHub user accounts.

Run from the project root:
    python create_user.py

Requires the Users table to exist (run the SQL in the README first).
Loads .env for database credentials automatically.
"""

import getpass
import os
import sys

from dotenv import load_dotenv

load_dotenv()

try:
    import mysql.connector
    from werkzeug.security import generate_password_hash
except ImportError:
    print("❌  Missing dependencies. Run:  pip install mysql-connector-python werkzeug")
    sys.exit(1)


def get_conn():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", 3306)),
        database=os.environ.get("DB_NAME", "CampusHub"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
    )


def prompt(label: str, required: bool = True) -> str:
    while True:
        val = input(f"{label}: ").strip()
        if val or not required:
            return val
        print("  ⚠️  This field is required.")


def main():
    print("\n" + "=" * 50)
    print("  CampusHub — Create User Account")
    print("=" * 50 + "\n")

    username = prompt("Username")
    while True:
        password = getpass.getpass("Password (min 6 chars): ").strip()
        if len(password) >= 6:
            break
        print("  ⚠️  Password must be at least 6 characters.")

    print("\nRoles: admin | student | faculty")
    while True:
        role = prompt("Role").lower()
        if role in ("admin", "student", "faculty"):
            break
        print("  ⚠️  Role must be admin, student, or faculty.")

    linked_id = None
    if role in ("student", "faculty"):
        raw = prompt(
            f"Linked {'student_id' if role == 'student' else 'faculty_id'} "
            f"(leave blank for none)",
            required=False,
        )
        if raw:
            try:
                linked_id = int(raw)
            except ValueError:
                print("  ⚠️  Invalid ID — setting linked_id to NULL.")

    pw_hash = generate_password_hash(password)

    try:
        conn = get_conn()
        cur  = conn.cursor()

        # Check duplicate username
        cur.execute("SELECT user_id FROM Users WHERE username = %s", (username,))
        if cur.fetchone():
            print(f"\n❌  Username '{username}' is already taken.")
            sys.exit(1)

        cur.execute(
            "INSERT INTO Users (username, password_hash, role, linked_id) VALUES (%s,%s,%s,%s)",
            (username, pw_hash, role, linked_id),
        )
        conn.commit()
        new_id = cur.lastrowid
        print(f"\n✅  User created successfully!")
        print(f"    user_id  : {new_id}")
        print(f"    username : {username}")
        print(f"    role     : {role}")
        print(f"    linked_id: {linked_id}\n")

    except mysql.connector.Error as e:
        print(f"\n❌  Database error: {e}")
        sys.exit(1)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
