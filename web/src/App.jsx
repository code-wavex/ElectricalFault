import { useState, useEffect, useCallback, useRef } from "react";

const NODES = ["kanyama-01", "matero-01", "kanyama-02"], ZONES = ["Kanyama", "Matero"];
const FAULTS = {
  short_circuit: { label: "Short Circuit", sev: "critical", tip: "Sparks, a loud bang or burning smell from wiring or a socket.", icon: "M13 2 4 14h7l-1 8 9-12h-7z" },
  earth_fault: { label: "Earth Fault", sev: "critical", tip: "Tingling or shocks from taps, metal doors or appliances.", icon: "M12 3v10M5 13h14M8 17h8M10.5 21h3" },
  overload: { label: "Overload", sev: "high", tip: "Hot sockets, tripping breakers or lights dimming.", icon: "M12 3a3 3 0 0 0-3 3v7.5a5 5 0 1 0 6 0V6a3 3 0 0 0-3-3z" },
  open_circuit: { label: "Open Circuit", sev: "medium", tip: "Your house has no power while neighbours still do.", icon: "M3 12h5M16 12h5M8 12l5-5" },
};
const STATUS = { new: "New", dispatched: "Dispatched", in_progress: "In progress", resolved: "Resolved" }, STEPS = Object.keys(STATUS);
const NEXT = { new: ["dispatched", "Dispatch crew"], dispatched: ["in_progress", "Start work"], in_progress: ["resolved", "Mark resolved"] };
const PORTALS = [["resident", "Resident"], ["safety_officer", "Officer"], ["administrator", "Admin"]];
const TABS = { resident: [["home", "My faults"], ["report", "Report fault"]], safety_officer: [["board", "Triage board"], ["live", "Live sensors"]], administrator: [["overview", "Overview"], ["live", "Live sensors"], ["users", "Users"], ["sms", "SMS log"]] };
const rank = t => ({ critical: 0, high: 1, medium: 2 })[FAULTS[t.fault]?.sev] ?? 3;
const dur = m => m == null ? "–" : m < 60 ? m + " min" : Math.floor(m / 60) + "h " + (m % 60) + "m";
const saved = () => { try { return JSON.parse(sessionStorage.getItem("fds")); } catch { return null; } };
const where = t => t.source === "sensor" ? `Sensor ${t.node_id} · ${t.zone}` : `House ${t.house}, ${t.zone}`;

