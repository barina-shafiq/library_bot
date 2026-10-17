"""
Flask application for Library-Bot.

Provides endpoints to search books, check book availability,
create reservations, and chat with the AI assistant.
"""

from collections import defaultdict, deque
from functools import wraps
import logging
import os
import time
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database import (
    add_book,
    cancel_reservation,
    check_availability,
    delete_book,
    get_all_books,
    get_all_reservations,
    get_book_by_id,
    get_conn,
    init_db,
    my_reservations,
    reserve_book,
    search_books,
    seed_data,
    update_book,
)
from bot import ask_bot

# Load environment variables
load_dotenv()

# Configure logging to app.log
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("library_bot")

app = Flask(__name__)

# Secret key configuration from environment variable
SECRET_KEY = os.getenv("SECRET_KEY")
app.secret_key = SECRET_KEY or os.urandom(32).hex()

# Initialize and seed database on startup
init_db()
seed_data()

# Rate limiting storage: 20 messages per minute per session_id
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 20
rate_limit_tracker: dict[str, deque] = defaultdict(deque)


def is_rate_limited(session_id: str) -> bool:
    """
    Checks if a given session_id has exceeded the rate limit of
    20 messages per minute.
    """
    now = time.time()
    timestamps = rate_limit_tracker[session_id]

    # Evict timestamps older than the sliding window
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        return True

    timestamps.append(now)
    return False


def admin_required(f):
    """Decorator to require admin session login for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
# Admin Routes (Protected by ADMIN_PASSWORD & Session)
# ---------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    Login page for library administration.
    Authenticates using ADMIN_PASSWORD from .env and establishes a session.
    """
    if request.method == "POST":
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            flash("ADMIN_PASSWORD is not configured in the environment (.env).", "error")
            return render_template("admin_login.html"), 401

        entered_password = request.form.get("password", "")
        if entered_password == admin_password:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin password. Please try again.", "error")
            return render_template("admin_login.html"), 401

    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    """Logs out the administrator and clears session."""
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin", methods=["GET"])
@admin_required
def admin_dashboard():
    """
    Main admin dashboard: lists all catalog books and all reservations.
    Protected by admin session authentication.
    """
    books = get_all_books()
    reservations = get_all_reservations()
    return render_template("admin.html", books=books, reservations=reservations)


@app.route("/admin/books/add", methods=["POST"])
@admin_required
def admin_add_book():
    """
    Adds a new book to the catalog.
    Accepts form submission or JSON payload.
    """
    data = request.get_json(silent=True) if request.is_json else request.form
    title = data.get("title", "")
    author = data.get("author", "")
    category = data.get("category", "")
    isbn = data.get("isbn", "")
    total_copies = data.get("total_copies", 1)
    available_copies = data.get("available_copies", 1)

    result = add_book(title, author, category, isbn, total_copies, available_copies)

    if request.is_json:
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    if "error" in result:
        flash(result["error"], "error")
    else:
        flash(result["message"], "success")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/books/<int:book_id>/edit", methods=["POST"])
@admin_required
def admin_edit_book(book_id: int):
    """
    Updates book details in the catalog.
    Accepts form submission or JSON payload.
    """
    data = request.get_json(silent=True) if request.is_json else request.form
    title = data.get("title", "")
    author = data.get("author", "")
    category = data.get("category", "")
    isbn = data.get("isbn", "")
    total_copies = data.get("total_copies", 1)
    available_copies = data.get("available_copies", 1)

    result = update_book(book_id, title, author, category, isbn, total_copies, available_copies)

    if request.is_json:
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    if "error" in result:
        flash(result["error"], "error")
    else:
        flash(result["message"], "success")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def admin_delete_book(book_id: int):
    """
    Deletes a book from the catalog if it has no active reservations.
    Accepts form submission or JSON payload.
    """
    result = delete_book(book_id)

    if request.is_json:
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    if "error" in result:
        flash(result["error"], "error")
    else:
        flash(result["message"], "success")

    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------
# Visitor Routes (Open, No Login Required)
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Renders the library main page."""
    return render_template("index.html")


@app.route("/api/books", methods=["GET"])
def get_books():
    """
    Search books with query string `q`.
    If `q` is empty or omitted, returns all books.
    """
    try:
        query = request.args.get("q", "").strip()
        if query:
            books = search_books(query)
        else:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, title, author, category, isbn, total_copies, available_copies
                    FROM books
                    ORDER BY id ASC;
                    """
                )
                rows = cursor.fetchall()
                books = [dict(row) for row in rows]

        return jsonify(books), 200
    except Exception as exc:
        logger.exception(f"Error in get_books: {exc}")
        return jsonify({"error": "Failed to retrieve books."}), 500


@app.route("/api/books/<int:book_id>", methods=["GET"])
def get_book(book_id: int):
    """Returns details and availability for a specific book."""
    try:
        result = check_availability(book_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result), 200
    except Exception as exc:
        logger.exception(f"Error in get_book({book_id}): {exc}")
        return jsonify({"error": "Failed to check book availability."}), 500


