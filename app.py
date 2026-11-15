import os, re, uuid, random, threading, requests, joblib, numpy as np
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature
import simulate

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")
app = Flask(__name__, static_folder=DIST, static_url_path=""); CORS(app)
ser = URLSafeTimedSerializer(os.getenv("SECRET_KEY", "dev-secret-change-me"))
NODE_KEY = os.getenv("NODE_KEY", "node-secret-123")
now = lambda: (datetime.utcnow() + timedelta(hours=2)).strftime("%H:%M:%S")  # CAT (UTC+2)

# ---------- Storage: MongoDB Atlas if MONGO_URI set, otherwise in-memory ----------
MONGO_URI = os.getenv("MONGO_URI")
if MONGO_URI:
    from pymongo import MongoClient
    db = MongoClient(MONGO_URI)["faultdb"]
    def save(col, doc): db[col].insert_one(dict(doc))
    def fetch(col, flt=None, limit=30): return list(db[col].find(flt or {}, {"_id": 0}).sort("ts", -1).limit(limit))
    def update(col, id_, fields): db[col].update_one({"id": id_}, {"$set": fields})
else:
    store = {"readings": [], "alerts": [], "reports": [], "tickets": [], "sms": []}
    def save(col, doc): store[col].insert(0, dict(doc))
    def fetch(col, flt=None, limit=30):
        return [d for d in store[col] if all(d.get(k) == v for k, v in (flt or {}).items())][:limit]
    def update(col, id_, fields):
        for d in store[col]:
            if d.get("id") == id_: d.update(fields)

# ---------- Users and auth ----------
ROLES = ["administrator", "safety_officer", "resident"]
if MONGO_URI:
    db.users.create_index("username", unique=True)
    def user_get(n): return db.users.find_one({"username": n}, {"_id": 0})
    def user_put(n, pw, role): db.users.update_one({"username": n}, {"$set": {"pw": pw, "role": role}}, upsert=True)
    def user_del(n): db.users.delete_one({"username": n})
    def user_list(): return list(db.users.find({}, {"_id": 0, "pw": 0}))
else:
    USERS = {}
    def user_get(n): return USERS.get(n)
    def user_put(n, pw, role): USERS[n] = {"username": n, "pw": pw, "role": role}
    def user_del(n): USERS.pop(n, None)
    def user_list(): return [{"username": k, "role": v["role"]} for k, v in USERS.items()]

# Starter accounts. Passwords come from environment variables in production; the defaults are for local testing only.
STARTERS = [("admin", "ADMIN_PASSWORD", "admin123", "administrator"), ("officer", "OFFICER_PASSWORD", "officer123", "safety_officer"),
            ("resident", "RESIDENT_PASSWORD", "resident123", "resident")]
for name, env, default, role in STARTERS:
    if os.getenv(env): user_put(name, generate_password_hash(os.environ[env]), role)   # env value always wins
    elif not user_get(name): user_put(name, generate_password_hash(default), role)
if MONGO_URI and not all(os.getenv(k) for k in ("SECRET_KEY", "ADMIN_PASSWORD", "OFFICER_PASSWORD", "RESIDENT_PASSWORD")):
    print("WARNING: set SECRET_KEY, ADMIN_PASSWORD, OFFICER_PASSWORD and RESIDENT_PASSWORD before exposing this app publicly.")