async function call(path, token, method = "GET", body) {
  const r = await fetch("/api/" + path, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
}
const Icon = ({ d, size = 18 }) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
const Badge = ({ fault, short }) => { const f = FAULTS[fault]; return f ? <span className={"badge " + f.sev}><Icon d={f.icon} size={14} />{f.label}{!short && <i>{f.sev}</i>}</span> : null; };
const Chip = ({ s }) => <span className={"chip " + s}>{STATUS[s]}</span>;
const Empty = ({ text }) => <div className="empty">{text}</div>;

function Login({ onAuth }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [p2, setP2] = useState(""), [err, setErr] = useState(""), [mk, setMk] = useState(false);
  async function go(user, pw) {
    setErr("");
    if (mk) {
      if (user.trim().length < 3 || pw.length < 6) return setErr("Username needs 3+ characters and password 6+.");
      if (pw !== p2) return setErr("The two passwords do not match.");
      const c = await call("register", null, "POST", { username: user, password: pw }); if (!c.ok) return setErr(c.data.error || "Could not create account");
    }
    const r = await call("login", null, "POST", { username: user, password: pw }); r.ok ? onAuth(r.data) : setErr(r.data.error || "Could not sign in");
  }
  return <div className="login"><form className="card login-card" onSubmit={e => { e.preventDefault(); go(u, p); }}>
    <div className="logo"><Icon d={FAULTS.short_circuit.icon} size={26} /></div><h1>Smart Electrical Fault Detection</h1>
    <p className="muted">Monitoring for Kanyama, Matero and other dense residential compounds</p>
    <label>Username<input value={u} onChange={e => setU(e.target.value)} autoFocus /></label>
    <label>Password<input type="password" value={p} onChange={e => setP(e.target.value)} /></label>
    {mk && <label>Confirm password<input type="password" value={p2} onChange={e => setP2(e.target.value)} /></label>}
    {err && <p className="err" role="alert">{err}</p>}<button className="btn">{mk ? "Create resident account" : "Sign in"}</button>
    <button type="button" className="link" onClick={() => { setMk(!mk); setErr(""); }}>{mk ? "Already have an account? Sign in" : "New resident? Create an account"}</button>
  </form></div>;
}

function SwitchModal({ role, onAuth, close }) {
  const name = PORTALS.find(p => p[0] === role)[1], [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState("");
  async function go(e) {
    e.preventDefault(); const r = await call("login", null, "POST", { username: u, password: p });
    if (!r.ok) return setErr(r.data.error || "Could not sign in");
    if (r.data.role !== role) return setErr(`That account does not have ${name} access.`);
    onAuth(r.data); close();
  }
  return <div className="overlay" onClick={close}><form className="card modal" onClick={e => e.stopPropagation()} onSubmit={go}>
    <h3>Sign in to the {name} portal</h3><label>Username<input value={u} onChange={e => setU(e.target.value)} autoFocus /></label>
    <label>Password<input type="password" value={p} onChange={e => setP(e.target.value)} /></label>
    {err && <p className="err" role="alert">{err}</p>}
    <div className="row"><button type="button" className="btn ghost" onClick={close}>Cancel</button><button className="btn">Sign in</button></div></form></div>;
}

function TopBar({ me, switchTo, out }) {
  return <header className="top"><div className="brand"><Icon d={FAULTS.short_circuit.icon} /> Fault Detection <small>Lusaka</small></div>
    <div className="switch" role="group" aria-label="Switch portal (demo)">{PORTALS.map(([r, n]) => <button key={r} className={me.role === r ? "on" : ""} onClick={() => me.role !== r && switchTo(r)}>{n}</button>)}</div>
    <div className="who"><span>{me.username}</span><button onClick={out}>Log out</button></div></header>;
}

function Tabs({ role, tab, setTab }) {
  return <nav className="tabs">{TABS[role].map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}</nav>;
}

/* ---------- Resident (mobile-first) ---------- */
function Tracker({ s }) { const i = STEPS.indexOf(s); return <ol className="track">{STEPS.map((x, n) => <li key={x} className={n <= i ? "done" : ""}><b />{STATUS[x]}</li>)}</ol>; }

function FaultCard({ t }) {
  return <article className={"fcard " + FAULTS[t.fault].sev}><div className="row"><Badge fault={t.fault} /><Chip s={t.status} /></div>
    <p className="loc">{where(t)}</p><p className="muted small">{t.description || "No description"}</p><Tracker s={t.status} />
    <div className="row small muted"><span>Ticket {t.id}</span><span>{t.created}</span></div></article>;
}

function Home({ tickets, go }) {
  const active = tickets.filter(t => t.status !== "resolved"), past = tickets.filter(t => t.status === "resolved");
  return <>
    <div className="hero"><div><b>{active.length}</b><span>active {active.length === 1 ? "fault" : "faults"}</span></div><button className="btn light" onClick={() => go("report")}>+ Report a fault</button></div>
    <h3>Active</h3>{active.length ? active.map(t => <FaultCard key={t.id} t={t} />) : <Empty text="No active faults. Stay safe!" />}
    <h3>Past</h3>{past.length ? past.map(t => <FaultCard key={t.id} t={t} />) : <Empty text="Resolved faults will show here." />}</>;
}

function Wizard({ token, done, back }) {
  const [step, setStep] = useState(1), [f, setF] = useState({ fault: "", zone: "Kanyama", house: "", phone: "", description: "" }), [err, setErr] = useState(""), [ticket, setTicket] = useState(null);
  const set = k => e => setF({ ...f, [k]: e.target.value });
  async function submit() {
    if (!f.house.trim()) return setErr("Please enter your house number.");
    const r = await call("tickets", token, "POST", f);
    if (!r.ok) return setErr(r.data.error || "Could not send report"); setTicket(r.data); setStep(3); done();
  }
  const reset = () => { setF({ fault: "", zone: "Kanyama", house: "", phone: "", description: "" }); setErr(""); setStep(1); };
  return <div className="wizard">
    <ol className="steps">{["Fault", "Location", "Done"].map((n, i) => <li key={n} className={step > i ? "on" : ""}><b>{step > i + 1 ? "✓" : i + 1}</b>{n}</li>)}</ol>
    {step === 1 && <><h3>What kind of fault is it?</h3>
      <div className="pick">{Object.entries(FAULTS).map(([k, x]) => <button key={k} type="button" className={"opt " + x.sev + (f.fault === k ? " sel" : "")} onClick={() => setF({ ...f, fault: k })}>
        <Icon d={x.icon} size={28} /><b>{x.label}</b><span>{x.tip}</span><em>{x.sev}</em></button>)}</div>
      {FAULTS[f.fault]?.sev === "critical" && <p className="warn">Danger: keep everyone away from the area and do not touch any wires or wet surfaces.</p>}
      <button className="btn wide" disabled={!f.fault} onClick={() => setStep(2)}>Continue</button></>}
    {step === 2 && <><h3>Where is it?</h3>
      <div className="zones">{ZONES.map(z => <button key={z} type="button" className={f.zone === z ? "on" : ""} onClick={() => setF({ ...f, zone: z })}>{z}</button>)}</div>
      <label>House number<input value={f.house} onChange={set("house")} maxLength={20} inputMode="numeric" placeholder="e.g. 142" /></label>
      <label>Phone for SMS updates (optional)<input value={f.phone} onChange={set("phone")} maxLength={16} inputMode="tel" placeholder="e.g. 0971234567" /></label>
      <label>Describe what you see<textarea rows={4} value={f.description} onChange={set("description")} maxLength={500} placeholder="When did it start? Is anyone in danger?" /></label>
      {err && <p className="err" role="alert">{err}</p>}
      <div className="row"><button className="btn ghost" onClick={() => setStep(1)}>Back</button><button className="btn" onClick={submit}>Submit report</button></div></>}
    {step === 3 && ticket && <div className="success"><div className="tick">✓</div><h3>Report received</h3><p className="muted">A field officer will be dispatched. Quote this ticket if you call.</p>
      <div className="tid">{ticket.id}</div><Badge fault={ticket.fault} /><p className="muted small">{where(ticket)}</p>{ticket.phone && <p className="muted small">SMS updates will go to {ticket.phone}</p>}
      <button className="btn wide" onClick={back}>Back to my faults</button><button className="btn ghost wide" onClick={reset}>Report another fault</button></div>}
  </div>;
}

/* ---------- Officer ---------- */
function Ticket({ t, token, refresh }) {
  const [note, setNote] = useState(""), [open, setOpen] = useState(false), nx = NEXT[t.status], crit = FAULTS[t.fault].sev === "critical" && t.status !== "resolved";
  const act = async body => { await call(`tickets/${t.id}/status`, token, "POST", { assign: true, ...body }); setNote(""); setOpen(false); refresh(); };
  return <article className={"tk " + (crit ? "crit" : "")}>{crit && <div className="prio">Priority</div>}
    <div className="row"><Badge fault={t.fault} short /><span className="small muted">{t.id}</span></div>
    <p className="loc">{where(t)}</p><p className="small muted">{t.description}</p>
    {t.notes?.slice(-2).map((n, i) => <p key={i} className="note"><b>{n.by}:</b> {n.text}</p>)}
    <div className="row small muted"><span>{t.assignee ? "Assigned: " + t.assignee : "Unassigned"}</span><span>{t.created}</span></div>
    {t.status !== "resolved" && <div className="acts">{nx && <button className="btn sm" onClick={() => act({ status: nx[0] })}>{nx[1]}</button>}<button className="btn sm ghost" onClick={() => setOpen(!open)}>Add note</button></div>}
    {open && <div className="noteform"><input value={note} onChange={e => setNote(e.target.value)} placeholder="Note for the crew…" maxLength={300} /><button className="btn sm" disabled={!note.trim()} onClick={() => act({ note })}>Save</button></div>}</article>;
}

function Board({ tickets, token, refresh }) {
  const crit = tickets.filter(t => t.status !== "resolved" && FAULTS[t.fault]?.sev === "critical").length;
  return <><div className={"banner " + (crit ? "bad" : "good")}>{crit ? `${crit} critical ${crit === 1 ? "hazard needs" : "hazards need"} attention. Short circuits and earth faults are pinned to the top.` : "No critical hazards are open right now."}</div>
    <div className="board">{STEPS.map(s => { const items = tickets.filter(t => t.status === s).sort((a, b) => rank(a) - rank(b) || b.ts - a.ts).slice(0, s === "resolved" ? 8 : 99);
      return <section key={s} className="col"><h4>{STATUS[s]}<em>{tickets.filter(t => t.status === s).length}</em></h4>
        <div className="colbody">{items.map(t => <Ticket key={t.id} t={t} token={token} refresh={refresh} />)}{!items.length && <Empty text="Nothing here" />}</div></section>; })}</div></>;
}

function Live({ rows, sim, setSim, token, refresh }) {
  const [node, setNode] = useState(NODES[0]), [kind, setKind] = useState("short_circuit");
  const inject = async () => { await call(`simulate/${node}?fault=${kind}`, token); refresh(); };
  return <><div className="bar"><p className="muted">Readings are classified by the trained model; real faults are rare, so use Inject to test one. Faults open triage tickets automatically.</p>
    <div className="inject"><select value={node} onChange={e => setNode(e.target.value)} aria-label="Node">{NODES.map(n => <option key={n}>{n}</option>)}</select>
      <select value={kind} onChange={e => setKind(e.target.value)} aria-label="Fault to inject">{Object.entries(FAULTS).map(([k, f]) => <option key={k} value={k}>{f.label}</option>)}</select>
      <button className="btn sm" onClick={inject}>Inject fault</button></div>
    <label className="toggle"><input type="checkbox" checked={sim} onChange={e => setSim(e.target.checked)} /><i /> Live simulation</label></div>
    <div className="card tbl"><table><thead><tr><th>Time</th><th>Node</th><th>Voltage</th><th>Current</th><th>Leakage</th><th>PF</th><th>Result</th></tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.ts + "-" + i}><td>{r.time}</td><td>{r.node_id}</td><td>{r.voltage} V</td><td>{r.current} A</td><td>{r.leakage_ma} mA</td><td>{r.power_factor}</td>
        <td>{r.fault === "normal" ? <span className="chip resolved">Normal</span> : <Badge fault={r.fault} short />}</td></tr>)}</tbody></table>
      {!rows.length && <Empty text={sim ? "Waiting for readings…" : "Turn on live simulation to see readings."} />}</div></>;
}

