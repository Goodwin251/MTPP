"""
Benchmark для Задачі 1.

Запускає всі варіанти (sequential, race, deadlock, safe) на різних
кількостях потоків, збирає реальні числа і зберігає JSON для звіту.

Використання:
    python3 benchmark.py            # короткий прогон
    python3 benchmark.py --full     # повний прогон до 1100 потоків
"""
import sys
import os
import json
import time
import random
import threading
import importlib.util


FULL = "--full" in sys.argv

DURATION = 0.5 if not FULL else 1.5
N_ACCOUNTS = 120
THREAD_COUNTS = [1, 2, 4, 8, 16] if not FULL else [1, 2, 4, 8, 16, 64, 256, 1100]
DEADLOCK_COUNTS = [2, 4, 8] if not FULL else [2, 8, 50, 200, 1100]


HERE = os.path.dirname(os.path.abspath(__file__))


def reload_module(path, name):
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reset_unsafe(mod, n_acc, n_thr, dur, deadlock):
    mod.N_ACCOUNTS = n_acc
    mod.N_THREADS = n_thr
    mod.TRANSFER_DURATION = dur
    mod.DEMO_DEADLOCK = deadlock
    random.seed(42)
    mod.accounts = [random.randint(mod.INITIAL_MIN, mod.INITIAL_MAX) for _ in range(n_acc)]
    mod.locks = [threading.Lock() for _ in range(n_acc)]
    mod.transfers_done = 0
    mod.stop_flag = threading.Event()


def reset_safe(mod, n_acc, n_thr, dur):
    mod.N_ACCOUNTS = n_acc
    mod.N_THREADS = n_thr
    mod.TRANSFER_DURATION = dur
    random.seed(42)
    mod.accounts = [random.randint(mod.INITIAL_MIN, mod.INITIAL_MAX) for _ in range(n_acc)]
    mod.locks = [threading.Lock() for _ in range(n_acc)]
    mod.transfers_done = 0
    mod.transfers_failed = 0
    mod.stop_flag = threading.Event()


def run_race(n_thr):
    mod = reload_module(os.path.join(HERE, "bank_unsafe.py"), "bank_unsafe")
    reset_unsafe(mod, N_ACCOUNTS, n_thr, DURATION, False)
    return mod.main()


def run_deadlock(n_thr):
    mod = reload_module(os.path.join(HERE, "bank_unsafe.py"), "bank_unsafe")
    reset_unsafe(mod, N_ACCOUNTS, n_thr, DURATION, True)
    return mod.main()


def run_safe(n_thr):
    mod = reload_module(os.path.join(HERE, "bank_safe.py"), "bank_safe")
    reset_safe(mod, N_ACCOUNTS, n_thr, DURATION)
    return mod.main()


def run_sequential():
    random.seed(42)
    accs = [random.randint(100, 1000) for _ in range(N_ACCOUNTS)]
    initial = sum(accs)
    tx = 0
    t0 = time.perf_counter()
    end = t0 + DURATION
    while time.perf_counter() < end:
        s = random.randrange(N_ACCOUNTS)
        d = random.randrange(N_ACCOUNTS)
        if s == d:
            continue
        a = random.randint(1, 50)
        if accs[s] >= a:
            accs[s] -= a
            accs[d] += a
        tx += 1
    el = time.perf_counter() - t0
    return {"initial_total": initial, "final_total": sum(accs),
            "delta": sum(accs) - initial, "transfers": tx, "elapsed": el}


def main():
    print(f"=== Benchmark Задача 1 ({'FULL' if FULL else 'short'} режим, "
          f"duration={DURATION}s, accounts={N_ACCOUNTS}) ===")
    results = {"config": {"duration": DURATION, "accounts": N_ACCOUNTS, "full": FULL},
               "sequential": {}, "race": {}, "deadlock": {}, "safe": {}}

    print("\n-- Sequential baseline --")
    s = run_sequential()
    results["sequential"]["1"] = s
    print(f"  tx={s['transfers']}, t={s['elapsed']:.3f}s, Δ={s['delta']}")

    print("\n-- RACE CONDITION (без локів) --")
    for n in THREAD_COUNTS:
        r = run_race(n)
        results["race"][str(n)] = r
        print(f"  threads={n:4d}  Δ={r['delta']:+7d}  tx={r['transfers']:8d}  t={r['elapsed']:.3f}s")
        time.sleep(0.1)

    print("\n-- DEADLOCK (захоплення локів без сортування) --")
    for n in DEADLOCK_COUNTS:
        r = run_deadlock(n)
        results["deadlock"][str(n)] = r
        print(f"  threads={n:4d}  Δ={r['delta']:+7d}  tx={r['transfers']:8d}  "
              f"deadlocked={r['deadlocked_threads']}  t={r['elapsed']:.3f}s")
        time.sleep(0.1)

    print("\n-- SAFE (sorted lock ordering) --")
    for n in THREAD_COUNTS:
        r = run_safe(n)
        results["safe"][str(n)] = r
        print(f"  threads={n:4d}  Δ={r['delta']:+7d}  tx={r['transfers']:8d}  "
              f"failed={r.get('failed', 0):7d}  t={r['elapsed']:.3f}s")
        time.sleep(0.1)

    out = os.path.abspath(os.path.join(HERE, "..", "results", "task1_results.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n→ JSON: {out}")


if __name__ == "__main__":
    main()
