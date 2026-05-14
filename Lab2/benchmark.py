"""
Головний benchmark-скрипт для Лабораторної роботи №2.

Запускає всі задачі та всі патерни з різною кількістю воркерів,
вимірює час, зберігає результат у results.json.

Запуск:
    python benchmark.py                # повний прогін
    python benchmark.py --quick        # швидкий (по одному запуску на конфігурацію)
    python benchmark.py --task task1_html   # лише одна задача

Доступні задачі: task1_html, task1_array, task1_matrix, task2_transactions

Worker конфігурації: 1, 2, 4, 6, 8, 12 (підбираються під CPU).
"""
import argparse
import json
import os
import sys
import time
from statistics import median

import numpy as np

# Обмежуємо BLAS до 1 потоку ДО імпорту numpy у воркерах.
# Це робить порівняння чесним для задачі множення матриць.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import task1_html
import task1_array
import task1_matrix
import task2_transactions


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
HTML_DIR = os.path.join(DATA_DIR, "html")
NUMBERS_PATH = os.path.join(DATA_DIR, "numbers.npy")
MATRIX_A_PATH = os.path.join(DATA_DIR, "matrix_a.npy")
MATRIX_B_PATH = os.path.join(DATA_DIR, "matrix_b.npy")
TRANSACTIONS_PATH = os.path.join(DATA_DIR, "transactions.csv")

WORKER_CONFIGS = [1, 2, 4, 6, 8, 12]


def time_run(fn, *args, repeats: int = 3, **kwargs):
    """Запускає fn кілька разів, повертає медіану часу і результат."""
    times = []
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        times.append(time.perf_counter() - t0)
    return median(times), result


# ----------------- Задача 1.1: HTML -----------------
def bench_task1_html(repeats: int):
    print("\n=== Задача 1.1: підрахунок HTML-тегів ===")
    paths = task1_html.collect_paths(HTML_DIR)
    print(f"  Файлів: {len(paths)}")

    results = {"task": "task1_html", "n_files": len(paths), "runs": []}

    # Sequential
    t, _ = time_run(task1_html.run_sequential, paths, repeats=repeats)
    print(f"  [seq]                {t:.4f} s")
    results["runs"].append({"pattern": "sequential", "workers": 1, "time": t})

    for n in WORKER_CONFIGS:
        for name, fn in [
            ("map_reduce", task1_html.run_map_reduce),
            ("fork_join", task1_html.run_fork_join),
            ("worker_pool", task1_html.run_worker_pool),
        ]:
            t, _ = time_run(fn, paths, n, repeats=repeats)
            print(f"  [{name:12s} w={n:2d}]  {t:.4f} s")
            results["runs"].append({"pattern": name, "workers": n, "time": t})
    return results


# ----------------- Задача 1.2: масив -----------------
def bench_task1_array(repeats: int):
    print("\n=== Задача 1.2: статистика масиву ===")
    arr = np.load(NUMBERS_PATH)
    print(f"  Чисел: {arr.size:,}")

    results = {"task": "task1_array", "n_numbers": int(arr.size), "runs": []}

    t, _ = time_run(task1_array.run_sequential, arr, repeats=repeats)
    print(f"  [seq]                {t:.4f} s")
    results["runs"].append({"pattern": "sequential", "workers": 1, "time": t})

    for n in WORKER_CONFIGS:
        for name, fn in [
            ("map_reduce", task1_array.run_map_reduce),
            ("fork_join", task1_array.run_fork_join),
            ("worker_pool", task1_array.run_worker_pool),
        ]:
            t, _ = time_run(fn, arr, n, repeats=repeats)
            print(f"  [{name:12s} w={n:2d}]  {t:.4f} s")
            results["runs"].append({"pattern": name, "workers": n, "time": t})
    return results


