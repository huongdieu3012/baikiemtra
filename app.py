import os
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sach.db")

app = Flask(__name__)
app.secret_key = "quan-ly-sach-secret"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            year INTEGER,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        """
    )
    if db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO categories(name, description) VALUES (?, ?)",
            [
                ("Công nghệ thông tin", "Lập trình, mạng, cơ sở dữ liệu"),
                ("Văn học", "Tiểu thuyết, truyện ngắn, thơ"),
                ("Kinh tế", "Quản trị, tài chính, marketing"),
            ],
        )
        db.executemany(
            "INSERT INTO books(title, author, price, quantity, year, category_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Lập trình Python cơ bản", "Nguyễn Văn A", 120000, 15, 2022, 1),
                ("Cơ sở dữ liệu SQLite", "Trần Thị B", 95000, 8, 2021, 1),
                ("Dế Mèn phiêu lưu ký", "Tô Hoài", 60000, 30, 2019, 2),
                ("Quản trị kinh doanh", "Lê Văn C", 150000, 5, 2020, 3),
            ],
        )
    db.commit()
    db.close()


def to_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@app.template_filter("money")
def money(v):
    return f"{int(v or 0):,}".replace(",", ".") + " đ"


@app.route("/")
def dashboard():
    db = get_db()
    total_categories = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    total_books = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    total_quantity = db.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM books"
    ).fetchone()[0]
    total_value = db.execute(
        "SELECT COALESCE(SUM(price * quantity), 0) FROM books"
    ).fetchone()[0]
    per_category = db.execute(
        """
        SELECT c.id, c.name, COUNT(b.id) AS book_count,
               COALESCE(SUM(b.quantity), 0) AS qty,
               COALESCE(SUM(b.price * b.quantity), 0) AS value
        FROM categories c LEFT JOIN books b ON b.category_id = c.id
        GROUP BY c.id ORDER BY book_count DESC, c.name
        """
    ).fetchall()
    max_count = max([r["book_count"] for r in per_category] or [1]) or 1
    recent = db.execute(
        """
        SELECT b.*, c.name AS category_name FROM books b
        JOIN categories c ON c.id = b.category_id
        ORDER BY b.id DESC LIMIT 5
        """
    ).fetchall()
    low_stock = db.execute(
        """
        SELECT b.*, c.name AS category_name FROM books b
        JOIN categories c ON c.id = b.category_id
        WHERE b.quantity <= 5 ORDER BY b.quantity, b.title LIMIT 5
        """
    ).fetchall()
    return render_template(
        "dashboard.html",
        total_categories=total_categories,
        total_books=total_books,
        total_quantity=total_quantity,
        total_value=total_value,
        per_category=per_category,
        max_count=max_count,
        recent=recent,
        low_stock=low_stock,
    )


@app.route("/categories")
def categories():
    rows = get_db().execute(
        """
        SELECT c.*, COUNT(b.id) AS book_count
        FROM categories c LEFT JOIN books b ON b.category_id = c.id
        GROUP BY c.id ORDER BY c.name
        """
    ).fetchall()
    return render_template("categories.html", categories=rows)


@app.route("/categories/add", methods=["GET", "POST"])
def category_add():
    form = {"name": "", "description": ""}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        error = validate_category(form)
        if error:
            flash(error, "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO categories(name, description) VALUES (?, ?)",
                (form["name"], form["description"]),
            )
            db.commit()
            flash("Đã thêm danh mục.", "success")
            return redirect(url_for("categories"))
    return render_template("category_form.html", form=form, editing=False)


@app.route("/categories/<int:cid>/edit", methods=["GET", "POST"])
def category_edit(cid):
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    if row is None:
        flash("Không tìm thấy danh mục.", "error")
        return redirect(url_for("categories"))
    form = {"name": row["name"], "description": row["description"] or ""}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        error = validate_category(form, cid)
        if error:
            flash(error, "error")
        else:
            db.execute(
                "UPDATE categories SET name = ?, description = ? WHERE id = ?",
                (form["name"], form["description"], cid),
            )
            db.commit()
            flash("Đã cập nhật danh mục.", "success")
            return redirect(url_for("categories"))
    return render_template("category_form.html", form=form, editing=True)


@app.route("/categories/<int:cid>/delete", methods=["POST"])
def category_delete(cid):
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM books WHERE category_id = ?", (cid,)
    ).fetchone()[0]
    if count > 0:
        flash(f"Không thể xóa: danh mục còn {count} cuốn sách. Hãy xóa sách trước.", "error")
    else:
        db.execute("DELETE FROM categories WHERE id = ?", (cid,))
        db.commit()
        flash("Đã xóa danh mục.", "success")
    return redirect(url_for("categories"))


def validate_category(form, cid=None):
    if not form["name"]:
        return "Vui lòng nhập tên danh mục."
    row = get_db().execute(
        "SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (form["name"],)
    ).fetchone()
    if row is not None and row["id"] != cid:
        return "Tên danh mục đã tồn tại."
    return None


@app.route("/books")
def books():
    db = get_db()
    category_id = to_int(request.args.get("category"))
    q = request.args.get("q", "").strip()
    sql = (
        "SELECT b.*, c.name AS category_name FROM books b "
        "JOIN categories c ON c.id = b.category_id WHERE 1=1"
    )
    params = []
    if category_id:
        sql += " AND b.category_id = ?"
        params.append(category_id)
    if q:
        sql += " AND (b.title LIKE ? OR b.author LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY c.name, b.title"
    rows = db.execute(sql, params).fetchall()
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template(
        "books.html", books=rows, categories=cats, category_id=category_id, q=q
    )


def read_book_form():
    return {
        "title": request.form.get("title", "").strip(),
        "author": request.form.get("author", "").strip(),
        "price": request.form.get("price", "").strip(),
        "quantity": request.form.get("quantity", "").strip(),
        "year": request.form.get("year", "").strip(),
        "category_id": request.form.get("category_id", "").strip(),
    }


def validate_book(form):
    if not form["title"]:
        return "Vui lòng nhập tên sách."
    if not form["author"]:
        return "Vui lòng nhập tác giả."
    price = to_int(form["price"])
    if price is None or price < 0:
        return "Giá phải là số nguyên không âm."
    qty = to_int(form["quantity"])
    if qty is None or qty < 0:
        return "Số lượng phải là số nguyên không âm."
    if form["year"]:
        year = to_int(form["year"])
        if year is None or year < 1000 or year > 2100:
            return "Năm xuất bản không hợp lệ."
    cid = to_int(form["category_id"])
    if cid is None or get_db().execute(
        "SELECT 1 FROM categories WHERE id = ?", (cid,)
    ).fetchone() is None:
        return "Vui lòng chọn danh mục hợp lệ."
    return None


@app.route("/books/add", methods=["GET", "POST"])
def book_add():
    db = get_db()
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if not cats:
        flash("Hãy tạo danh mục trước khi thêm sách.", "error")
        return redirect(url_for("category_add"))
    form = {
        "title": "", "author": "", "price": "", "quantity": "", "year": "",
        "category_id": request.args.get("category", ""),
    }
    if request.method == "POST":
        form = read_book_form()
        error = validate_book(form)
        if error:
            flash(error, "error")
        else:
            db.execute(
                "INSERT INTO books(title, author, price, quantity, year, category_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    form["title"], form["author"], to_int(form["price"]),
                    to_int(form["quantity"]), to_int(form["year"]),
                    to_int(form["category_id"]),
                ),
            )
            db.commit()
            flash("Đã thêm sách.", "success")
            return redirect(url_for("books", category=to_int(form["category_id"])))
    return render_template("book_form.html", form=form, categories=cats, editing=False)


@app.route("/books/<int:bid>/edit", methods=["GET", "POST"])
def book_edit(bid):
    db = get_db()
    row = db.execute("SELECT * FROM books WHERE id = ?", (bid,)).fetchone()
    if row is None:
        flash("Không tìm thấy sách.", "error")
        return redirect(url_for("books"))
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    form = {
        "title": row["title"], "author": row["author"],
        "price": row["price"], "quantity": row["quantity"],
        "year": row["year"] or "", "category_id": row["category_id"],
    }
    if request.method == "POST":
        form = read_book_form()
        error = validate_book(form)
        if error:
            flash(error, "error")
        else:
            db.execute(
                "UPDATE books SET title=?, author=?, price=?, quantity=?, year=?,"
                " category_id=? WHERE id=?",
                (
                    form["title"], form["author"], to_int(form["price"]),
                    to_int(form["quantity"]), to_int(form["year"]),
                    to_int(form["category_id"]), bid,
                ),
            )
            db.commit()
            flash("Đã cập nhật sách.", "success")
            return redirect(url_for("books", category=to_int(form["category_id"])))
    return render_template("book_form.html", form=form, categories=cats, editing=True)


@app.route("/books/<int:bid>/delete", methods=["POST"])
def book_delete(bid):
    db = get_db()
    row = db.execute("SELECT category_id FROM books WHERE id = ?", (bid,)).fetchone()
    db.execute("DELETE FROM books WHERE id = ?", (bid,))
    db.commit()
    flash("Đã xóa sách.", "success")
    return redirect(url_for("books", category=row["category_id"] if row else None))


init_db()

if __name__ == "__main__":
    app.run(debug=True)