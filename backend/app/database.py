import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.sqlite3"


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            notes TEXT,
            date TEXT NOT NULL
        )
        """
    )
    connection.commit()
    columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)").fetchall()}
    migrations = {
        "kind": "ALTER TABLE transactions ADD COLUMN kind TEXT NOT NULL DEFAULT 'expense'",
        "payment_method": "ALTER TABLE transactions ADD COLUMN payment_method TEXT",
        "merchant": "ALTER TABLE transactions ADD COLUMN merchant TEXT",
        "recurring": "ALTER TABLE transactions ADD COLUMN recurring INTEGER NOT NULL DEFAULT 0",
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL DEFAULT 'savings',
            institution TEXT,
            opening_balance REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'INR',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            period TEXT NOT NULL DEFAULT 'monthly',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL NOT NULL DEFAULT 0,
            target_date TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'monthly',
            status TEXT NOT NULL DEFAULT 'upcoming',
            created_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    return connection