# ----------------- Задача 1.3: матриці -----------------
def bench_task1_matrix(repeats: int):
    print("\n=== Задача 1.3: множення матриць ===")
    A = np.load(MATRIX_A_PATH)
    B = np.load(MATRIX_B_PATH)
    print(f"  Розмір: {A.shape} x {B.shape}")

    results = {"task": "task1_matrix",
               "shape_a": list(A.shape), "shape_b": list(B.shape),
               "runs": []}

    t, _ = time_run(task1_matrix.run_sequential, A, B, repeats=repeats)
    print(f"  [seq]                {t:.4f} s")
    results["runs"].append({"pattern": "sequential", "workers": 1, "time": t})

    for n in WORKER_CONFIGS:
        for name, fn in [
            ("map_reduce", task1_matrix.run_map_reduce),
            ("fork_join", task1_matrix.run_fork_join),
            ("worker_pool", task1_matrix.run_worker_pool),
        ]:
            t, _ = time_run(fn, A, B, n, repeats=repeats)
            print(f"  [{name:12s} w={n:2d}]  {t:.4f} s")
            results["runs"].append({"pattern": name, "workers": n, "time": t})
    return results


# ----------------- Задача 2: транзакції -----------------
def bench_task2_transactions(repeats: int):
    print("\n=== Задача 2: фінансові транзакції ===")
    n_rows = task2_transactions._count_csv_rows(TRANSACTIONS_PATH)
    print(f"  Транзакцій: {n_rows:,}")

    results = {"task": "task2_transactions", "n_transactions": n_rows, "runs": []}

    t, acc = time_run(task2_transactions.run_sequential, TRANSACTIONS_PATH,
                      repeats=repeats)
    print(f"  [seq]                          {t:.4f} s")
    print(f"     total_net_usd={acc['total_net_usd']:.2f}, count={acc['count']}")
    results["runs"].append({"pattern": "sequential", "workers": 1, "time": t})

    # Pipeline — фіксована структура з 3 потоків
    t, _ = time_run(task2_transactions.run_pipeline, TRANSACTIONS_PATH,
                    repeats=repeats)
    print(f"  [pipeline 3-stages]            {t:.4f} s")
    results["runs"].append({"pattern": "pipeline", "workers": 3, "time": t})

    # Producer-Consumer: різні комбінації
    for n_prod in [1, 2, 4]:
        for n_cons in [1, 2, 4, 8]:
            t, _ = time_run(task2_transactions.run_producer_consumer,
                            TRANSACTIONS_PATH, n_prod, n_cons,
                            repeats=repeats)
            print(f"  [prod-cons P={n_prod} C={n_cons}]         {t:.4f} s")
            results["runs"].append({
                "pattern": "producer_consumer",
                "producers": n_prod, "consumers": n_cons,
                "workers": n_prod + n_cons, "time": t,
            })

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["task1_html", "task1_array",
                                       "task1_matrix", "task2_transactions",
                                       "all"], default="all")
    ap.add_argument("--repeats", type=int, default=3,
                    help="Кількість повторів кожного запуску (медіана)")
    ap.add_argument("--quick", action="store_true",
                    help="Швидкий прогін: repeats=1")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "..", "results.json"))
    args = ap.parse_args()

    repeats = 1 if args.quick else args.repeats

    # Перевіряємо наявність даних
    if not os.path.isdir(HTML_DIR) or not os.path.isfile(NUMBERS_PATH):
        print("[!] Дані не згенеровано. Запусти спочатку: python generate_data.py")
        sys.exit(1)

    # Системна інформація
    import platform
    info = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "numpy": np.__version__,
        "repeats": repeats,
        "worker_configs": WORKER_CONFIGS,
    }
    print("System:", info)

    all_results = {"system": info, "tasks": []}

    tasks = ["task1_html", "task1_array", "task1_matrix", "task2_transactions"]
    if args.task != "all":
        tasks = [args.task]

    for t in tasks:
        if t == "task1_html":
            all_results["tasks"].append(bench_task1_html(repeats))
        elif t == "task1_array":
            all_results["tasks"].append(bench_task1_array(repeats))
        elif t == "task1_matrix":
            all_results["tasks"].append(bench_task1_matrix(repeats))
        elif t == "task2_transactions":
            all_results["tasks"].append(bench_task2_transactions(repeats))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[ok] Результати збережено: {args.out}")


if __name__ == "__main__":
    main()