/* ---------- Admin ---------- */
function Overview({ s, tickets }) {
  if (!s) return <Empty text="Loading analytics…" />;
  const max = Math.max(1, ...Object.values(s.by_type).flatMap(z => Object.values(z)));
  const cards = [["Total faults", s.total, ""], ["Active critical hazards", s.critical_active, "bad"], ["Avg resolution time", dur(s.avg_resolution_min), ""], ["Open tickets", s.open, ""]];
  return <><div className="metrics">{cards.map(([n, v, k]) => <div key={n} className={"metric " + k}><span>{n}</span><b>{v}</b></div>)}</div>
    <div className="split2"><section className="card"><div className="row"><h3>Faults by type and compound</h3><div className="legend"><i className="kanyama" />Kanyama<i className="matero" />Matero</div></div>
      {Object.entries(FAULTS).map(([k, f]) => <div key={k} className="brow"><div className="blabel"><Badge fault={k} short /></div><div>{ZONES.map(z => { const n = s.by_type[k][z]; return <div key={z} className="bl"><div className="trk"><div className={"fl " + z.toLowerCase()} style={{ width: n / max * 100 + "%" }} /></div><b>{n}</b></div>; })}</div></div>)}</section>
      <section className="card"><h3>Ticket pipeline</h3>{STEPS.map(x => <div key={x} className="pipe"><Chip s={x} /><b>{s.by_status[x]}</b></div>)}
        <h3>Frequency table</h3><table className="mini"><thead><tr><th>Fault</th>{ZONES.map(z => <th key={z}>{z}</th>)}</tr></thead>
          <tbody>{Object.entries(FAULTS).map(([k, f]) => <tr key={k}><td>{f.label}</td>{ZONES.map(z => <td key={z}>{s.by_type[k][z]}</td>)}</tr>)}</tbody></table></section></div></>;
}

