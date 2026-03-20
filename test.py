import argparse, csv, json, os, statistics, sys, threading, time
from datetime import datetime
from http.client import HTTPConnection, RemoteDisconnected
from urllib.parse import urlparse
from urllib.request import urlopen
from urllib.error import URLError

RESULTS = "results"
os.makedirs(RESULTS, exist_ok=True)

class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.latencies = []
        self.errors = 0

    def add(self, lat):
        with self.lock:
            self.latencies.append(lat)

    def add_err(self):
        with self.lock:
            self.errors += 1


def worker(url, stats, stop):
    p = urlparse(url)
    conn = None
    while not stop.is_set():
        try:
            if conn is None:
                conn = HTTPConnection(p.hostname, p.port or 80, timeout=5)
            t0 = time.perf_counter()
            conn.request("GET", p.path or "/", headers={"Connection": "keep-alive"})
            r = conn.getresponse(); r.read()
            stats.add(time.perf_counter() - t0)
        except Exception:
            stats.add_err()
            try: conn.close()
            except: pass
            conn = None
    if conn:
        try: conn.close()
        except: pass


def run_load(url, connections, duration, label):
  
    stop = threading.Event()
    all_stats = [Stats() for _ in range(connections)]
    threads = [
        threading.Thread(target=worker, args=(url, all_stats[i], stop), daemon=True)
        for i in range(connections)
    ]
    t0 = time.perf_counter()
    for t in threads: t.start()
    time.sleep(duration)
    stop.set()
    for t in threads: t.join(timeout=3)
    elapsed = time.perf_counter() - t0

    lats = []
    errs = 0
    for s in all_stats:
        lats.extend(s.latencies)
        errs += s.errors
    total = len(lats) + errs

    if not lats:
        lats = [0]

    sl = sorted(lats)
    n  = len(sl)
    pct = lambda p: round(sl[min(int(n * p / 100), n - 1)] * 1000, 2)

    row = {
        "label":     label,
        "env":       "",           # set by caller
        "conns":     connections,
        "duration":  duration,
        "requests":  total,
        "errors":    errs,
        "rps":       round(total / elapsed, 1),
        "lat_min":   round(min(lats) * 1000, 2),
        "lat_mean":  round(statistics.mean(lats) * 1000, 2),
        "lat_p50":   pct(50),
        "lat_p90":   pct(90),
        "lat_p95":   pct(95),
        "lat_p99":   pct(99),
        "lat_max":   round(max(lats) * 1000, 2),
        "err_pct":   round(errs / total * 100, 2) if total else 0,
    }
    print(f"    [{label}] rps={row['rps']}  p50={row['lat_p50']}ms  "
          f"p99={row['lat_p99']}ms  err={row['err_pct']}%")
    return row

#Prometheus metrics snapshot helper
def prom_val(base, query):
    try:
        url = f"{base}/api/v1/query?query={query}"
        with urlopen(url, timeout=8) as r:
            d = json.loads(r.read())
            results = d.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1])
    except Exception:
        pass
    return None

#This will return all the metrics
def get_metrics(prom_url, env):
    return {
        "env":           env,
        "timestamp":     datetime.now().isoformat(),
        "active_conns":  prom_val(prom_url, "nginx_connections_active"),
        "requests_total":prom_val(prom_url, "sum(nginx_http_requests_total)"),
        "cpu_nginx":     prom_val(prom_url, 'sum(rate(container_cpu_usage_seconds_total{container="nginx"}[1m]))'),
        "mem_nginx_mb":  (prom_val(prom_url, 'sum(container_memory_working_set_bytes{container="nginx"})') or 0) / 1e6,
    }

#this is a test suite for one environment
SCENARIOS = [
    ("low",    10,  30),
    ("medium", 50,  60),
    ("high",  200,  60),
]

def warm_up(url):
    p = urlparse(url)
    try:
        conn = HTTPConnection(p.hostname, p.port or 80, timeout=5)
        for _ in range(5):
            conn.request("GET", p.path or "/")
            r = conn.getresponse(); r.read()
        conn.close()
        return True
    except Exception as e:
        print(f"  ERROR: cannot reach {url}: {e}")
        return False