@app.route("/api/reserve", methods=["POST"])
def reserve():
    """
    Accepts JSON body: {"book_id": int, "name": str, "email": str}
    (supports "member_email" as fallback for "email")
    and creates a reservation, returning status 400 on error.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            logger.warning("Invalid JSON payload in /api/reserve")
            return jsonify({"error": "Invalid or missing JSON payload."}), 400

        book_id = data.get("book_id")
        name = data.get("name")
        email = data.get("email") or data.get("member_email")

        if book_id is None or name is None or email is None:
            return (
                jsonify({"error": "Fields 'book_id', 'name', and 'email' are required."}),
                400,
            )

        try:
            book_id_int = int(book_id)
        except (ValueError, TypeError):
            return jsonify({"error": "'book_id' must be an integer."}), 400

        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "'name' must be a non-empty string."}), 400

        if not isinstance(email, str) or not email.strip():
            return jsonify({"error": "'email' must be a non-empty string."}), 400

        result = reserve_book(book_id_int, name.strip(), email.strip())
        if "error" in result:
            return jsonify(result), 400

        return jsonify(result), 200
    except Exception as exc:
        logger.exception(f"Error in /api/reserve: {exc}")
        return jsonify({"error": "Failed to reserve book."}), 500


@app.route("/api/reservations", methods=["GET"])
def get_member_reservations():
    """
    Returns active reservations for a given email query parameter.
    (also accepts 'member_email' query param as fallback)
    """
    try:
        email = (request.args.get("email") or request.args.get("member_email", "")).strip()
        if not email:
            return jsonify({"error": "'email' query parameter is required."}), 400

        reservations = my_reservations(email)
        return jsonify(reservations), 200
    except Exception as exc:
        logger.exception(f"Error in get_member_reservations: {exc}")
        return jsonify({"error": "Failed to fetch reservations."}), 500


@app.route("/api/reservations/cancel", methods=["POST"])
def cancel_member_reservation():
    """
    Accepts JSON body: {"reservation_id": int, "email": str}
    (supports "member_email" as fallback for "email")
    Cancels an active reservation and restores book availability.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"error": "Invalid or missing JSON payload."}), 400

        reservation_id = data.get("reservation_id")
        email = data.get("email") or data.get("member_email")

        if reservation_id is None or email is None:
            return (
                jsonify({"error": "Both 'reservation_id' and 'email' are required."}),
                400,
            )

        try:
            reservation_id_int = int(reservation_id)
        except (ValueError, TypeError):
            return jsonify({"error": "'reservation_id' must be an integer."}), 400

        if not isinstance(email, str) or not email.strip():
            return jsonify({"error": "'email' must be a valid email string."}), 400

        result = cancel_reservation(reservation_id_int, email.strip())
        if "error" in result:
            return jsonify(result), 400

        return jsonify(result), 200
    except Exception as exc:
        logger.exception(f"Error in cancel_member_reservation: {exc}")
        return jsonify({"error": "Failed to cancel reservation."}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Accepts JSON body: {"session_id": str, "message": str}
    Validates input (non-empty, max 500 characters), enforces rate limit
    of 20 messages per minute per session_id, and returns {"reply": str}.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            logger.warning("Rejected /api/chat: Invalid or missing JSON body.")
            return jsonify({"error": "Invalid or missing JSON payload."}), 400

        session_id = data.get("session_id")
        message = data.get("message")

        # 1. Validate session_id
        if not isinstance(session_id, str) or not session_id.strip():
            logger.warning("Rejected /api/chat: Missing or empty 'session_id'.")
            return jsonify({"error": "'session_id' is required."}), 400
        clean_session_id = session_id.strip()

        # 2. Validate message type and strip whitespace
        if not isinstance(message, str):
            logger.warning("Rejected /api/chat: 'message' must be a string.")
            return jsonify({"error": "'message' must be a string."}), 400

        clean_message = message.strip()

        # 3. Reject empty message
        if not clean_message:
            logger.warning("Rejected /api/chat: Empty message received.")
            return jsonify({"error": "Message cannot be empty."}), 400

        # 4. Limit message length to 500 characters
        if len(clean_message) > 500:
            logger.warning(
                f"Rejected /api/chat: Message length {len(clean_message)} exceeds 500 limit."
            )
            return (
                jsonify(
                    {
                        "error": "Message exceeds the maximum allowed length of 500 characters."
                    }
                ),
                400,
            )

        # 5. Enforce rate limit (20 messages per minute per session_id)
        if is_rate_limited(clean_session_id):
            logger.warning(
                f"Rate limit exceeded for session_id '{clean_session_id}' (limit: 20 msgs/min)."
            )
            return (
                jsonify(
                    {
                        "error": "Rate limit exceeded. You can only send up to 20 messages per minute."
                    }
                ),
                429,
            )

        # 6. Call the bot assistant
        reply = ask_bot(clean_session_id, clean_message)
        return jsonify({"reply": reply}), 200

    except Exception as exc:
        logger.exception(f"Unhandled error in /api/chat: {exc}")
        return (
            jsonify(
                {"error": "An internal error occurred while processing your request."}
            ),
            500,
        )


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors with JSON response for API or fallback."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found."}), 404
    return "<h1>404 Not Found</h1>", 404


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors without leaking stack traces."""
    logger.exception(f"Internal server error: {error}")
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error."}), 500
    return "<h1>500 Internal Server Error</h1>", 500


@app.errorhandler(Exception)
def unhandled_exception(error):
    """Catch-all for unexpected exceptions to ensure no stack traces are shown."""
    logger.exception(f"Unhandled exception occurred: {error}")
    if request.path.startswith("/api/"):
        return jsonify({"error": "An unexpected error occurred."}), 500
    return "<h1>An unexpected error occurred</h1>", 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
