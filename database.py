"""
Database module for Library-Bot.

Provides SQLite database initialization, data seeding, and helper
functions for searching books, checking availability, and reserving books.
"""

import csv
import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")
BOOKS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books.csv")
MEMBERS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "members.csv")
NOVELS_COMICS_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "novels_comics.csv"
)


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Connects to the SQLite database and sets row_factory to sqlite3.Row.

    Args:
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        sqlite3.Connection: Database connection with row_factory set.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """
    Creates the books, members, and reservations tables if they do not exist.

    Args:
        db_path: Path to the SQLite database file. Defaults to library.db.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                category TEXT,
                isbn TEXT UNIQUE,
                total_copies INTEGER DEFAULT 1,
                available_copies INTEGER DEFAULT 1
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER REFERENCES books(id),
                member_id INTEGER REFERENCES members(id),
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.commit()


def seed_data(
    db_path: str = DB_PATH,
    books_csv: str = BOOKS_CSV,
    members_csv: str = MEMBERS_CSV,
    novels_comics_csv: str = NOVELS_COMICS_CSV,
) -> None:
    """
    Seeds the database by loading books from books.csv, novels_comics.csv, and members
    from members.csv using Python's csv module. Maps columns to existing tables and skips
    rows if the isbn or email already exists.

    Args:
        db_path: Path to the SQLite database file. Defaults to library.db.
        books_csv: Path to the primary books CSV file. Defaults to books.csv.
        members_csv: Path to the members CSV file. Defaults to members.csv.
        novels_comics_csv: Path to the novels/comics CSV file. Defaults to novels_comics.csv.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()

        # Seed books from CSV files
        for csv_path in (books_csv, novels_comics_csv):
            if os.path.exists(csv_path):
                with open(csv_path, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        isbn = row["isbn"].strip()
                        cursor.execute("SELECT 1 FROM books WHERE isbn = ?;", (isbn,))
                        if cursor.fetchone() is not None:
                            continue

                        cursor.execute(
                            """
                            INSERT INTO books (title, author, category, isbn, total_copies, available_copies)
                            VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            (
                                row["title"].strip(),
                                row["author"].strip(),
                                row["category"].strip(),
                                isbn,
                                int(row.get("total_copies", 1)),
                                int(row.get("available_copies", 1)),
                            ),
                        )

        # Seed members from members_csv
        if os.path.exists(members_csv):
            with open(members_csv, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = row["email"].strip()
                    cursor.execute(
                        "SELECT 1 FROM members WHERE LOWER(email) = LOWER(?);", (email,)
                    )
                    if cursor.fetchone() is not None:
                        continue

                    cursor.execute(
                        "INSERT INTO members (name, email) VALUES (?, ?);",
                        (row["name"].strip(), email),
                    )

        conn.commit()


def search_books(query: str, db_path: str = DB_PATH) -> list[dict]:
    """
    Searches for books where title, author, or category matches the query.

    Args:
        query: The search term to find in title, author, or category.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        list[dict]: A list of up to 10 matching book records as dictionaries.
    """
    pattern = f"%{query.strip()}%"
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, author, category, isbn, total_copies, available_copies
            FROM books
            WHERE title LIKE ? OR author LIKE ? OR category LIKE ?
            ORDER BY id ASC
            LIMIT 10;
            """,
            (pattern, pattern, pattern),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def check_availability(book_id: int, db_path: str = DB_PATH) -> dict:
    """
    Checks the availability and copy counts for a specific book by ID.

    Args:
        book_id: The ID of the book to inspect.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Book information including available and total copies,
              or an error dictionary if the book does not exist.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, author, category, isbn, total_copies, available_copies
            FROM books
            WHERE id = ?;
            """,
            (book_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Book with id {book_id} not found."}

        data = dict(row)
        data["is_available"] = data["available_copies"] > 0
        return data


def reserve_book(
    book_id: int, name: str, email: str, db_path: str = DB_PATH
) -> dict:
    """
    Reserves a book for any user by book_id, name, and email without prior registration.

    Rules:
    - Validates that name is not empty and email contains '@' and a domain dot.
    - If the email is not in the members table, auto-creates a new member. If it exists, reuses it.
    - Decrements available_copies only if > 0, then records the reservation.
    - Returns an error if the book does not exist or has 0 copies.
    - Limits each email to 3 active reservations at a time.
    - Prevents the same email from reserving the same book twice while active.

    Args:
        book_id: The ID of the book to reserve.
        name: Full name of the person reserving.
        email: Email address of the person reserving.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Reservation confirmation details or an error dictionary.
    """
    clean_name = name.strip() if isinstance(name, str) else ""
    clean_email = email.strip() if isinstance(email, str) else ""

    # Validate name
    if not clean_name:
        return {"error": "Name is required to make a reservation."}

    # Validate email format (must contain '@' and '.')
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        return {
            "error": "A valid email address containing '@' and a dot is required."
        }

    with get_conn(db_path) as conn:
        cursor = conn.cursor()

        # Validate book existence
        cursor.execute(
            "SELECT id, title, total_copies, available_copies FROM books WHERE id = ?;",
            (book_id,),
        )
        book = cursor.fetchone()
        if not book:
            return {"error": f"Book with id {book_id} not found."}

        # Check availability
        if book["available_copies"] <= 0:
            return {"error": f"No available copies left for '{book['title']}'."}

        # Check or create member record
        cursor.execute(
            "SELECT id, name, email FROM members WHERE LOWER(email) = LOWER(?);",
            (clean_email,),
        )
        member = cursor.fetchone()
        if member:
            member_id = member["id"]
            member_name = member["name"]
        else:
            cursor.execute(
                "INSERT INTO members (name, email) VALUES (?, ?);",
                (clean_name, clean_email),
            )
            member_id = cursor.lastrowid
            member_name = clean_name

        # Limit to 3 active reservations per email
        cursor.execute(
            """
            SELECT COUNT(*) AS active_count
            FROM reservations r
            JOIN members m ON r.member_id = m.id
            WHERE LOWER(m.email) = LOWER(?) AND r.status = 'active';
            """,
            (clean_email,),
        )
        active_count = cursor.fetchone()["active_count"]
        if active_count >= 3:
            return {
                "error": "Reservation limit reached. You can only have up to 3 active reservations at a time."
            }

        # Prevent duplicate active reservation for the same book
        cursor.execute(
            """
            SELECT 1
            FROM reservations r
            JOIN members m ON r.member_id = m.id
            WHERE LOWER(m.email) = LOWER(?) AND r.book_id = ? AND r.status = 'active'
            LIMIT 1;
            """,
            (clean_email, book_id),
        )
        if cursor.fetchone() is not None:
            return {
                "error": f"You already have an active reservation for '{book['title']}'."
            }

        # Decrement available copies safely
        cursor.execute(
            """
            UPDATE books
            SET available_copies = available_copies - 1
            WHERE id = ? AND available_copies > 0;
            """,
            (book_id,),
        )
        if cursor.rowcount == 0:
            return {"error": f"No available copies left for '{book['title']}'."}

        # Insert reservation
        cursor.execute(
            """
            INSERT INTO reservations (book_id, member_id, status)
            VALUES (?, ?, 'active');
            """,
            (book_id, member_id),
        )
        reservation_id = cursor.lastrowid
        conn.commit()

        return {
            "success": True,
            "reservation_id": reservation_id,
            "book_id": book_id,
            "book_title": book["title"],
            "member_id": member_id,
            "member_name": member_name,
            "member_email": clean_email,
            "status": "active",
            "available_copies": book["available_copies"] - 1,
            "message": f"Successfully reserved '{book['title']}' for {member_name}. Please collect it from the library desk within 3 days.",
        }


def my_reservations(member_email: str, db_path: str = DB_PATH) -> list[dict]:
    """
    Returns the active reservations for a given email address with book details.

    Args:
        member_email: Email address of the member.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        list[dict]: List of active reservation dictionaries with book titles.
    """
    clean_email = member_email.strip() if isinstance(member_email, str) else ""
    if not clean_email:
        return []

    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                r.id AS reservation_id,
                r.book_id,
                b.title AS book_title,
                b.author AS book_author,
                b.category AS book_category,
                b.isbn,
                r.status,
                r.created_at
            FROM reservations r
            JOIN members m ON r.member_id = m.id
            JOIN books b ON r.book_id = b.id
            WHERE LOWER(m.email) = LOWER(?) AND r.status = 'active'
            ORDER BY r.id DESC;
            """,
            (clean_email,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def cancel_reservation(
    reservation_id: int, member_email: str, db_path: str = DB_PATH
) -> dict:
    """
    Cancels an active reservation identified by reservation_id and the member's email.
    Updates its status to 'cancelled' and adds 1 copy back to the book's available copies.

    Args:
        reservation_id: ID of the reservation to cancel.
        member_email: Email address of the member requesting the cancellation.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Confirmation dictionary or an error dictionary.
    """
    clean_email = member_email.strip() if isinstance(member_email, str) else ""
    if not clean_email:
        return {"error": "Email address is required to cancel a reservation."}

    with get_conn(db_path) as conn:
        cursor = conn.cursor()

        # Verify active reservation exists for this email
        cursor.execute(
            """
            SELECT r.id, r.book_id, r.status, b.title AS book_title
            FROM reservations r
            JOIN members m ON r.member_id = m.id
            JOIN books b ON r.book_id = b.id
            WHERE r.id = ? AND LOWER(m.email) = LOWER(?);
            """,
            (reservation_id, clean_email),
        )
        reservation = cursor.fetchone()
        if not reservation:
            return {
                "error": f"Active reservation #{reservation_id} was not found for email '{member_email}'."
            }

        if reservation["status"] != "active":
            return {
                "error": f"Reservation #{reservation_id} is already '{reservation['status']}'."
            }

        # Mark reservation as cancelled
        cursor.execute(
            """
            UPDATE reservations
            SET status = 'cancelled'
            WHERE id = ? AND status = 'active';
            """,
            (reservation_id,),
        )

        # Restore 1 copy to the book's available copies
        cursor.execute(
            """
            UPDATE books
            SET available_copies = available_copies + 1
            WHERE id = ?;
            """,
            (reservation["book_id"],),
        )

        conn.commit()

        return {
            "success": True,
            "reservation_id": reservation_id,
            "book_id": reservation["book_id"],
            "book_title": reservation["book_title"],
            "status": "cancelled",
            "message": f"Reservation #{reservation_id} for '{reservation['book_title']}' has been successfully cancelled.",
        }


def import_books_from_csv(path: str, db_path: str = DB_PATH) -> int:
    """
    Imports books from a CSV file into the books table.
    Skips rows whose ISBN already exists.

    Args:
        path: Path to the CSV file to import.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        int: Number of new books successfully inserted.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV file not found at: {path}")

    inserted_count = 0
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                isbn = row["isbn"].strip()
                # Skip if isbn already exists
                cursor.execute("SELECT 1 FROM books WHERE isbn = ?;", (isbn,))
                if cursor.fetchone() is not None:
                    continue

                cursor.execute(
                    """
                    INSERT INTO books (title, author, category, isbn, total_copies, available_copies)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        row["title"].strip(),
                        row["author"].strip(),
                        row["category"].strip(),
                        isbn,
                        int(row.get("total_copies", 1)),
                        int(row.get("available_copies", 1)),
                    ),
                )
                inserted_count += 1

        conn.commit()

    return inserted_count


def get_all_books(db_path: str = DB_PATH) -> list[dict]:
    """
    Returns all books in the catalog ordered by ID.

    Args:
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        list[dict]: List of all book records as dictionaries.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, author, category, isbn, total_copies, available_copies
            FROM books
            ORDER BY id ASC;
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def get_book_by_id(book_id: int, db_path: str = DB_PATH) -> dict | None:
    """
    Retrieves a single book record by ID using a ? placeholder.

    Args:
        book_id: The ID of the book to retrieve.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict | None: The book record or None if not found.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, author, category, isbn, total_copies, available_copies
            FROM books
            WHERE id = ?;
            """,
            (book_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_book(
    title: str,
    author: str,
    category: str,
    isbn: str,
    total_copies: int,
    available_copies: int,
    db_path: str = DB_PATH,
) -> dict:
    """
    Adds a new book to the catalog using ? placeholders.

    Args:
        title: Title of the book.
        author: Author of the book.
        category: Category of the book.
        isbn: Unique ISBN string.
        total_copies: Total copies in the library.
        available_copies: Available copies currently in stock.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Success details or an error dictionary.
    """
    clean_title = title.strip() if isinstance(title, str) else ""
    clean_author = author.strip() if isinstance(author, str) else ""
    clean_category = category.strip() if isinstance(category, str) else ""
    clean_isbn = isbn.strip() if isinstance(isbn, str) else ""

    if not clean_title or not clean_author:
        return {"error": "Title and author are required."}
    if not clean_isbn:
        return {"error": "ISBN is required."}

    try:
        tot = int(total_copies)
        avail = int(available_copies)
    except (ValueError, TypeError):
        return {"error": "Total copies and available copies must be integers."}

    if tot < 1:
        return {"error": "Total copies must be at least 1."}
    if avail < 0 or avail > tot:
        return {"error": "Available copies must be between 0 and total copies."}

    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM books WHERE isbn = ?;", (clean_isbn,))
        if cursor.fetchone():
            return {"error": f"A book with ISBN '{clean_isbn}' already exists."}

        cursor.execute(
            """
            INSERT INTO books (title, author, category, isbn, total_copies, available_copies)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (clean_title, clean_author, clean_category, clean_isbn, tot, avail),
        )
        conn.commit()
        book_id = cursor.lastrowid
        return {
            "success": True,
            "book_id": book_id,
            "message": f"Book '{clean_title}' was added successfully.",
        }


def update_book(
    book_id: int,
    title: str,
    author: str,
    category: str,
    isbn: str,
    total_copies: int,
    available_copies: int,
    db_path: str = DB_PATH,
) -> dict:
    """
    Updates an existing book's details using ? placeholders.

    Args:
        book_id: The ID of the book to update.
        title: Updated title.
        author: Updated author.
        category: Updated category.
        isbn: Updated ISBN string.
        total_copies: Updated total copies count.
        available_copies: Updated available copies count.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Success details or an error dictionary.
    """
    clean_title = title.strip() if isinstance(title, str) else ""
    clean_author = author.strip() if isinstance(author, str) else ""
    clean_category = category.strip() if isinstance(category, str) else ""
    clean_isbn = isbn.strip() if isinstance(isbn, str) else ""

    if not clean_title or not clean_author:
        return {"error": "Title and author are required."}
    if not clean_isbn:
        return {"error": "ISBN is required."}

    try:
        tot = int(total_copies)
        avail = int(available_copies)
    except (ValueError, TypeError):
        return {"error": "Total copies and available copies must be integers."}

    if tot < 1:
        return {"error": "Total copies must be at least 1."}
    if avail < 0 or avail > tot:
        return {"error": "Available copies must be between 0 and total copies."}

    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM books WHERE id = ?;", (book_id,))
        if not cursor.fetchone():
            return {"error": f"Book with id {book_id} not found."}

        cursor.execute(
            "SELECT id FROM books WHERE isbn = ? AND id != ?;",
            (clean_isbn, book_id),
        )
        if cursor.fetchone():
            return {"error": f"Another book with ISBN '{clean_isbn}' already exists."}

        cursor.execute(
            """
            UPDATE books
            SET title = ?, author = ?, category = ?, isbn = ?, total_copies = ?, available_copies = ?
            WHERE id = ?;
            """,
            (clean_title, clean_author, clean_category, clean_isbn, tot, avail, book_id),
        )
        conn.commit()
        return {
            "success": True,
            "book_id": book_id,
            "message": f"Book '{clean_title}' was updated successfully.",
        }


def delete_book(book_id: int, db_path: str = DB_PATH) -> dict:
    """
    Deletes a book if it has no active reservations.
    Returns an error if the book has active reservations.
    Uses ? placeholders for all queries.

    Args:
        book_id: The ID of the book to delete.
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        dict: Success confirmation or an error dictionary.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM books WHERE id = ?;", (book_id,))
        book = cursor.fetchone()
        if not book:
            return {"error": f"Book with id {book_id} not found."}

        # Check for active reservations
        cursor.execute(
            """
            SELECT COUNT(*) AS active_count
            FROM reservations
            WHERE book_id = ? AND status = 'active';
            """,
            (book_id,),
        )
        active_count = cursor.fetchone()["active_count"]
        if active_count > 0:
            return {
                "error": f"Cannot delete '{book['title']}' because it has {active_count} active reservation(s)."
            }

        # Delete any past cancelled reservations for this book to avoid FK violation
        cursor.execute("DELETE FROM reservations WHERE book_id = ?;", (book_id,))
        cursor.execute("DELETE FROM books WHERE id = ?;", (book_id,))
        conn.commit()
        return {
            "success": True,
            "message": f"Book '{book['title']}' was deleted successfully.",
        }


def get_all_reservations(db_path: str = DB_PATH) -> list[dict]:
    """
    Returns all reservations joining member name, email, book title, status, and date.
    Uses ? placeholders for all queries.

    Args:
        db_path: Path to the SQLite database file. Defaults to library.db.

    Returns:
        list[dict]: List of reservation records.
    """
    with get_conn(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                r.id AS reservation_id,
                m.name AS member_name,
                m.email AS member_email,
                b.id AS book_id,
                b.title AS book_title,
                r.status,
                r.created_at AS date
            FROM reservations r
            JOIN members m ON r.member_id = m.id
            JOIN books b ON r.book_id = b.id
            ORDER BY r.id DESC;
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


if __name__ == "__main__":
    init_db()
    seed_data()

    # Import novels_comics.csv
    novels_comics_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "novels_comics.csv"
    )
    added_count = 0
    if os.path.exists(novels_comics_file):
        added_count = import_books_from_csv(novels_comics_file)
        print(f"Books added from {os.path.basename(novels_comics_file)}: {added_count}")

    with get_conn() as conn:
        book_count = conn.execute("SELECT COUNT(*) FROM books;").fetchone()[0]
        member_count = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
        category_rows = conn.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM books
            GROUP BY category
            ORDER BY count DESC, category ASC;
            """
        ).fetchall()

    print(f"\nDatabase Status: {book_count} total books, {member_count} members.")
    print("\n--- Number of Books per Category ---")
    for r in category_rows:
        print(f"  • {r['category']}: {r['count']}")

    print("\n--- Test Search: 'machine learning' ---")
    search_results = search_books("machine learning")
    for b in search_results:
        print(
            f"[{b['id']}] {b['title']} by {b['author']} "
            f"({b['category']}) - Available: {b['available_copies']}/{b['total_copies']}"
        )
