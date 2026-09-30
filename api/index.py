"""
ARCHET SOLUTIONS - Flask Backend Server
Serves the public website and the internal workspace by hostname.
"""

from flask import Flask, send_from_directory, request, jsonify, redirect
import os
from dotenv import load_dotenv
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from html import escape

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

try:
    from api.supabase_store import db, StoreError
    from api.portal import register_portal, portal_host, INTERNAL_HOST, rate_limit, client_address, PortalError
except ModuleNotFoundError:
    from supabase_store import db, StoreError
    from portal import register_portal, portal_host, INTERNAL_HOST, rate_limit, client_address, PortalError

EMAIL_FROM = os.getenv("EMAIL_FROM", "mahee123.aamir@gmail.com")
EMAIL_TO = os.getenv("EMAIL_TO", EMAIL_FROM)
EMAIL_APP_PWD = os.getenv("EMAIL_APP_PWD", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SITE_URL = os.getenv("SITE_URL", "https://archetsolutions.com").rstrip("/")
LOGO_URL = os.getenv("LOGO_URL", f"{SITE_URL}/archet-logo-dark.png")


def send_email(to_email, subject, html):
    if not EMAIL_FROM or not EMAIL_APP_PWD:
        raise RuntimeError("Email credentials are not configured.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Archet Solutions <{EMAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as srv:
        srv.login(EMAIL_FROM, EMAIL_APP_PWD)
        srv.sendmail(EMAIL_FROM, to_email, msg.as_string())


def send_confirmation_email(to_email, to_name, company):
    safe_name = escape(to_name)
    safe_company = escape(company)
    safe_email = escape(to_email)
    safe_logo_url = escape(LOGO_URL, quote=True)
    first_name = escape((to_name.split() or ["there"])[0])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<style>
  body{{margin:0;padding:0;background:#f1f3f4;font-family:'Google Sans',Roboto,Arial,sans-serif}}
  .wrap{{max-width:600px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.08)}}
  .header{{background:#030309;padding:22px 36px}}
  .email-logo{{display:block;width:176px;max-width:100%;height:auto;border:0}}
  .body{{padding:36px 36px 28px}}
  .greeting{{font-size:20px;font-weight:500;color:#202124;margin-bottom:6px}}
  .intro{{font-size:14px;color:#5f6368;line-height:1.6;margin-bottom:24px}}
  .card{{background:#f8f9fa;border:1px solid #e8eaed;border-radius:8px;padding:20px 24px;margin-bottom:24px}}
  .card-title{{font-size:11px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:#80868b;margin-bottom:12px}}
  .card-row{{display:flex;gap:8px;margin-bottom:6px;font-size:13px}}
  .card-label{{color:#80868b;min-width:90px;flex-shrink:0}}
  .card-val{{color:#202124;font-weight:500}}
  .divider{{height:1px;background:#e8eaed;margin:20px 0}}
  .next-steps{{font-size:14px;color:#5f6368;line-height:1.7;margin-bottom:24px}}
  .next-steps strong{{color:#202124}}
  .badge{{display:inline-block;background:#e8f5e9;color:#137333;font-size:12px;font-weight:600;padding:4px 12px;border-radius:100px;margin-bottom:20px}}
  .cta-block{{text-align:center;margin:8px 0 24px}}
  .cta{{display:inline-block;background:#030309;color:#0FFFD4;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:-.1px}}
  .footer{{background:#f8f9fa;border-top:1px solid #e8eaed;padding:20px 36px;font-size:12px;color:#80868b;text-align:center;line-height:1.6}}
  .footer a{{color:#1a73e8;text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <img src="{safe_logo_url}" width="176" height="119" alt="Archet Solutions" class="email-logo"/>
  </div>
  <div class="body">
    <div class="badge">&#10003; Request Received</div>
    <div class="greeting">Hi {first_name},</div>
    <p class="intro">
      Thank you for reaching out to Archet Solutions. We've received your quote request for <strong>{safe_company}</strong> and an Archet strategist will be in touch within <strong>one business day</strong> with a tailored proposal.
    </p>

    <div class="card">
      <div class="card-title">Your submission summary</div>
      <div class="card-row"><span class="card-label">Name</span><span class="card-val">{safe_name}</span></div>
      <div class="card-row"><span class="card-label">Company</span><span class="card-val">{safe_company}</span></div>
      <div class="card-row"><span class="card-label">Email</span><span class="card-val">{safe_email}</span></div>
    </div>

    <div class="next-steps">
      <strong>What happens next?</strong><br/>
      Our team reviews every request personally. You'll hear from a dedicated Archet strategist who will walk you through how we can deploy the full operations stack for your locations — no templates, no guesswork.
    </div>

    <div class="divider"></div>

    <p style="font-size:13px;color:#5f6368;margin-bottom:6px">Have an urgent need? Reach us directly:</p>
    <p style="font-size:13px;color:#202124;margin-bottom:4px">&#128222; <strong>+1 (469) 993-7957</strong></p>
    <p style="font-size:13px;color:#202124;margin-bottom:20px">&#9993; <a href="mailto:mahee123.aamir@gmail.com" style="color:#1a73e8;text-decoration:none">mahee123.aamir@gmail.com</a></p>

    <div class="cta-block">
      <a href="https://archetsolutions.com" class="cta">Visit Archet Solutions &rarr;</a>
    </div>
  </div>
  <div class="footer">
    &copy; {datetime.now(timezone.utc).year} Archet Solutions &nbsp;&middot;&nbsp; 20727 Stone Oak Pkwy, San Antonio, TX 78258<br/>
    <span style="color:#bdc1c6">You're receiving this because you submitted a quote request at archetsolutions.com.</span>
  </div>
</div>
</body>
</html>"""

    try:
        send_email(to_email, "We received your quote request - Archet Solutions", html)
    except Exception as exc:
        print(f"[email] Failed to send confirmation to {to_email}: {exc}")

def send_lead_notification(record):
    safe_logo_url = escape(LOGO_URL, quote=True)
    rows = "".join(
        f"""
        <tr>
          <td style="padding:8px 12px;color:#5f6368;border-bottom:1px solid #e8eaed">{escape(label)}</td>
          <td style="padding:8px 12px;color:#202124;border-bottom:1px solid #e8eaed;font-weight:600">{escape(value or "-")}</td>
        </tr>
        """
        for label, value in [
            ("Received", record["received_at"]),
            ("Name", record["full_name"]),
            ("Company", record["company"]),
            ("Email", record["email"]),
            ("Phone", record["phone"]),
            ("Industry / Brand", record["brand"]),
            ("Locations", record["stores"]),
            ("Message", record["message"]),
        ]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:24px;background:#f1f3f4;font-family:Arial,sans-serif">
  <div style="max-width:680px;margin:auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e8eaed">
    <div style="background:#030309;color:#fff;padding:20px 24px">
      <img src="{safe_logo_url}" width="170" height="115" alt="Archet Solutions" style="display:block;width:170px;max-width:100%;height:auto;border:0;margin-bottom:12px"/>
      <div style="font-size:18px;font-weight:700">New Archet quote request</div>
      <div style="font-size:12px;color:#9aa0a6;margin-top:4px">Submitted from archetsolutions.com</div>
    </div>
    <div style="padding:20px 24px">
      <table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>
    </div>
  </div>
</body>
</html>"""

    subject = f"New quote request: {record['company']} - {record['full_name']}"
    send_email(EMAIL_TO, subject, html)


# Resolve the absolute path of the directory this file lives in.
# Go up one level from api/ to reach the frontend files.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Disable Flask's default template_folder and static_folder so it does
# NOT look for a /templates or /static directory at all.
app = Flask(
    __name__,
    static_folder=None,
    template_folder=None,
)
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
register_portal(app)

try:
    from api.sales import register_sales, connect as sales_connect
    from api.calling_tree import register_calling_tree
    from api.quota import register_quota
    from api.invoices import register_invoices
except ModuleNotFoundError:
    from sales import register_sales, connect as sales_connect
    from calling_tree import register_calling_tree
    from quota import register_quota
    from invoices import register_invoices
register_sales(app)
register_calling_tree(app,lambda: sales_connect())
register_quota(app)
register_invoices(app)


@app.get('/assets/<filename>')
def portal_assets(filename):
    if filename not in ('sales.js', 'sales.css', 'calling-tree.js', 'workspace.js', 'workspace.css', 'quota.js', 'quota.css', 'rest.js', 'rest.css', 'rest-image-1.png', 'rest-image-2.png', 'rest-image-3.png', 'invoices.js', 'invoices.css'):
        return '', 404
    return send_from_directory(os.path.join(BASE_DIR, 'assets'), filename)

# ---------------------------------------------------------------------------
# Route: Serve the appropriate homepage directly from the project root.
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    """
    Safely serves the frontend from BASE_DIR using send_from_directory,
    which guards against path traversal attacks.
    """
    filename = "index.html" if request.host.split(":")[0].lower() == INTERNAL_HOST else "public.html"
    return send_from_directory(BASE_DIR, filename)


@app.get("/internal")
@app.get("/internal/")
def internal():
    if not portal_host():
        return redirect("https://" + INTERNAL_HOST, code=302)
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/robots.txt")
def robots():
    if request.host.split(":")[0].lower() == INTERNAL_HOST:
        return app.response_class("User-agent: *\nDisallow: /\n", mimetype="text/plain")
    return send_from_directory(BASE_DIR, "robots.txt")


@app.get("/sitemap.xml")
def sitemap():
    return send_from_directory(BASE_DIR, "sitemap.xml")


@app.route("/archet-logo.png", methods=["GET"])
def logo():
    return send_from_directory(BASE_DIR, "archet-logo.png")


@app.route("/archet-logo-dark.png", methods=["GET"])
def dark_logo():
    return send_from_directory(BASE_DIR, "archet-logo-dark.png")


# ---------------------------------------------------------------------------
# Route: Lead capture endpoint for the B2B quote form.
# ---------------------------------------------------------------------------
@app.route("/api/quote", methods=["POST"])
def submit_quote():
    """
    Accepts JSON or form-encoded data from the website's quote form.
    Persists the lead in Supabase before attempting email notifications.
    """
    # Accept both JSON payloads (fetch) and standard form posts.
    payload = request.get_json(silent=True) or request.form.to_dict()

    if not isinstance(payload, dict):
        raise PortalError("Invalid quote request.")
    limits = {"full_name": 100, "company": 200, "email": 254, "phone": 50,
              "brand": 100, "stores": 100, "message": 10000}
    for field, limit in limits.items():
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value) > limit:
            raise PortalError("Invalid " + field.replace("_", " ") + ".")

    required_fields = ["full_name", "company", "email", "brand"]
    missing = [f for f in required_fields if not payload.get(f, "").strip()]
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}"
        }), 400

    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", payload["email"].strip()):
        raise PortalError("Please enter a valid email address.")
    rate_limit("quote-ip", client_address(), limit=10, seconds=900)

    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "full_name": payload.get("full_name", "").strip(),
        "company":   payload.get("company", "").strip(),
        "email":     payload.get("email", "").strip(),
        "phone":     payload.get("phone", "").strip(),
        "brand":     payload.get("brand", "").strip(),
        "stores":    payload.get("stores", "").strip(),
        "message":   payload.get("message", "").strip(),
    }

    saved = db("quote_requests", "POST", record)[0]
    notification_status = "sent"
    try:
        send_lead_notification(record)
    except Exception:
        notification_status = "failed"
        app.logger.warning("Quote saved, but email notification failed")
    try:
        db("quote_requests", "PATCH", {"notification_status": notification_status}, id="eq." + saved["id"])
    except StoreError:
        app.logger.warning("Quote saved, but notification status could not be updated")
    send_confirmation_email(record["email"], record["full_name"], record["company"])

    return jsonify({
        "status": "success",
        "message": "Thank you. An Archet strategist will reach out within one business day."
    }), 200


# ---------------------------------------------------------------------------
# Health check (handy for uptime monitors / load balancers).
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "archet-solutions"}), 200


# ---------------------------------------------------------------------------
# Block any attempt to fetch other arbitrary files from the root directory.
# Only explicitly registered routes are exposed.
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_):
    return jsonify({"status": "error", "message": "Not found"}), 404


if __name__ == "__main__":
    # debug=False is recommended for production; flip to True while developing.
    app.run(host="0.0.0.0", port=5000, debug=False)
