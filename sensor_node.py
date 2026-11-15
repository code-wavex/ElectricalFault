#!/usr/bin/env python3
"""Standalone sensor node. Needs only: pip install requests

  python sensor_node.py --url https://YOUR-APP.onrender.com --key YOUR_NODE_KEY --node kanyama-01
  python sensor_node.py --once short_circuit          # send one fault reading and stop (for demos)
  python sensor_node.py --url http://127.0.0.1:5000   # local test with the default key

If the network drops, readings are kept in a local queue and sent when the connection returns.
"""
import argparse, collections, math, os, random, sys, time, requests

CLASSES = ["normal", "short_circuit", "earth_fault", "overload", "open_circuit"]
U, G = random.uniform, random.gauss
logu = lambda lo, hi: math.exp(U(math.log(lo), math.log(hi)))

def sample(label):  # same ranges the model was trained on
    if label == "normal":          v, i, l, pf = G(228, 10), U(1.5, 20), U(0, 12), U(.6, .98)
    elif label == "short_circuit": v, i, l, pf = U(60, 200), logu(30, 250), U(0, 20), U(.2, .75)
    elif label == "earth_fault":   v, i, l, pf = G(222, 12), U(4, 30), logu(8, 300), U(.6, .95)
    elif label == "overload":      v, i, l, pf = U(195, 228), U(16, 40), U(0, 12), U(.6, .9)
    else:                          v, i, l, pf = U(220, 250), U(0, 2), U(0, 3), U(0, .5)
    return dict(voltage=round(v + G(0, 3), 1), current=round(max(0, i * (1 + G(0, .05))), 2),
                leakage_ma=round(max(0, l + G(0, 1.5)), 2), power_factor=round(min(1, max(0, pf + G(0, .03))), 3))

def flush(queue, url, key):
    while queue:
        try:
            r = requests.post(url + "/api/predict", json=queue[0], headers={"X-Node-Key": key}, timeout=45)
        except requests.RequestException:
            return False
        if r.status_code == 401: sys.exit("The server rejected the node key. Check --key.")
        if r.status_code >= 400:
            print("  dropped a reading the server refused:", r.status_code, r.text[:80])
        else:
            q = queue[0]; print(f"  {q['node_id']}  V={q['voltage']} I={q['current']} leak={q['leakage_ma']}mA pf={q['power_factor']}  ->  {r.json().get('fault')}")
        queue.popleft()
    return True

def main():
    p = argparse.ArgumentParser(description="Simulated electrical sensor node")
    p.add_argument("--url", default="http://127.0.0.1:5000"); p.add_argument("--key", default=os.getenv("NODE_KEY", "node-secret-123"))
    p.add_argument("--node", default="kanyama-01"); p.add_argument("--interval", type=float, default=5, help="seconds between readings")
    p.add_argument("--fault-rate", type=float, default=0.02, help="chance a reading is a fault (0 to 1)")
    p.add_argument("--once", choices=CLASSES[1:], help="send one reading of this fault and exit"); p.add_argument("--count", type=int, default=0, help="stop after N readings (0 = run forever)")
    a = p.parse_args(); url = a.url.rstrip("/"); queue = collections.deque(maxlen=500); sent = 0
    print(f"Sensor node {a.node} -> {url}  (Ctrl+C to stop)")
    while True:
        label = a.once or (random.choice(CLASSES[1:]) if random.random() < a.fault_rate else "normal")
        queue.append({"node_id": a.node, **sample(label)}); sent += 1
        if not flush(queue, url, a.key): print(f"  offline, {len(queue)} reading(s) waiting to send")
        if a.once or (a.count and sent >= a.count): break
        time.sleep(a.interval)
    if queue: print(f"Stopped with {len(queue)} unsent reading(s).")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nStopped.")