def test_env(env, url, prom_url):
    print(f"\n{'='*55}")
    print(f"  Testing {env.upper()}  {url}")
    print(f"{'='*55}")

    if not warm_up(url):
        print(f"  Skipping {env} – cluster not ready")
        return [], {}

    rows = []
    # Runs each scenario 3 times for reliability
    for name, conns, dur in SCENARIOS:
        for run in range(1, 4):
            label = f"{name}-run{run}"
            print(f"  {label} ({conns}c × {dur}s)...")
            row = run_load(url, conns, dur, label)
            row["env"] = env
            rows.append(row)
            time.sleep(10)   # cooldown between runs

    # Burst test: ramp 10→100→200→10
    print("\n  Burst ramp (10→100→200→10 conns, 30s each)...")
    burst_rows = []
    for conns, phase in [(10,"low-baseline"),(100,"moderate"),(200,"peak"),(10,"recovery")]:
        r = run_load(url, conns, 30, f"burst-{phase}")
        r["env"] = env
        burst_rows.append(r)
        time.sleep(5)
    rows.extend(burst_rows)

    # Final metrics snapshot
    metrics = get_metrics(prom_url, env) if prom_url else {}
    if metrics:
        print(f"\n  Prometheus snapshot:")
        for k, v in metrics.items():
            if k not in ("env","timestamp"):
                print(f"    {k:20s}: {v}")

    return rows, metrics

#Charts to understand the results, used matplotlib
def make_charts(cloud_rows, edge_rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  matplotlib not installed – skipping charts. pip3 install matplotlib")
        return

    CLOUD, EDGE = "#1f77b4", "#ff7f0e"

    def avg_by(rows, label_prefix, field):
        vals = [r[field] for r in rows if r["label"].startswith(label_prefix)]
        return round(sum(vals) / len(vals), 2) if vals else 0

    # Chart1 - Throughput
    fig, ax = plt.subplots(figsize=(8, 4))
    loads  = ["Low (10c)", "Medium (50c)", "High (200c)"]
    prfx   = ["low",       "medium",       "high"]
    c_rps  = [avg_by(cloud_rows, p, "rps") for p in prfx]
    e_rps  = [avg_by(edge_rows,  p, "rps") for p in prfx]
    x = np.arange(3); w = .35
    b1 = ax.bar(x - w/2, c_rps, w, label="Cloud (Minikube)", color=CLOUD)
    b2 = ax.bar(x + w/2, e_rps, w, label="Edge (K3s/k3d)",   color=EDGE)
    ax.bar_label(b1, fmt="%.0f", padding=3, fontsize=8)
    ax.bar_label(b2, fmt="%.0f", padding=3, fontsize=8)
    ax.set(xlabel="Load level", ylabel="Requests / second",
           title="Throughput – Cloud vs Edge (NGINX LB VNF)", xticks=x, xticklabels=loads)
    ax.legend(); fig.tight_layout()
    fig.savefig(f"{RESULTS}/01_throughput.png", dpi=150); plt.close(fig)
    print("01_throughput.png")

    # Chart2 - Latency percentiles
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=False)
    for idx, (lbl, pfx) in enumerate(zip(loads, prfx)):
        ax = axes[idx]
        pcts = ["lat_p50","lat_p90","lat_p95","lat_p99"]
        plbl = ["p50","p90","p95","p99"]
        cv = [avg_by(cloud_rows, pfx, p) for p in pcts]
        ev = [avg_by(edge_rows,  pfx, p) for p in pcts]
        xi = np.arange(4)
        ax.bar(xi - w/2, cv, w, label="Cloud", color=CLOUD)
        ax.bar(xi + w/2, ev, w, label="Edge",  color=EDGE)
        ax.set(title=lbl, xlabel="Percentile", ylabel="ms" if idx==0 else "",
               xticks=xi, xticklabels=plbl)
        if idx==0: ax.legend()
    fig.suptitle("Latency Percentiles – Cloud vs Edge", fontsize=13)
    fig.tight_layout(); fig.savefig(f"{RESULTS}/02_latency.png", dpi=150); plt.close(fig)
    print("  ✔ 02_latency.png")

    # Chart3 - Error rate
    fig, ax = plt.subplots(figsize=(8, 4))
    ce = [avg_by(cloud_rows, p, "err_pct") for p in prfx]
    ee = [avg_by(edge_rows,  p, "err_pct") for p in prfx]
    b1 = ax.bar(x - w/2, ce, w, label="Cloud", color=CLOUD)
    b2 = ax.bar(x + w/2, ee, w, label="Edge",  color=EDGE)
    ax.bar_label(b1, fmt="%.2f%%", padding=3, fontsize=8)
    ax.bar_label(b2, fmt="%.2f%%", padding=3, fontsize=8)
    ax.set(xlabel="Load level", ylabel="Error rate (%)",
           title="Error Rate – Cloud vs Edge", xticks=x, xticklabels=loads)
    ax.legend(); fig.tight_layout()
    fig.savefig(f"{RESULTS}/03_error_rate.png", dpi=150); plt.close(fig)
    print("03_error_rate.png")

    # Chart4 - Burst rps timeline
    fig, ax = plt.subplots(figsize=(10, 4))
    phases = ["burst-low-baseline","burst-moderate","burst-peak","burst-recovery"]
    for rows, col, lbl in [(cloud_rows,CLOUD,"Cloud"),(edge_rows,EDGE,"Edge")]:
        vals = [avg_by(rows, p, "rps") for p in phases]
        ax.plot(["Baseline\n(10c)","Moderate\n(100c)","Peak\n(200c)","Recovery\n(10c)"],
                vals, marker="o", color=col, label=lbl, linewidth=2)
    ax.set(ylabel="Requests / second", title="Burst Ramp – Cloud vs Edge")
    ax.legend(); fig.tight_layout()
    fig.savefig(f"{RESULTS}/04_burst.png", dpi=150); plt.close(fig)
    print("04_burst.png")


