import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response
from history import HistoryStore
from parser import analyze_reports
from report_builder import build_dashboard_html

BASE = Path(__file__).resolve().parent
DB = os.getenv("DATABASE_PATH", str(BASE / "data" / "gct_report_parser.db"))
MAX_FILE = int(os.getenv("MAX_FILE_SIZE_MB", "500")) * 1024 * 1024
MAX_REQUEST = int(os.getenv("MAX_REQUEST_SIZE_MB", "1024")) * 1024 * 1024

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST
history = HistoryStore(DB)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/feedback")
def feedback_form():
    return render_template("feedback.html")


@app.post("/api/feedback")
def submit_feedback():
    payload = request.get_json(silent=True) or request.form
    name = str(payload.get("name", "")).strip()[:120]
    email = str(payload.get("email", "")).strip()[:254]
    category = str(payload.get("category", "General feedback")).strip()[:80]
    subject = str(payload.get("subject", "")).strip()[:160]
    message = str(payload.get("message", "")).strip()[:10000]

    if not message:
        return jsonify({"error": "Please enter your feedback before submitting."}), 400
    if email and ("\n" in email or "\r" in email or "@" not in email):
        return jsonify({"error": "Enter a valid email address or leave it blank."}), 400

    # Persist feedback in the same host-mounted SQLite database used by the app.
    # This does not require an SMTP server or expose administrator email addresses.
    try:
        with sqlite3.connect(DB, timeout=10) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submitted_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    reply_email TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'NEW'
                )
            """)
            connection.execute("""
                INSERT INTO user_feedback
                    (submitted_at, name, reply_email, category, subject, message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                name, email, category, subject, message
            ))
    except sqlite3.Error:
        app.logger.exception("Could not store user feedback")
        return jsonify({"error": "We couldn't save your feedback right now. Please try again later."}), 500

    return jsonify({
        "message": "Thank you! Your feedback has been saved for the app administrator."
    }), 200


@app.get("/healthz")
def healthz():
    """Lightweight readiness probe for deployment and periodic monitoring."""
    try:
        with history.conn() as connection:
            connection.execute("SELECT 1").fetchone()
        return jsonify({"status": "healthy", "database": "ok"}), 200
    except Exception:
        app.logger.exception("health check failed")
        return jsonify({"status": "unhealthy", "database": "error"}), 503


@app.get("/api/dashboard")
def dashboard():
    return jsonify({
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "buildFingerprint": "Not detected",
        "securityPatch": "Not detected",
        "androidVersion": "Not detected",
        "fingerprints": [],
        "builds": [],
        "uploadedFiles": 0,
        "xmlReportsFound": 0,
        "recognizedReports": 0,
        "reportDiagnostics": [],
        "overall": {
            "totalTests": 0,
            "passed": 0,
            "failed": 0,
            "assumptionFailures": 0,
            "ignored": 0,
            "warnings": 0,
            "blocked": 0,
            "fingerprintMismatch": False,
            "multipleBuilds": False,
            "buildIdentityIncomplete": False,
        },
        "suites": [],
        "incompleteModules": [],
        "failures": [],
    })


@app.get("/api/history")
def history_list():
    return jsonify({"maxRuns": history.MAX_RUNS, "runs": history.list_runs()})


@app.get("/api/history/<run_id>")
def history_run(run_id):
    data = history.get_run(run_id)
    return (jsonify(data), 200) if data else (
        jsonify({"error": "Historical run not found."}), 404
    )


@app.post("/api/analyze")
def analyze():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Upload at least one report ZIP file."}), 400

    paths = []
    try:
        for uploaded in files:
            if not uploaded.filename:
                continue
            if Path(uploaded.filename).suffix.lower() != ".zip":
                return jsonify({
                    "error": f"Only ZIP files are supported: {uploaded.filename}"
                }), 400

            fd, temp_path = tempfile.mkstemp(prefix="gct-report-", suffix=".zip")
            os.close(fd)
            uploaded.save(temp_path)

            if os.path.getsize(temp_path) > MAX_FILE:
                return jsonify({
                    "error": (
                        f"{uploaded.filename} exceeds the "
                        f"{MAX_FILE // 1048576} MB file limit."
                    )
                }), 413

            paths.append((uploaded.filename, temp_path))

        if not paths:
            return jsonify({"error": "Upload at least one report ZIP file."}), 400

        data = analyze_reports(paths)
        history.save(data)
        return jsonify(data)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("analysis failed")
        return jsonify({"error": f"Analysis failed: {exc}"}), 500
    finally:
        for _, temp_path in paths:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.post("/api/publish")
def publish():
    dashboard_data = request.get_json(silent=True)
    if not isinstance(dashboard_data, dict):
        return jsonify({"error": "Dashboard data is required."}), 400

    html = build_dashboard_html(dashboard_data)
    return Response(
        html.encode("utf-8"),
        mimetype="text/html",
        headers={
            "Content-Disposition": (
                "attachment; filename=gct-certification-dashboard.html"
            ),
            "Cache-Control": "no-store",
        },
    )


@app.errorhandler(413)
def too_large(_):
    return jsonify({
        "error": "Upload is too large. The total request limit is 1 GB."
    }), 413


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )
