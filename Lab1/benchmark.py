"""
Основний бенчмарк для Лабораторної роботи №1.

Запускає всі CPU-, Memory- та I/O-bound задачі у послідовному та
паралельному режимах (потоки і процеси) з різною кількістю воркерів,
вимірює час виконання, обчислює прискорення (speedup) та зберігає
результати у CSV та JSON.
"""

import json
import os
import sys
import csv
import time
import multiprocessing as mp

import numpy as np

# Додаємо поточну директорію до шляху імпортів.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cpu_bound import (
    pi_sequential, pi_parallel_threads, pi_parallel_processes,
    factorize, factor_sequential, factor_parallel_threads, factor_parallel_processes,
    primes_sequential, primes_parallel_threads, primes_parallel_processes,
    timed,
)
from memory_bound import (
    transpose_sequential, transpose_parallel_threads, time_it as mem_time_it,
)
from io_bound import (
    generate_test_files, count_words_sequential,
    count_words_parallel_threads, count_words_parallel_processes,
    time_it as io_time_it,
)


RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Кількості воркерів, для яких будемо запускати паралельні версії.
WORKER_COUNTS = [1, 2, 4, 8]

# Параметри задач. Підбираємо так, щоб бенчмарк відпрацював розумний час на
# слабкому 1-ядерному контейнері. На сильнішій машині рекомендовано підняти
# MONTE_CARLO_POINTS до 50–100M і MATRIX_SIZE до 10000.
MONTE_CARLO_POINTS = 8_000_000
FACTOR_NUMBERS = [
    982_451_653, 999_999_937, 982_451_649, 1_000_000_007,
    1_000_000_009, 999_999_733, 982_451_651, 1_000_000_021,
    999_983 * 999_961, 999_983 * 999_979,
] * 4  # 40 чисел
PRIMES_RANGE = (1, 500_000)
MATRIX_SIZE = 3000
IO_FILES_COUNT = 1000


def banner(text: str):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def run_pi():
    banner("CPU-bound: Monte Carlo π")
    results = {"sequential": None, "threads": {}, "processes": {}}

    pi_val, t = timed(pi_sequential, MONTE_CARLO_POINTS)
    print(f"Sequential: π≈{pi_val:.6f}, time={t:.3f}s")
    results["sequential"] = t

    for n in WORKER_COUNTS:
        pi_val, t = timed(pi_parallel_threads, MONTE_CARLO_POINTS, n)
        print(f"Threads(n={n}): π≈{pi_val:.6f}, time={t:.3f}s")
        results["threads"][n] = t

    for n in WORKER_COUNTS:
        pi_val, t = timed(pi_parallel_processes, MONTE_CARLO_POINTS, n)
        print(f"Processes(n={n}): π≈{pi_val:.6f}, time={t:.3f}s")
        results["processes"][n] = t

    return results


def run_factor():
    banner("CPU-bound: Factorization")
    results = {"sequential": None, "threads": {}, "processes": {}}

    _, t = timed(factor_sequential, FACTOR_NUMBERS)
    print(f"Sequential: time={t:.3f}s")
    results["sequential"] = t

    for n in WORKER_COUNTS:
        _, t = timed(factor_parallel_threads, FACTOR_NUMBERS, n)
        print(f"Threads(n={n}): time={t:.3f}s")
        results["threads"][n] = t

    for n in WORKER_COUNTS:
        _, t = timed(factor_parallel_processes, FACTOR_NUMBERS, n)
        print(f"Processes(n={n}): time={t:.3f}s")
        results["processes"][n] = t

    return results