function Users({ rows, tickets, token, refresh, me }) {
  const [f, setF] = useState({ username: "", password: "", role: "safety_officer" }), [msg, setMsg] = useState(null), set = k => e => setF({ ...f, [k]: e.target.value });
  async function add(e) { e.preventDefault(); const r = await call("users", token, "POST", f); setMsg(r.ok ? { ok: 1, t: "User created." } : { t: r.data.error || "Could not create user" }); if (r.ok) { setF({ ...f, username: "", password: "" }); refresh(); } }
  async function del(u) { if (!confirm(`Remove ${u}?`)) return; const r = await call("users/" + u, token, "DELETE"); if (!r.ok) setMsg({ t: r.data.error }); refresh(); }
  return <div className="split2 u"><div className="card tbl"><table><thead><tr><th>Username</th><th>Role</th><th>Tickets</th><th></th></tr></thead>
    <tbody>{rows.map(u => <tr key={u.username}><td>{u.username}</td><td><span className={"role " + u.role}>{u.role.replace("_", " ")}</span></td><td>{tickets.filter(t => t.reporter === u.username).length}</td>
      <td>{!["admin", "officer", "resident", me.username].includes(u.username) && <button className="btn sm ghost" onClick={() => del(u.username)}>Remove</button>}</td></tr>)}</tbody></table></div>
    <form className="card form" onSubmit={add}><h3>Add account</h3><label>Username<input value={f.username} onChange={set("username")} /></label>
      <label>Password (6+ characters)<input type="password" value={f.password} onChange={set("password")} /></label>
      <label>Role<select value={f.role} onChange={set("role")}><option value="safety_officer">Officer</option><option value="administrator">Admin</option><option value="resident">Resident</option></select></label>
      <button className="btn">Create account</button>{msg && <p className={msg.ok ? "okmsg" : "err"} role="status">{msg.t}</p>}</form></div>;
}

