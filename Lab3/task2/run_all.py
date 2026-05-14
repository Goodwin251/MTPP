"""
Запускає всі три IPC-методи (Pipe, Socket, Shared Memory) Python↔C++,
збирає результати у results/task2_results.json.

Запуск:
    python run_all.py --n 50000
"""
import argparse, importlib.util, json, os, sys, time, platform

HERE = os.path.dirname(os.path.abspath(__file__))


def load(rel_path):
    path = os.path.join(HERE, rel_path)
    spec = importlib.util.spec_from_file_location("_mod", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(name, rel_main, n):
    print(f"\n{'─'*55}\n  {name}  (n={n})\n{'─'*55}")
    try:
        mod = load(rel_main)
        # тимчасово підмінюємо sys.argv щоб argparse в main() взяв наш n
        _argv, sys.argv = sys.argv, ["main", "--n", str(n)]
        r = mod.main()
        sys.argv = _argv
        return r
    except SystemExit as e:
        sys.argv = _argv
        return {"method": name, "error": str(e)}
    except Exception as e:
        sys.argv = _argv
        return {"method": name, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()

    print(f"\n{'='*55}")
    print(f"  IPC Benchmark — Python ↔ C++  |  n={args.n}")
    print(f"  {platform.system()} {platform.release()}  |  Python {sys.version.split()[0]}")
    print(f"{'='*55}")

    results = []
    for name, rel in [
        ("Pipe",          "pipe/main_pipe.py"),
        ("Socket (TCP)",  "socket/main_socket.py"),
        ("Shared Memory", "shared_mem/main_shm.py"),
    ]:
        r = run(name, rel, args.n)
        results.append(r)
        time.sleep(0.5)

    # Підсумкова таблиця
    print(f"\n{'='*55}")
    print(f"{'Метод':<22} {'Обмінів/с':>10} {'mean мкс':>10} {'p99 мкс':>10}")
    print("─" * 55)
    for r in results:
        if "error" in r:
            print(f"{r['method']:<22}  ERROR: {r['error'][:30]}")
        else:
            print(f"{r['method']:<22} {r['throughput']:>10.0f} "
                  f"{r['mean_us']:>10.2f} {r['p99_us']:>10.2f}")
    print(f"{'='*55}\n")

    out = os.path.join(HERE, "..", "results", "task2_results.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Збережено: {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
