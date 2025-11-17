import os
from flask import Flask, request, render_template_string, abort
import sqlite3
import secrets
import smtplib

DB_PATH = "votes.db"
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")


app = Flask(__name__)

# ---------- DB helpers ----------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            voter_id INTEGER NOT NULL,
            player_3 INTEGER NOT NULL,
            player_2 INTEGER NOT NULL,
            player_1 INTEGER NOT NULL,
            UNIQUE(match_id, voter_id),
            FOREIGN KEY(match_id) REFERENCES matches(id),
            FOREIGN KEY(voter_id) REFERENCES voters(id)
        )
    """)
    conn.commit()
    conn.close()

# ---------- Email sending ----------

def send_vote_emails(match_id):
    """
    Send each voter an email with their unique voting link for this match.
    For now, if email isn't configured, it will just print the emails.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, token FROM voters")
    voters = cur.fetchall()
    cur.execute("SELECT name FROM matches WHERE id = ?", (match_id,))
    match = cur.fetchone()
    conn.close()

    if not match:
        raise ValueError("Match not found")

    subject = f"Vote 3-2-1 for {match['name']}"

    for v in voters:
        link = f"{BASE_URL}/vote/{match_id}?token={v['token']}"
        body = (
            f"Hi {v['name']},\n\n"
            f"Please submit your 3-2-1 votes for {match['name']} at this link:\n{link}\n\n"
            "Thanks!"
        )
        send_email(v["email"], subject, body)

def send_email(to_email, subject, body):
    """
    If email credentials are set as environment variables, send via Gmail.
    Otherwise, just print the email to the terminal.
    """
    from_email = os.environ.get("VOTE_APP_EMAIL")
    password = os.environ.get("VOTE_APP_EMAIL_PASS")

    if not from_email or not password:
        print("---- EMAIL (not actually sent) ----")
        print("To:", to_email)
        print("Subject:", subject)
        print(body)
        print("-----------------------------------")
        return

    msg = f"From: {from_email}\r\nTo: {to_email}\r\nSubject: {subject}\r\n\r\n{body}"

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, [to_email], msg)

# ---------- HTML templates ----------

VOTE_FORM_TEMPLATE = """
<!doctype html>
<title>3-2-1 Voting</title>
<h1>3-2-1 Voting for {{ match_name }}</h1>
<p>Hi {{ voter_name }}, please choose three different players.</p>
{% if error %}
<p style="color:red;">{{ error }}</p>
{% endif %}
<form method="post">
  <label>3 votes:</label>
  <select name="player_3" required>
    <option value="">-- choose --</option>
    {% for p in players %}
      <option value="{{ p.id }}">{{ p.name }}</option>
    {% endfor %}
  </select><br><br>

  <label>2 votes:</label>
  <select name="player_2" required>
    <option value="">-- choose --</option>
    {% for p in players %}
      <option value="{{ p.id }}">{{ p.name }}</option>
    {% endfor %}
  </select><br><br>

  <label>1 vote:</label>
  <select name="player_1" required>
    <option value="">-- choose --</option>
    {% for p in players %}
      <option value="{{ p.id }}">{{ p.name }}</option>
    {% endfor %}
  </select><br><br>

  <button type="submit">Submit</button>
</form>
"""

RESULTS_TEMPLATE = """
<!doctype html>
<title>Results</title>
<h1>Results for {{ match_name }}</h1>
<table border="1" cellpadding="5">
  <tr><th>Player</th><th>Points</th></tr>
  {% for row in results %}
    <tr>
      <td>{{ row.name }}</td>
      <td>{{ row.points }}</td>
    </tr>
  {% endfor %}
</table>
"""

# ---------- Routes ----------

@app.route("/")
def index():
    return "Hello, the voting app is running!"

@app.route("/vote/<int:match_id>", methods=["GET", "POST"])
def vote(match_id):
    token = request.args.get("token")

    # If no token at all, show clear message
    if not token:
        return """
        <h1>Missing token</h1>
        <p>This link is missing the <code>?token=...</code> part.</p>
        """, 400

    conn = get_db()
    cur = conn.cursor()

    # Get all voters + tokens so we can show them if needed
    cur.execute("SELECT id, name, email, token FROM voters")
    voters = cur.fetchall()

    # Try to find the voter for this token
    cur.execute("SELECT id, name FROM voters WHERE token = ?", (token,))
    voter = cur.fetchone()

    # If token not found, show a debug page instead of 403
    if not voter:
        conn.close()
        html = ["<h1>Invalid token</h1>"]
        html.append(f"<p>Incoming token from URL: <code>{token}</code></p>")
        html.append("<p>This token does not match any voter in the database.</p>")
        html.append("<h2>Voters in database:</h2><ul>")
        for v in voters:
            html.append(
                f"<li>id={v['id']}, name={v['name']}, email={v['email']}, token={v['token']}</li>"
            )
        html.append("</ul>")
        return "\n".join(html), 403

    # Ensure match exists
    cur.execute("SELECT name FROM matches WHERE id = ?", (match_id,))
    match = cur.fetchone()
    if not match:
        conn.close()
        return f"<h1>Match {match_id} not found</h1>", 404

    # Check if already voted
    cur.execute(
        "SELECT 1 FROM votes WHERE match_id = ? AND voter_id = ?",
        (match_id, voter["id"])
    )
    if cur.fetchone():
        conn.close()
        return "<h1>You have already voted for this match. Thank you!</h1>"

    # Load players
    cur.execute("SELECT id, name FROM players ORDER BY name")
    players = cur.fetchall()

    error = None

    if request.method == "POST":
        try:
            p3 = int(request.form["player_3"])
            p2 = int(request.form["player_2"])
            p1 = int(request.form["player_1"])
        except (KeyError, ValueError):
            error = "Invalid selection."
        else:
            if len({p3, p2, p1}) != 3:
                error = "You must choose three different players."
            else:
                cur.execute("""
                    INSERT INTO votes (match_id, voter_id, player_3, player_2, player_1)
                    VALUES (?, ?, ?, ?, ?)
                """, (match_id, voter["id"], p3, p2, p1))
                conn.commit()
                conn.close()
                return "<h1>Thanks, your vote has been recorded!</h1>"

    conn.close()
    return render_template_string(
        VOTE_FORM_TEMPLATE,
        match_name=match["name"],
        voter_name=voter["name"],
        players=players,
        error=error
    )


