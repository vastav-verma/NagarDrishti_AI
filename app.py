from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "civicsense_secret"

UPLOAD_FOLDER = "static/uploads"
if not os.path.isdir(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect("civic.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    con = db()
    cur = con.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    # Complaints table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        issue TEXT,
        address TEXT,
        image TEXT,
        status TEXT,
        severity TEXT
    )
    """)

    # Ensure admin account exists
    admin = cur.execute("SELECT * FROM users WHERE email='admin@gov.in'").fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (email, password, role) VALUES (?,?,?)",
            ("admin@gov.in", generate_password_hash("admin"), "government")
        )

    con.commit()
    con.close()

init_db()

# ---------------- AI / SEVERITY ----------------
def predict_severity(issue_text):
    high_keywords = ["pothole", "water leak", "electricity", "flood", "accident", "broken pipe"]
    moderate_keywords = ["garbage", "street light", "tree branch", "litter", "bench"]

    text = issue_text.lower()
    for word in high_keywords:
        if word in text: return "High"
    for word in moderate_keywords:
        if word in text: return "Moderate"
    return "Low"

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")

# ---------------- AUTH ----------------
@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["role"]

    con = db()
    user = con.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role)).fetchone()
    con.close()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["role"] = role
        return redirect("/citizen/report" if role == "citizen" else "/government/complaints")

    return "Invalid email or password"

@app.route("/register", methods=["POST"])
def register():
    email = request.form["email"]
    password = generate_password_hash(request.form["password"])
    try:
        con = db()
        con.execute("INSERT INTO users (email,password,role) VALUES (?,?,?)", (email, password, "citizen"))
        con.commit()
        con.close()
        return redirect("/")
    except:
        return "User already exists"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- CITIZEN ----------------
@app.route("/citizen/report", methods=["GET", "POST"])
def report():
    if session.get("role") != "citizen": return redirect("/")

    if request.method == "POST":
        issue = request.form["issue"]
        address = request.form["address"]
        image = request.files["image"]
        other_issue = request.form.get("other_issue")
        
        issue_text = other_issue if issue == "Other" and other_issue else issue
        severity = predict_severity(issue_text)

        filename = image.filename
        image.save(os.path.join(UPLOAD_FOLDER, filename))

        con = db()
        con.execute("""
            INSERT INTO complaints (user_id, issue, address, image, status, severity)
            VALUES (?,?,?,?,?,?)
        """, (session["user_id"], issue_text, address, filename, "Reported", severity))
        con.commit()
        con.close()
        return redirect("/citizen/status")

    return render_template("citizen/report.html")

@app.route("/citizen/status")
def status():
    if session.get("role") != "citizen": return redirect("/")
    con = db()
    complaints = con.execute("SELECT * FROM complaints WHERE user_id=?", (session["user_id"],)).fetchall()
    con.close()
    return render_template("citizen/status.html", complaints=complaints)

# ---------------- GOVERNMENT ----------------
@app.route("/government/complaints")
def gov_complaints():
    if session.get("role") != "government": return redirect("/")
    con = db()
    complaints = con.execute("""
        SELECT * FROM complaints ORDER BY 
        CASE severity WHEN 'High' THEN 1 WHEN 'Moderate' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END
    """).fetchall()
    con.close()
    return render_template("government/complaints.html", complaints=complaints)

@app.route("/resolve/<int:id>")
def resolve(id):
    if session.get("role") != "government": return redirect("/")
    con = db()
    con.execute("UPDATE complaints SET status='Resolved' WHERE id=?", (id,))
    con.commit()
    con.close()
    return redirect("/government/complaints")

# !!! UPDATED ANALYTICS ROUTE !!!
@app.route("/government/analytics")
def analytics():
    if session.get("role") != "government":
        return redirect("/")
    
    con = db()
    # We fetch ALL complaints so the JavaScript in the template can 
    # count them and build the charts dynamically.
    complaints = con.execute("SELECT * FROM complaints").fetchall()
    con.close()
    
    return render_template("government/analytics.html", complaints=complaints)

if __name__ == "__main__":
    app.run(debug=True)