def run_primes():
    banner("CPU-bound: Primes in range")
    results = {"sequential": None, "threads": {}, "processes": {}}

    low, high = PRIMES_RANGE
    cnt, t = timed(primes_sequential, low, high)
    print(f"Sequential: count={cnt}, time={t:.3f}s")
    results["sequential"] = t

    for n in WORKER_COUNTS:
        cnt, t = timed(primes_parallel_threads, low, high, n)
        print(f"Threads(n={n}): count={cnt}, time={t:.3f}s")
        results["threads"][n] = t

    for n in WORKER_COUNTS:
        cnt, t = timed(primes_parallel_processes, low, high, n)
        print(f"Processes(n={n}): count={cnt}, time={t:.3f}s")
        results["processes"][n] = t

    return results


def run_transpose():
    banner(f"Memory-bound: Transpose {MATRIX_SIZE}x{MATRIX_SIZE}")
    results = {"sequential": None, "threads": {}}

    rng = np.random.default_rng(42)
    M = rng.random((MATRIX_SIZE, MATRIX_SIZE), dtype=np.float64)

    _, t = mem_time_it(transpose_sequential, M)
    print(f"Sequential: time={t:.3f}s")
    results["sequential"] = t

    for n in WORKER_COUNTS:
        _, t = mem_time_it(transpose_parallel_threads, M, n)
        print(f"Threads(n={n}): time={t:.3f}s")
        results["threads"][n] = t

    return results


def run_io():
    banner(f"I/O-bound: word count over {IO_FILES_COUNT} files")
    results = {"sequential": None, "threads": {}, "processes": {}}

    root = os.path.join(RESULTS_DIR, "..", "test_files")
    root = os.path.abspath(root)
    if not os.path.isdir(root) or len(os.listdir(root)) == 0:
        print(f"Generating {IO_FILES_COUNT} test files in {root} ...")
        generate_test_files(root, n_files=IO_FILES_COUNT)

    cnt, t = io_time_it(count_words_sequential, root)
    print(f"Sequential: total_words={cnt}, time={t:.3f}s")
    results["sequential"] = t

    io_worker_counts = [1, 2, 4, 8, 16, 32]
    results["threads"] = {}
    for n in io_worker_counts:
        cnt, t = io_time_it(count_words_parallel_threads, root, n)
        print(f"Threads(n={n}): total_words={cnt}, time={t:.3f}s")
        results["threads"][n] = t

    for n in WORKER_COUNTS:
        cnt, t = io_time_it(count_words_parallel_processes, root, n)
        print(f"Processes(n={n}): total_words={cnt}, time={t:.3f}s")
        results["processes"][n] = t

    return results


def save_results(all_results: dict):
    json_path = os.path.join(RESULTS_DIR, "benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved JSON: {json_path}")

    csv_path = os.path.join(RESULTS_DIR, "benchmark_results.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task", "mode", "workers", "time_s", "speedup"])
        for task_name, task_res in all_results.items():
            if task_name.startswith("_"):
                continue
            base = task_res["sequential"]
            w.writerow([task_name, "sequential", 1, f"{base:.4f}", "1.00"])
            for n, t in task_res.get("threads", {}).items():
                w.writerow([task_name, "threads", n, f"{t:.4f}",
                            f"{base / t:.2f}"])
            for n, t in task_res.get("processes", {}).items():
                w.writerow([task_name, "processes", n, f"{t:.4f}",
                            f"{base / t:.2f}"])
    print(f"Saved CSV: {csv_path}")


def main():
    mp.set_start_method("spawn", force=True)
    all_results = {}
    all_results["pi"] = run_pi()
    all_results["factor"] = run_factor()
    all_results["primes"] = run_primes()
    all_results["transpose"] = run_transpose()
    all_results["io_words"] = run_io()

    all_results["_meta"] = {
        "cpu_count_logical": os.cpu_count(),
        "monte_carlo_points": MONTE_CARLO_POINTS,
        "factor_numbers_count": len(FACTOR_NUMBERS),
        "primes_range": list(PRIMES_RANGE),
        "matrix_size": MATRIX_SIZE,
        "io_files_count": IO_FILES_COUNT,
        "worker_counts": WORKER_COUNTS,
    }

    save_results(all_results)


if __name__ == "__main__":
    main()
