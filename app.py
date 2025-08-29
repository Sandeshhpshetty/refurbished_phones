# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_cors import CORS
import mysql.connector
import os

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET", "supersecretkey")  # change in prod
CORS(app)

# ---------- MySQL Connection (edit credentials) ----------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",         # change to your MySQL user
    "password": "sand", # change to your MySQL password
    "database": "refurbished_db",
    "auth_plugin": "mysql_native_password"
}

def get_db_cursor():
    # Create a new connection per request to avoid stale connections
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    return conn, cur

# ---------- Routes: Login / Logout / Inventory pages ----------
@app.route("/", methods=["GET"])
def root():
    # If logged in, show inventory page; otherwise redirect to login
    if session.get("user"):
        return redirect(url_for("inventory"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn, cur = get_db_cursor()
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        conn.close()
        if user:
            session["user"] = username
            return redirect(url_for("inventory"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/inventory")
def inventory():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("index.html")

# ---------- API: Phones ----------
@app.route("/api/phones", methods=["GET"])
def api_get_phones():
    conn, cur = get_db_cursor()
    cur.execute("SELECT * FROM phones ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

@app.route("/api/past_products", methods=["GET"])
def api_get_past_products():
    conn, cur = get_db_cursor()
    cur.execute("SELECT * FROM past_products ORDER BY sold_out_date DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

@app.route("/api/phones", methods=["POST"])
def api_add_phone():
    data = request.get_json() or {}
    model = (data.get("model") or "").strip()
    try:
        base_cost = float(data.get("base_cost", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid base_cost"}), 400
    condition_type = (data.get("condition_type") or "").strip()
    try:
        stock = int(data.get("stock", 0))
    except (TypeError, ValueError):
        stock = 0

    # Validation
    if not model:
        return jsonify({"error": "Model is required"}), 400
    if base_cost <= 0:
        return jsonify({"error": "Base cost must be greater than 0"}), 400
    if stock < 0:
        return jsonify({"error": "Stock cannot be negative"}), 400

    conn, cur = get_db_cursor()
    cur.execute(
        "INSERT INTO phones (model, base_cost, condition_type, stock) VALUES (%s, %s, %s, %s)",
        (model, base_cost, condition_type, stock)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Phone added successfully"}), 201

@app.route("/api/phones/<int:phone_id>/sell", methods=["PUT"])
def api_sell_phone(phone_id):
    conn, cur = get_db_cursor()
    # Decrease stock by 1 if stock > 0
    cur.execute("UPDATE phones SET stock = stock - 1 WHERE id = %s AND stock > 0", (phone_id,))
    conn.commit()

    # Fetch updated row (might be None if row was deleted or never existed)
    cur.execute("SELECT * FROM phones WHERE id = %s", (phone_id,))
    phone = cur.fetchone()

    if phone is None:
        # Could be deleted already, or id invalid
        conn.close()
        return jsonify({"message": "Phone not found (or already moved)"}), 404

    # If stock reached 0, move to past_products and delete from phones
    if phone.get("stock") == 0:
        cur.execute(
            "INSERT INTO past_products (model, base_cost, condition_type) VALUES (%s, %s, %s)",
            (phone["model"], phone["base_cost"], phone["condition_type"])
        )
        conn.commit()
        cur.execute("DELETE FROM phones WHERE id = %s", (phone_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Phone sold out and moved to past products."})

    conn.close()
    return jsonify({"message": "One phone sold!"})

@app.route("/api/phones/<int:phone_id>/b2b", methods=["PUT"])
def api_toggle_b2b(phone_id):
    data = request.get_json() or {}
    sold_b2b = bool(data.get("sold_b2b", False))
    conn, cur = get_db_cursor()
    cur.execute("UPDATE phones SET sold_b2b = %s WHERE id = %s", (sold_b2b, phone_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "B2B status updated"})

# ---------- Run ----------
if __name__ == "__main__":
    # Ensure the app uses environment settings if provided
    app.run(host="0.0.0.0", debug=True)
