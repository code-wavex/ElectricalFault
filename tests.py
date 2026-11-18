"""Run: python tests.py   (needs model files: python train.py first). Writes test_results.csv"""
import time, uuid
import pandas as pd
from app import app as flask_app          # same code the dashboard is running

c = flask_app.test_client()
results = []
def check(tid, req, what, inp, expected, actual, ok):
    results.append(dict(ID=tid, Req=req, Test=what, Input=inp, Expected=expected,
                        Actual=actual, Result="PASS" if ok else "FAIL"))
def post(path, body=None, h=None): return c.post(path, json=body, headers=h or {})
def get(path, h=None): return c.get(path, headers=h or {})
def tok(u, p): return (post("/api/login", {"username": u, "password": p}).get_json() or {}).get("token", "")
H = lambda t: {"Authorization": "Bearer " + t}
NODE = {"X-Node-Key": "node-secret-123"}

# --- Authentication ---
r = post("/api/login", {"username": "admin", "password": "admin123"}); d = r.get_json()
check("T01","FR2","Login, valid credentials","admin/admin123","200, role administrator",f"{r.status_code}, {d.get('role')}",r.status_code==200 and d.get("role")=="administrator")
r = post("/api/login", {"username": "admin", "password": "wrong"})
check("T02","FR2","Login, wrong password","admin/wrong","401",r.status_code,r.status_code==401)
u1, u2 = "res_"+uuid.uuid4().hex[:6], "res_"+uuid.uuid4().hex[:6]
r = post("/api/register", {"username": u1, "password": "secret123"})
check("T03","FR1","Register new resident",f"{u1}/secret123","201",r.status_code,r.status_code==201)
post("/api/register", {"username": u2, "password": "secret123"})
r = post("/api/register", {"username": "admin", "password": "secret123"})
check("T04","FR1","Register existing username","admin","409",r.status_code,r.status_code==409)
r = post("/api/register", {"username": "ab", "password": "123"})
check("T05","FR1","Register too-short username/password","ab/123","400",r.status_code,r.status_code==400)

admin, off, r1, r2 = tok("admin","admin123"), tok("officer","officer123"), tok(u1,"secret123"), tok(u2,"secret123")

# --- Access control ---
r = get("/api/readings")
check("T06","FR3, NFR4","Staff endpoint, no token","GET /api/readings","401",r.status_code,r.status_code==401)
r = get("/api/readings", H("abc"))
check("T07","NFR4","Staff endpoint, invalid token","token 'abc'","401",r.status_code,r.status_code==401)
r = get("/api/alerts", H(r1))
check("T08","FR3","Resident calls staff endpoint","GET /api/alerts as resident","403",r.status_code,r.status_code==403)
r = post("/api/users", {"username":"x1y2z3","password":"secret123","role":"resident"}, H(r1))
check("T09","FR3, FR14","Resident tries to create user","POST /api/users as resident","403",r.status_code,r.status_code==403)

# --- Reports ---
r = post("/api/reports", {"location":"Kanyama, Block 4","type":"Sparking","description":"Sparks from pole"}, H(r1))
check("T10","FR12","Resident submits report","valid report","201",r.status_code,r.status_code==201)
own = [x for x in get("/api/reports", H(r2)).get_json() if x.get("username")==u1]
staff = [x for x in get("/api/reports", H(off)).get_json() if x.get("username")==u1]
check("T11","FR13","Residents see only own reports; staff see all","resident2 vs officer","resident2: 0 of resident1's; officer: ≥1",f"resident2: {len(own)}; officer: {len(staff)}",len(own)==0 and len(staff)>=1)
r = post("/api/reports", {"location":"","type":"Other","description":""}, H(r1))
check("T12","NFR5","Empty report rejected","blank location and description","400",r.status_code,r.status_code==400)

# --- Classification via sensor API ---
cases = [("T13","short_circuit",dict(voltage=120,current=150,leakage_ma=5,power_factor=0.4)),
         ("T14","open_circuit", dict(voltage=240,current=0.1,leakage_ma=1,power_factor=0.1)),
         ("T15","earth_fault",  dict(voltage=222,current=15,leakage_ma=150,power_factor=0.8)),
         ("T16","overload",     dict(voltage=210,current=30,leakage_ma=3,power_factor=0.8)),
         ("T17","normal",       dict(voltage=230,current=8,leakage_ma=2,power_factor=0.95))]
for tid, exp, vals in cases:
    r = post("/api/predict", {"node_id":"test-node", **vals}, NODE); d = r.get_json() or {}
    check(tid,"FR4, FR5",f"Classify a clear {exp} reading",str(vals),exp,d.get("fault",r.status_code),d.get("fault")==exp)
r = post("/api/predict", {"node_id":"test-node","voltage":230,"current":8,"leakage_ma":2,"power_factor":0.9}, {"X-Node-Key":"wrong"})
check("T18","FR4","Sensor reading, wrong API key","key 'wrong'","401",r.status_code,r.status_code==401)
try: r = post("/api/predict", {"node_id":"test-node","voltage":230}, NODE); code = r.status_code
except Exception as e: code = "exception"
check("T19","NFR5","Sensor reading with missing fields","only node_id and voltage","400",code,code==400)

# --- Alerts ---
alerts = get("/api/alerts", H(off)).get_json()
check("T20","FR8, FR10","Fault readings created alerts","after T13-T16","≥ 1 alert listed",f"{len(alerts)} alerts",len(alerts)>=1)
open_alert = next((a for a in alerts if a.get("status")=="open"), None)
r = post(f"/api/alerts/{open_alert['id']}/ack", None, H(r1)) if open_alert else None
check("T21","FR3","Resident tries to acknowledge alert","POST ack as resident","403",r.status_code if r else "no alert",bool(r) and r.status_code==403)
r = post(f"/api/alerts/{open_alert['id']}/ack", None, H(off)) if open_alert else None
after = next((a for a in get("/api/alerts", H(off)).get_json() if open_alert and a["id"]==open_alert["id"]), {})
check("T22","FR11","Officer acknowledges alert","POST ack as officer","status acknowledged, by officer",f"{after.get('status')}, {after.get('by')}",after.get("status")=="acknowledged" and after.get("by")=="officer")

# --- User management ---
nu = "off_"+uuid.uuid4().hex[:6]
r = post("/api/users", {"username":nu,"password":"secret123","role":"safety_officer"}, H(admin))
role = (post("/api/login", {"username":nu,"password":"secret123"}).get_json() or {}).get("role")
check("T23","FR14","Admin creates a safety officer",nu,"201; new user logs in as safety_officer",f"{r.status_code}; {role}",r.status_code==201 and role=="safety_officer")
names = [x["username"] for x in get("/api/users", H(admin)).get_json()]
check("T24","FR15","Admin lists users","GET /api/users","new user listed",nu in names,nu in names)

# --- Performance (NFR1) ---
times = []
for _ in range(100):
    t = time.time(); post("/api/predict", {"node_id":"perf","voltage":230,"current":8,"leakage_ma":2,"power_factor":0.9}, NODE); times.append((time.time()-t)*1000)
check("T25","NFR1","Classification response time","100 sequential readings","mean and max under 2000 ms",f"mean {sum(times)/100:.0f} ms, max {max(times):.0f} ms",max(times)<2000)