@app.route("/results/<int:match_id>")
def results(match_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT name FROM matches WHERE id = ?", (match_id,))
    match = cur.fetchone()
    if not match:
        conn.close()
        abort(404)

    cur.execute("SELECT id, name FROM players")
    players = cur.fetchall()
    player_map = {p["id"]: p["name"] for p in players}

    cur.execute("""
        SELECT player_3, player_2, player_1
        FROM votes
        WHERE match_id = ?
    """, (match_id,))
    votes = cur.fetchall()
    conn.close()

    points = {pid: 0 for pid in player_map.keys()}
    for v in votes:
        points[v["player_3"]] += 3
        points[v["player_2"]] += 2
        points[v["player_1"]] += 1

    results_list = [
        {"name": player_map[pid], "points": pts}
        for pid, pts in points.items()
        if pts > 0
    ]
    results_list.sort(key=lambda r: r["points"], reverse=True)

    return render_template_string(
        RESULTS_TEMPLATE,
        match_name=match["name"],
        results=results_list
    )

@app.route("/debug_tokens")
def debug_tokens():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, token FROM voters")
    rows = cur.fetchall()
    conn.close()

    html = ["<h1>Voters and tokens</h1>", "<ul>"]
    for r in rows:
        html.append(
            f"<li>id={r['id']}, name={r['name']}, email={r['email']}, token={r['token']}</li>"
        )
    html.append("</ul>")
    return "\n".join(html)

# ---------- Helper functions (used by setup.py) ----------

def add_player(name):
    conn = get_db()
    conn.execute("INSERT INTO players (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def add_voter(name, email):
    token = secrets.token_urlsafe(16)
    conn = get_db()
    conn.execute(
        "INSERT INTO voters (name, email, token) VALUES (?, ?, ?)",
        (name, email, token)
    )
    conn.commit()
    conn.close()

def add_match(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO matches (name) VALUES (?)", (name,))
    conn.commit()
    match_id = cur.lastrowid
    conn.close()
    return match_id

from flask import Response  # add to your existing imports if not already

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    # Very simple auth: ?key=SECRET
    admin_key = os.environ.get("ADMIN_KEY")
    key = request.args.get("key")
    if not admin_key or key != admin_key:
        return "Forbidden", 403

    if request.method == "GET":
        # Show a simple form
        return """
        <h1>Admin Setup</h1>
        <p>Paste CSV data with columns: Player,Email (header required)</p>
        <form method="post">
          <label>Round name:</label><br>
          <input type="text" name="round_name" size="40" required><br><br>
          <label>CSV data:</label><br>
          <textarea name="csv" rows="15" cols="80" placeholder="Player,Email&#10;John Smith,john@example.com"></textarea><br><br>
          <button type="submit">Set up round</button>
        </form>
        """

    # POST: process form
    round_name = request.form.get("round_name", "").strip()
    csv_text = request.form.get("csv", "").strip()

    if not round_name or not csv_text:
        return "Round name and CSV are required", 400

    import io
    import pandas as pd

    # Read CSV from the textarea
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        return f"Error reading CSV: {e}", 400

    # Basic validation
    if "Player" not in df.columns or "Email" not in df.columns:
        return "CSV must have columns 'Player' and 'Email' in the header row.", 400

    # Clean up
    df["Player"] = df["Player"].astype(str).str.strip()
    df["Email"] = df["Email"].astype(str).str.strip()

    # Init DB and add data
    init_db()

    missing_emails = []
    for _, row in df.iterrows():
        name = row["Player"]
        email = row["Email"]

        if not name:
            continue

        add_player(name)

        if email:
            add_voter(name, email)
        else:
            missing_emails.append(name)

    # Create match and send emails
    match_id = add_match(round_name)
    send_vote_emails(match_id)

    # Summary response (only for you, no emails or tokens shown)
    lines = [f"Setup done for round: {round_name!r}", f"Match id: {match_id}"]
    if missing_emails:
        lines.append("Players with missing email (NOT added as voters):")
        lines.extend(f"- {name}" for name in missing_emails)

    return Response("<br>".join(lines), mimetype="text/html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