function SmsLog({ rows }) {
  return <div className="card tbl"><table><thead><tr><th>Time</th><th>To</th><th>Message</th><th>Gateway result</th></tr></thead>
    <tbody>{rows.map(s => <tr key={s.id}><td>{s.time}</td><td>{s.to}</td><td className="wrap">{s.text}</td><td>{s.result}</td></tr>)}</tbody></table>
    {!rows.length && <Empty text="No SMS sent yet. Alerts for critical faults and ticket updates appear here." />}</div>;
}

export default function App() {
  const [me, setMe] = useState(saved), [ask, setAsk] = useState(null), [tab, setTab] = useState(null), [sim, setSim] = useState(true), empty = { tickets: [], users: [], stats: null, readings: [] }, [d, setD] = useState(empty);
  const ref = useRef({}); ref.current = { me, tab, sim };
  const auth = x => { sessionStorage.setItem("fds", JSON.stringify(x)); setMe(x); setTab(TABS[x.role][0][0]); setD(empty); };
  const out = useCallback(() => { sessionStorage.removeItem("fds"); setMe(null); setD({ tickets: [], users: [], stats: null, readings: [] }); }, []);

  const tick = useCallback(async () => {
    const { me: m, tab: tb, sim: sm } = ref.current; if (!m) return;
    const t = m.token, live = m.role !== "resident" && tb === "live";
    if (live && sm) await call("simulate/" + NODES[Math.floor(Math.random() * NODES.length)], t);
    const jobs = [["tickets", "tickets"]]; if (live) jobs.push(["readings", "readings"]);
    if (m.role === "administrator") jobs.push(["users", "users"], ["stats", "analytics"]);
    if (m.role === "administrator" && tb === "sms") jobs.push(["sms", "sms"]);
    const next = {}; for (const [k, p] of jobs) { const r = await call(p, t); if (r.status === 401) return out(); if (r.ok) next[k] = r.data; }
    setD(o => ({ ...o, ...next }));
  }, [out]);
  useEffect(() => { if (!me) return; tick(); const id = setInterval(tick, 4000); return () => clearInterval(id); }, [me, tab, sim, tick]);

  if (!me) return <Login onAuth={auth} />;
  const role = me.role, cur = TABS[role].some(t => t[0] === tab) ? tab : TABS[role][0][0], R = { token: me.token, refresh: tick };
  return <div className={"app " + role}><TopBar me={me} switchTo={setAsk} out={out} />
    <Tabs role={role} tab={cur} setTab={setTab} />
    <main className={role === "resident" ? "phone" : "wide"}>
      {role === "resident" && cur === "home" && <Home tickets={d.tickets} go={setTab} />}
      {role === "resident" && cur === "report" && <Wizard token={me.token} done={tick} back={() => setTab("home")} />}
      {role === "safety_officer" && cur === "board" && <Board tickets={d.tickets} {...R} />}
      {cur === "live" && <Live rows={d.readings} sim={sim} setSim={setSim} {...R} />}
      {role === "administrator" && cur === "overview" && <Overview s={d.stats} tickets={d.tickets} />}
      {role === "administrator" && cur === "sms" && <SmsLog rows={d.sms || []} />}
      {role === "administrator" && cur === "users" && <Users rows={d.users} tickets={d.tickets} me={me} {...R} />}
    </main>{ask && <SwitchModal role={ask} onAuth={auth} close={() => setAsk(null)} />}</div>;
}