#Final CSV 
FIELDS = ["env","label","conns","duration","requests","errors","rps",
          "lat_min","lat_mean","lat_p50","lat_p90","lat_p95","lat_p99","lat_max","err_pct"]

def save_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"  CSV → {path}")

#cli entry point
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cloud",      default="", help="Cloud NGINX URL")
    p.add_argument("--edge",       default="", help="Edge NGINX URL")
    p.add_argument("--cloud-prom", default="", help="Cloud Prometheus URL")
    p.add_argument("--edge-prom",  default="", help="Edge Prometheus URL")
    args = p.parse_args()

    cloud_rows, cloud_metrics = [], {}
    edge_rows,  edge_metrics  = [], {}

    if args.cloud:
        cloud_rows, cloud_metrics = test_env("cloud", args.cloud, args.cloud_prom)
        save_csv(cloud_rows, f"{RESULTS}/cloud_results.csv")

    if args.edge:
        edge_rows, edge_metrics = test_env("edge", args.edge, args.edge_prom)
        save_csv(edge_rows, f"{RESULTS}/edge_results.csv")

    if cloud_rows or edge_rows:
        print("\n  Generating charts...")
        make_charts(cloud_rows, edge_rows)

    # Print comparison table
    if cloud_rows and edge_rows:
        print(f"\n  {'─'*52}")
        print(f"  {'Metric':<30} {'Cloud':>10} {'Edge':>10}")
        print(f"  {'─'*52}")
        for name, pfx in [("Low load","low"),("Medium load","medium"),("High load","high")]:
            def avg(rows, f): v=[r[f] for r in rows if r['label'].startswith(pfx)]; return round(sum(v)/len(v),1) if v else 0
            print(f"  {name+' rps':<30} {avg(cloud_rows,'rps'):>10} {avg(edge_rows,'rps'):>10}")
            print(f"  {name+' p99 ms':<30} {avg(cloud_rows,'lat_p99'):>10} {avg(edge_rows,'lat_p99'):>10}")
            print(f"  {name+' err%':<30} {avg(cloud_rows,'err_pct'):>10} {avg(edge_rows,'err_pct'):>10}")
        print(f"  {'─'*52}")

    print("\n  Done. Results in results/")


if __name__ == "__main__":
    main()
