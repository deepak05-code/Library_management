import os
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "library_secret_key"
app.config['TEMPLATES_AUTO_RELOAD'] = True
DB_NAME = "library.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                isbn TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'Available'
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                joined_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                issue_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                return_date TEXT,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );
        """)

@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    conn = get_db()
    base_sql = """
        SELECT b.*, c.name AS borrower_name, t.id AS active_tx_id, t.due_date
        FROM books b
        LEFT JOIN transactions t ON b.id = t.book_id AND t.return_date IS NULL
        LEFT JOIN customers c ON t.customer_id = c.id
    """
    if query:
        books = conn.execute(
            base_sql + " WHERE b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ? ORDER BY b.id DESC",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        books = conn.execute(base_sql + " ORDER BY b.id DESC").fetchall()
    conn.close()
    return render_template("index.html", books=books, query=query)

@app.route("/add", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        isbn = request.form.get("isbn", "").strip()
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO books (title, author, isbn) VALUES (?, ?, ?)", (title, author, isbn))
            flash(f'"{title}" added successfully!', "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("A book with this ISBN already exists.", "warning")
    return render_template("add_book.html")

@app.route("/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    conn = get_db()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        isbn = request.form.get("isbn", "").strip()
        try:
            conn.execute("UPDATE books SET title = ?, author = ?, isbn = ? WHERE id = ?", (title, author, isbn, book_id))
            conn.commit()
            flash("Book updated!", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("Another book already uses that ISBN.", "warning")
        finally:
            conn.close()
    conn.close()
    return render_template("edit_book.html", book=book)

@app.route("/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    with get_db() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    flash("Book deleted.", "secondary")
    return redirect(url_for("index"))

@app.route("/customers")
def customers():
    query = request.args.get("q", "").strip()
    conn = get_db()
    base_sql = """
        SELECT c.*, COUNT(t.id) AS active_books
        FROM customers c
        LEFT JOIN transactions t ON c.id = t.customer_id AND t.return_date IS NULL
    """
    if query:
        customer_list = conn.execute(
            base_sql + " WHERE c.name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? GROUP BY c.id ORDER BY c.id DESC",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        customer_list = conn.execute(base_sql + " GROUP BY c.id ORDER BY c.id DESC").fetchall()
    conn.close()
    return render_template("customers.html", customers=customer_list, query=query)

@app.route("/customers/add", methods=["GET", "POST"])
def add_customer():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        joined_date = datetime.now().strftime("%Y-%m-%d")
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO customers (name, email, phone, joined_date) VALUES (?, ?, ?, ?)",
                    (name, email, phone, joined_date),
                )
            flash(f"Customer {name} registered!", "success")
            return redirect(url_for("customers"))
        except sqlite3.IntegrityError:
            flash("A customer with this email already exists.", "warning")
    return render_template("add_customer.html")

@app.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
def edit_customer(customer_id):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        try:
            conn.execute("UPDATE customers SET name = ?, email = ?, phone = ? WHERE id = ?", (name, email, phone, customer_id))
            conn.commit()
            flash("Customer details updated!", "success")
            return redirect(url_for("customers"))
        except sqlite3.IntegrityError:
            flash("Another customer already uses that email.", "warning")
        finally:
            conn.close()
    conn.close()
    return render_template("edit_customer.html", customer=customer)

@app.route("/customers/delete/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    conn = get_db()
    active = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE customer_id = ? AND return_date IS NULL", (customer_id,)
    ).fetchone()[0]
    if active > 0:
        conn.close()
        flash("Cannot delete customer while they have unreturned books.", "danger")
        return redirect(url_for("customers"))
    conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()
    flash("Customer deleted.", "secondary")
    return redirect(url_for("customers"))

@app.route("/issue/<int:book_id>", methods=["GET", "POST"])
def issue_book(book_id):
    conn = get_db()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        days = int(request.form.get("days", 14))
        issue_date = datetime.now().strftime("%Y-%m-%d")
        due_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO transactions (book_id, customer_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
            (book_id, customer_id, issue_date, due_date),
        )
        conn.execute("UPDATE books SET status = 'Issued' WHERE id = ?", (book_id,))
        conn.commit()
        conn.close()
        flash(f'"{book["title"]}" issued! Due on {due_date}.', "success")
        return redirect(url_for("index"))
    customer_list = conn.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("issue_book.html", book=book, customers=customer_list)

@app.route("/return/<int:tx_id>", methods=["POST"])
def return_book(tx_id):
    conn = get_db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if tx and tx["return_date"] is None:
        return_date = datetime.now().strftime("%Y-%m-%d")
        conn.execute("UPDATE transactions SET return_date = ? WHERE id = ?", (return_date, tx_id))
        conn.execute("UPDATE books SET status = 'Available' WHERE id = ?", (tx["book_id"],))
        conn.commit()
        flash("Book returned!", "info")
    conn.close()
    return redirect(request.referrer or url_for("index"))

@app.route("/transactions")
def transactions():
    conn = get_db()
    records = conn.execute("""
        SELECT t.*, b.title AS book_title, b.isbn, c.name AS customer_name, c.phone
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        JOIN customers c ON t.customer_id = c.id
        ORDER BY t.id DESC
    """).fetchall()
    conn.close()
    return render_template("transactions.html", transactions=records)

if __name__ == '__main__':
    init_db()
    app.run(port=5005)
