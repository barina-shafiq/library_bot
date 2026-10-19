# 📚 Library-Bot

An intelligent, full-stack library management assistant powered by Flask, SQLite, and Google Gemini API with automated function calling.

Library-Bot enables users to explore the library catalog, check real-time copy availability, reserve books, and manage their reservations through a modern, responsive web chat interface or directly via a terminal CLI.

---

## ✨ Features

- **Conversational Library Assistant**: Powered by Google's Gemini models with tool calling to interact directly with the catalog database.
- **Smart Catalog Search**: Case-insensitive substring search matching across book titles, authors, and categories.
- **Live Inventory & Availability**: Checks total copies vs. available copies before allowing reservations.
- **Reservation Lifecycle Management**: Members can reserve books and cancel active reservations, automatically updating inventory.
- **Multi-Turn Session Memory**: Contextual conversation memory preserved per session and cached in `sessionStorage` across page reloads.
- **Rate Limiting & Input Validation**: Enforces a 500-character limit, whitespace stripping, empty-message rejection, and a 20-message-per-minute rate limiter per session.
- **Resilient Model Fallback**: Supports automatic fallback across Gemini models if a specific tier or preview model experiences quota limits or deprecation.
- **Zero Stack Trace Leaks**: Secure error handling with all internal exceptions and warnings logged to `app.log`.
- **Modern Responsive Web UI**: Clean soft-blue and white card interface featuring typing indicators, quick-reply chips, and markdown formatting.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.13+, [Flask](https://flask.palletsprojects.com/)
- **Database**: SQLite3 (Python built-in `sqlite3` module with parameter binding)
- **AI / LLM**: [Google GenAI SDK](https://github.com/googleapis/python-genai) (`google-genai`), Gemini API
- **Frontend**: HTML5, Vanilla CSS3 (modern flexbox & animations), Vanilla JavaScript (ES6+ `fetch` and `sessionStorage`)
- **Environment Management**: `python-dotenv`

---

## 📁 Project Structure

```text
Library-Bot/
├── .env.example          # Environment variable template
├── .gitignore            # Git exclusion rules
├── app.log               # Application error and access logs
├── app.py                # Flask application, REST API routes, and rate limiting
├── bot.py                # Gemini client setup, function calling tools, and chat sessions
├── database.py           # SQLite connection, schema definition, CSV seeding, and query functions
├── books.csv             # Initial catalog seed dataset (30 books)
├── novels_comics.csv     # Novels & comics catalog dataset (30 books)
├── members.csv           # Initial member seed dataset
├── library.db            # SQLite database file (generated automatically)
├── requirements.txt      # Python dependencies
├── Procfile              # Render process definition (gunicorn)
├── render.yaml           # Render blueprint deployment specification
├── LICENSE               # MIT License
├── static/
│   ├── chat.js           # Client-side chat logic, session handling, and quick replies
│   └── style.css         # Responsive styling, message bubbles, and typing animations
└── templates/
    ├── admin.html        # Admin dashboard for inventory & reservations
    ├── admin_login.html  # Admin login authentication template
    └── index.html        # Main chat interface HTML template
```

---

## 🤖 Bot Tools (Function Calling)

The Gemini assistant is equipped with the following custom tools defined in `database.py`:

| Tool Function | Description | Parameters |
| :--- | :--- | :--- |
| `search_books` | Searches up to 10 matching books by title, author, or category. | `query: str` |
| `check_availability` | Returns the total copies, available copies, and availability status of a book. | `book_id: int` |
| `reserve_book` | Reserves a book for anyone by name and email (no registration needed). Enforces 3-reservation limit. | `book_id: int, name: str, email: str` |
| `my_reservations` | Lists all active reservations and corresponding book titles for an email address. | `member_email: str` |
| `cancel_reservation` | Cancels an active reservation belonging to that email and restores 1 copy to inventory. | `reservation_id: int, member_email: str` |

---

## 🚀 Setup & Installation

### 1. Clone the repository and navigate into the folder:
```bash
git clone https://github.com/barina-shafiq/library_bot.git
cd library_bot
```

### 2. Create and activate a virtual environment:

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install required dependencies:
```bash
pip install -r requirements.txt
```

### 4. Configure your environment variables:
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and set your valid Google Gemini API Key:
```ini
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 5. Initialize the database:
Populate `library.db` with sample books and members from CSV files:
```bash
python database.py
```

---

## 💻 Running the Application

### Web Application (Flask)
Start the local development server:
```bash
python app.py
```
Open your browser and visit:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

### Terminal CLI Bot
You can also converse with the bot directly from your terminal:
```bash
python bot.py
```

---

## ☁️ Deploy to Render

1. Log in to **[Render](https://render.com/)** and link your GitHub account.
2. Click **New +** -> **Blueprint** (or **Web Service**).
3. Select your repository: `barina-shafiq/library_bot`.
4. Render will automatically detect `render.yaml` (or use `buildCommand: pip install -r requirements.txt` and `startCommand: gunicorn app:app --workers 1 --threads 4 --timeout 120`).
5. In the **Environment Variables** section on Render, add:
   - `GEMINI_API_KEY`: *Your Google Gemini API Key*
   - `ADMIN_PASSWORD`: *Your custom admin dashboard password*
   - `SECRET_KEY`: *(Auto-generated or a 32-character random string)*
6. Click **Deploy Web Service**. Your app will be live with a free `onrender.com` URL!

---

## 🌐 API Reference

| Endpoint | Method | Payload / Query | Description |
| :--- | :--- | :--- | :--- |
| `/` | `GET` | - | Renders the web chat interface. |
| `/api/books` | `GET` | `?q=<search_query>` | Returns matching books (or all books if `q` is omitted). |
| `/api/books/<id>` | `GET` | - | Retrieves details and copy count for a book by ID. |
| `/api/reserve` | `POST` | `{"book_id": int, "name": str, "email": str}` | Reserves a book for anyone without prior registration. |
| `/api/reservations` | `GET` | `?email=<email>` | Retrieves active reservations for an email. |
| `/api/reservations/cancel` | `POST` | `{"reservation_id": int, "email": str}` | Cancels an active reservation and restocks the copy. |
| `/api/chat` | `POST` | `{"session_id": str, "message": str}` | Sends a message to the AI assistant with tool calling. |

---

## 📝 License
This project is open-source and available under the [MIT License](LICENSE).