# =====================================================================
# Extended tests T26-T44: ticket workflow, SMS log, analytics, deployment checks
# (these cover features added after the original Chapter 3 design)
# =====================================================================
NEW = "Added after Ch.3"
r = post("/api/tickets", {"fault":"short_circuit","zone":"Kanyama","house":"88","phone":"097 123 4567","description":"Sparks at meter box"}, H(r1)); t1 = r.get_json() or {}
check("T26",NEW,"Resident submits fault ticket (wizard)","short_circuit, Kanyama, house 88","201, id FT-..., status new",f"{r.status_code}, {t1.get('id')}, {t1.get('status')}",r.status_code==201 and str(t1.get("id","")).startswith("FT-") and t1.get("status")=="new")
r = post("/api/tickets", {"fault":"lightning","zone":"Kanyama","house":"1"}, H(r1))
check("T27",NEW,"Unknown fault type rejected","fault = lightning","400",r.status_code,r.status_code==400)
r = post("/api/tickets", {"fault":"overload","zone":"Matero","house":""}, H(r1))
check("T28",NEW,"Missing house number rejected","house = (blank)","400",r.status_code,r.status_code==400)
r = post("/api/tickets", {"fault":"overload","zone":"Matero","house":"5","phone":"12"}, H(r1))
check("T29",NEW,"Invalid phone number rejected","phone = 12","400",r.status_code,r.status_code==400)
check("T30",NEW,"Phone number normalised to +260 format","097 123 4567","+260971234567",t1.get("phone"),t1.get("phone")=="+260971234567")
mine2 = [x for x in get("/api/tickets", H(r2)).get_json() if x.get("id")==t1.get("id")]
mine1 = [x for x in get("/api/tickets", H(r1)).get_json() if x.get("id")==t1.get("id")]
check("T31",NEW,"Residents see only their own tickets","resident2 vs resident1","resident1: 1, resident2: 0",f"resident1: {len(mine1)}, resident2: {len(mine2)}",len(mine1)==1 and len(mine2)==0)
seen = [x for x in get("/api/tickets", H(off)).get_json() if x.get("id")==t1.get("id")]
check("T32",NEW,"Officer sees all tickets","GET /api/tickets as officer","resident's ticket listed",f"{len(seen)} found",len(seen)==1)
r = post(f"/api/tickets/{t1['id']}/status", {"status":"dispatched"}, H(r1))
check("T33",NEW,"Resident cannot change ticket status","POST status as resident","403",r.status_code,r.status_code==403)
r = post(f"/api/tickets/{t1['id']}/status", {"status":"dispatched","assign":True,"note":"Crew heading to Kanyama"}, H(off))
tk = next((x for x in get("/api/tickets", H(off)).get_json() if x["id"]==t1["id"]), {})
check("T34",NEW,"Officer dispatches ticket with note","status dispatched + note","dispatched, assigned to officer, 1 note",f"{tk.get('status')}, {tk.get('assignee')}, {len(tk.get('notes',[]))} note",tk.get("status")=="dispatched" and tk.get("assignee")=="officer" and len(tk.get("notes",[]))==1)
r = post(f"/api/tickets/{t1['id']}/status", {"status":"flying"}, H(off))
check("T35",NEW,"Invalid status rejected","status = flying","400",r.status_code,r.status_code==400)
post(f"/api/tickets/{t1['id']}/status", {"status":"in_progress"}, H(off)); post(f"/api/tickets/{t1['id']}/status", {"status":"resolved"}, H(off))
tk = next((x for x in get("/api/tickets", H(off)).get_json() if x["id"]==t1["id"]), {})
check("T36",NEW,"Resolving a ticket records resolution time","dispatched > in_progress > resolved","status resolved, resolved_ts set",f"{tk.get('status')}, set={tk.get('resolved_ts') is not None}",tk.get("status")=="resolved" and tk.get("resolved_ts") is not None)
r = get("/api/analytics", H(off)); a = get("/api/analytics", H(admin)); ad = a.get_json() or {}
ok = r.status_code==403 and a.status_code==200 and set(ad.get("by_type",{}))=={"short_circuit","earth_fault","overload","open_circuit"} and ad.get("avg_resolution_min") is not None
check("T37",NEW,"Analytics: admin only, 4 fault types x zones","officer vs admin","officer 403; admin 200 with 4 fault types",f"officer {r.status_code}; admin {a.status_code}, avg {ad.get('avg_resolution_min')} min",ok)
def sensor_tickets(): return [x for x in get("/api/tickets", H(admin)).get_json() if x.get("node_id")=="dedupe-node" and x["fault"]=="earth_fault"]
bad = dict(voltage=222,current=15,leakage_ma=150,power_factor=0.8)
post("/api/predict", {"node_id":"dedupe-node", **bad}, NODE); n1 = len(sensor_tickets())
post("/api/predict", {"node_id":"dedupe-node", **bad}, NODE); n2 = len(sensor_tickets())
check("T38",NEW,"Repeated sensor fault opens only one ticket","same fault sent twice","1 ticket after both",f"{n1} then {n2}",n1==1 and n2==1)
time.sleep(1)
r = get("/api/sms", H(off)); logs = get("/api/sms", H(admin)).get_json()
check("T39",NEW,"SMS log: admin only, messages recorded","officer vs admin","officer 403; admin sees >= 2 messages",f"officer {r.status_code}; admin {len(logs)} messages",r.status_code==403 and len(logs)>=2)
gone = "tmp_"+uuid.uuid4().hex[:6]; post("/api/users", {"username":gone,"password":"secret123","role":"resident"}, H(admin))
r = c.delete(f"/api/users/{gone}", headers=H(admin)); after = post("/api/login", {"username":gone,"password":"secret123"})
check("T40",NEW,"Admin removes a user; user can no longer log in",gone,"200, then login 401",f"{r.status_code}, then {after.status_code}",r.status_code==200 and after.status_code==401)
r = c.delete("/api/users/admin", headers=H(admin))
check("T41",NEW,"Starter admin account cannot be removed","DELETE /api/users/admin","400",r.status_code,r.status_code==400)
r = get("/")
check("T42",NEW,"React web app served at the root address","GET /","200 and HTML with root element",f"{r.status_code}, root={b'id=\"root\"' in r.data}",r.status_code==200 and b'id="root"' in r.data)
kinds = [(get("/api/simulate/rate-test", H(off)).get_json() or {}).get("fault") for _ in range(300)]
rate = 100*sum(k!="normal" for k in kinds)/300
check("T43",NEW,"Simulator produces faults at a realistic rate","300 simulated readings","fault share under 10%",f"{rate:.1f}% faults",rate<10)

df = pd.DataFrame(results); df.to_csv("test_results.csv", index=False)
pd.set_option("display.max_colwidth", 60, "display.width", 250)
print(df[["ID","Req","Test","Expected","Actual","Result"]].to_string(index=False))
print(f"\n{(df.Result=='PASS').sum()} of {len(df)} passed")