def require(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            try: data = ser.loads(token, max_age=8 * 3600)
            except BadSignature: return jsonify(error="Please log in again"), 401
            if roles and data["role"] not in roles: return jsonify(error="Not allowed for your role"), 403
            request.user = data
            return f(*a, **kw)
        return wrapper
    return deco

@app.post("/api/login")
def api_login():
    d = request.json or {}
    u = user_get(d.get("username", "").strip().lower())
    if not u or not check_password_hash(u["pw"], d.get("password", "")):
        return jsonify(error="Invalid username or password"), 401
    uname = d["username"].strip().lower()
    return jsonify(token=ser.dumps({"username": uname, "role": u["role"]}), username=uname, role=u["role"])

@app.post("/api/register")  # residents self-register
def api_register():
    d = request.json or {}
    uname, pw = d.get("username", "").strip().lower(), d.get("password", "")
    if len(uname) < 3 or len(pw) < 6: return jsonify(error="Username 3+ chars, password 6+ chars"), 400
    if user_get(uname): return jsonify(error="Username already taken"), 409
    user_put(uname, generate_password_hash(pw), "resident")
    return jsonify(ok=True), 201

@app.get("/api/users")
@require("administrator")
def api_users(): return jsonify(user_list())

@app.post("/api/users")
@require("administrator")
def api_create_user():
    d = request.json or {}
    uname, pw, role = d.get("username", "").strip().lower(), d.get("password", ""), d.get("role")
    if len(uname) < 3 or len(pw) < 6 or role not in ROLES: return jsonify(error="Invalid details"), 400
    if user_get(uname): return jsonify(error="Username already taken"), 409
    user_put(uname, generate_password_hash(pw), role)
    return jsonify(ok=True), 201

# ---------- Model ----------
le = joblib.load("labels.joblib"); winner = joblib.load("winner.joblib")
if winner == "rf":
    model = joblib.load("model_rf.joblib")
    predict = lambda x: model.predict(x)[0]
else:
    import tensorflow as tf
    model = tf.keras.models.load_model("model_nn.keras"); sc = joblib.load("scaler.joblib")
    predict = lambda x: model.predict(sc.transform(x), verbose=0).argmax(1)[0]

# ---------- SMS (Africa's Talking: AT_USERNAME=sandbox for testing, your app username for live) ----------
AT_USER, AT_KEY, ALERT_PHONE = os.getenv("AT_USERNAME"), os.getenv("AT_API_KEY"), os.getenv("ALERT_PHONE")
AT_BASE = os.getenv("AT_BASE_URL") or ("https://api.sandbox.africastalking.com" if AT_USER == "sandbox" else "https://api.africastalking.com")

def clean_phone(p):
    p = re.sub(r"[\s\-()]", "", str(p or ""))
    if re.fullmatch(r"0\d{9}", p): p = "+260" + p[1:]          # 0971234567 -> +260971234567
    elif re.fullmatch(r"260\d{9}", p): p = "+" + p
    return p if re.fullmatch(r"\+\d{10,15}", p) else None

def _deliver(number, text):
    result = "stub (no gateway keys set)"
    if AT_USER and AT_KEY:
        try:
            r = requests.post(AT_BASE + "/version1/messaging", headers={"apiKey": AT_KEY, "Accept": "application/json"},
                              data={"username": AT_USER, "to": number, "message": text[:300]}, timeout=10)
            result = f"HTTP {r.status_code}"
            try: result += ": " + r.json()["SMSMessageData"]["Recipients"][0]["status"]
            except Exception: pass
        except Exception as e: result = "failed: " + str(e)[:80]
    ts = datetime.utcnow().timestamp()
    save("sms", {"id": uuid.uuid4().hex[:8], "to": number, "text": text, "result": result, "ts": ts, "time": stamp(ts)})
    print(f"[SMS -> {number}] {text} ({result})")

def send_sms(number, text):  # runs in a thread so a slow gateway never delays the API
    if number: threading.Thread(target=_deliver, args=(number, text), daemon=True).start()

def notify_staff(text): send_sms(clean_phone(ALERT_PHONE), text)

FAULTS = ["short_circuit", "earth_fault", "overload", "open_circuit"]
ZONES = ["Kanyama", "Matero"]
STATUSES = ["new", "dispatched", "in_progress", "resolved"]
stamp = lambda ts: (datetime.utcfromtimestamp(ts) + timedelta(hours=2)).strftime("%d %b, %H:%M")

def new_ticket(fault, zone, house, desc, source, reporter=None, node_id=None, ts=None):
    ts = ts or datetime.utcnow().timestamp()
    return dict(id="FT-" + uuid.uuid4().hex[:6].upper(), fault=fault, zone=zone, house=house, description=desc, source=source,
                reporter=reporter, node_id=node_id, status="new", created=stamp(ts), ts=ts, resolved_ts=None, assignee=None, notes=[])

def open_ticket(doc):
    if doc["fault"] not in FAULTS: return
    live = fetch("tickets", {"node_id": doc["node_id"], "fault": doc["fault"]}, limit=50)
    if any(t["status"] != "resolved" for t in live): return
    zone = "Matero" if "matero" in doc["node_id"].lower() else "Kanyama"
    save("tickets", new_ticket(doc["fault"], zone, "", f"Detected by sensor node {doc['node_id']}", "sensor", node_id=doc["node_id"]))
    notify_staff(f"ALERT {doc['fault'].replace('_', ' ').upper()} detected at {doc['node_id']} ({zone})")  # one SMS per new ticket, not per reading

def classify_and_store(node_id, v, i, leak, pf):
    label = le.inverse_transform([predict(np.array([[v, i, leak, pf]]))])[0]
    doc = dict(node_id=node_id, voltage=round(v, 1), current=round(i, 2), leakage_ma=round(leak, 1),
               power_factor=round(pf, 2), fault=label, time=now(), ts=datetime.utcnow().timestamp())
    save("readings", doc)
    if label != "normal":
        save("alerts", {**doc, "id": uuid.uuid4().hex[:8], "status": "open"})
        open_ticket(doc)
    return doc

# ---------- Data endpoints ----------
@app.post("/api/predict")  # sensor nodes authenticate with an API key
def api_predict():
    if request.headers.get("X-Node-Key") != NODE_KEY: return jsonify(error="Invalid node key"), 401
    d = request.get_json(silent=True) or {}
    try:
        vals = [float(d[k]) for k in ("voltage", "current", "leakage_ma", "power_factor")]
        node_id = str(d["node_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="node_id, voltage, current, leakage_ma and power_factor are required"), 400
    return jsonify(classify_and_store(node_id, *vals))

@app.get("/api/simulate/<node_id>")
@require("administrator", "safety_officer")
def api_simulate(node_id):
    forced = request.args.get("fault")  # staff can inject a fault on purpose to test the pipeline
    label = forced if forced in simulate.CLASSES else np.random.choice(simulate.CLASSES, p=[0.95, 0.012, 0.012, 0.016, 0.01])
    return jsonify(classify_and_store(node_id, *simulate.sample(label)))

@app.get("/api/readings")
@require("administrator", "safety_officer")
def api_readings(): return jsonify(fetch("readings"))

@app.get("/api/alerts")
@require("administrator", "safety_officer")
def api_alerts(): return jsonify(fetch("alerts"))

@app.post("/api/alerts/<alert_id>/ack")
@require("administrator", "safety_officer")
def api_ack(alert_id):
    update("alerts", alert_id, {"status": "acknowledged", "by": request.user["username"]})
    return jsonify(ok=True)

@app.post("/api/reports")
@require("administrator", "safety_officer", "resident")
def api_reports():
    d = request.get_json(silent=True) or {}
    loc, desc = str(d.get("location", "")).strip(), str(d.get("description", "")).strip()
    if not loc or not desc: return jsonify(error="Location and description are required"), 400
    if len(loc) > 100 or len(desc) > 500: return jsonify(error="Location max 100, description max 500 characters"), 400
    doc = dict(id=uuid.uuid4().hex[:8], username=request.user["username"], location=loc,
               type=str(d.get("type", "")), description=desc, status="submitted",
               time=now(), ts=datetime.utcnow().timestamp())
    save("reports", doc)
    return jsonify(ok=True), 201

@app.get("/api/reports")
@require("administrator", "safety_officer", "resident")
def api_get_reports():
    if request.user["role"] == "resident":
        return jsonify(fetch("reports", {"username": request.user["username"]}))
    return jsonify(fetch("reports"))

# ---------- Fault tickets (triage board, resident wizard, analytics) ----------
@app.get("/api/tickets")
@require("administrator", "safety_officer", "resident")
def api_tickets():
    if request.user["role"] == "resident":
        return jsonify(fetch("tickets", {"reporter": request.user["username"]}, limit=200))
    return jsonify(fetch("tickets", limit=500))

@app.post("/api/tickets")
@require("administrator", "safety_officer", "resident")
def api_new_ticket():
    d = request.get_json(silent=True) or {}
    fault, zone = d.get("fault"), d.get("zone")
    house, desc = str(d.get("house", "")).strip(), str(d.get("description", "")).strip()
    if fault not in FAULTS or zone not in ZONES: return jsonify(error="Choose a fault type and a zone"), 400
    if not house or len(house) > 20 or len(desc) > 500: return jsonify(error="House number required (max 20 chars); description max 500"), 400
    raw = str(d.get("phone", "")).strip(); phone = clean_phone(raw) if raw else None
    if raw and not phone: return jsonify(error="Enter a valid phone number, e.g. 0971234567"), 400
    t = new_ticket(fault, zone, house, desc, "resident", reporter=request.user["username"]); t["phone"] = phone; save("tickets", t)
    if phone: send_sms(phone, f"Fault report {t['id']} received. We will update you by SMS.")
    if fault in ("short_circuit", "earth_fault"): notify_staff(f"New {fault.replace('_', ' ')} report: {zone}, house {house} ({t['id']})")
    return jsonify(t), 201

@app.post("/api/tickets/<tid>/status")
@require("administrator", "safety_officer")
def api_ticket_status(tid):
    d = request.get_json(silent=True) or {}
    t = next(iter(fetch("tickets", {"id": tid}, limit=1)), None)
    if not t: return jsonify(error="Ticket not found"), 404
    f = {}
    if d.get("status"):
        if d["status"] not in STATUSES: return jsonify(error="Invalid status"), 400
        f["status"] = d["status"]; f["resolved_ts"] = datetime.utcnow().timestamp() if d["status"] == "resolved" else None
    if d.get("assign"): f["assignee"] = request.user["username"]
    note = str(d.get("note", "")).strip()[:300]
    if note: f["notes"] = (t.get("notes") or []) + [dict(by=request.user["username"], text=note, time=now())]
    update("tickets", tid, f)
    if d.get("status") in ("dispatched", "resolved") and t.get("phone"):
        send_sms(t["phone"], f"Ticket {tid}: " + ("a field officer has been dispatched to you." if d["status"] == "dispatched" else "your fault is marked resolved. Stay safe."))
    return jsonify(ok=True)

@app.get("/api/analytics")
@require("administrator")
def api_analytics():
    ts = fetch("tickets", limit=5000); done = [t for t in ts if t.get("resolved_ts")]
    by = {k: {z: 0 for z in ZONES} for k in FAULTS}
    for t in ts:
        if t["fault"] in by and t["zone"] in by[t["fault"]]: by[t["fault"]][t["zone"]] += 1
    mins = [(t["resolved_ts"] - t["ts"]) / 60 for t in done]
    return jsonify(total=len(ts), open=sum(t["status"] != "resolved" for t in ts),
                   critical_active=sum(t["status"] != "resolved" and t["fault"] in ("short_circuit", "earth_fault") for t in ts),
                   avg_resolution_min=round(sum(mins) / len(mins)) if mins else None, by_type=by,
                   by_status={s: sum(t["status"] == s for t in ts) for s in STATUSES})

@app.get("/api/sms")
@require("administrator")
def api_sms(): return jsonify(fetch("sms", limit=100))

@app.delete("/api/users/<uname>")
@require("administrator")
def api_delete_user(uname):
    uname = uname.lower()
    if not user_get(uname) or uname in ("admin", "officer", "resident") or uname == request.user["username"]:
        return jsonify(error="This account cannot be removed"), 400
    user_del(uname); return jsonify(ok=True)

# ---------- React front end (built into web/dist) ----------
@app.get("/")
def home(): return send_from_directory(DIST, "index.html")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=False)
