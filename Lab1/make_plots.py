"""
Генерує графіки часу виконання та прискорення (speedup) для кожної задачі
на основі benchmark_results.json.
"""

import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)


TASK_TITLES = {
    "pi": "CPU-bound: π методом Монте-Карло",
    "factor": "CPU-bound: факторизація чисел",
    "primes": "CPU-bound: прості числа у діапазоні",
    "transpose": "Memory-bound: транспонування матриці",
    "io_words": "I/O-bound: підрахунок слів у файлах",
}


def plot_task(task_key: str, task_data: dict):
    title = TASK_TITLES.get(task_key, task_key)
    base = task_data["sequential"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # ---- Час виконання
    ax = axes[0]
    if "threads" in task_data and task_data["threads"]:
        ks = sorted(int(k) for k in task_data["threads"].keys())
        ts = [task_data["threads"][str(k) if isinstance(list(task_data["threads"].keys())[0], str) else k] for k in ks]
        ax.plot(ks, ts, marker="o", linewidth=2, label="Потоки (Threads)")
    if "processes" in task_data and task_data["processes"]:
        ks = sorted(int(k) for k in task_data["processes"].keys())
        ts = [task_data["processes"][str(k) if isinstance(list(task_data["processes"].keys())[0], str) else k] for k in ks]
        ax.plot(ks, ts, marker="s", linewidth=2, label="Процеси (Processes)")
    ax.axhline(base, color="red", linestyle="--", label=f"Послідовно ({base:.3f} c)")
    ax.set_xlabel("Кількість воркерів")
    ax.set_ylabel("Час виконання, с")
    ax.set_title(f"{title}\nЧас виконання")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_xscale("log", base=2)

    # ---- Прискорення
    ax = axes[1]
    if "threads" in task_data and task_data["threads"]:
        ks = sorted(int(k) for k in task_data["threads"].keys())
        sps = [base / task_data["threads"][str(k) if isinstance(list(task_data["threads"].keys())[0], str) else k] for k in ks]
        ax.plot(ks, sps, marker="o", linewidth=2, label="Потоки")
    if "processes" in task_data and task_data["processes"]:
        ks = sorted(int(k) for k in task_data["processes"].keys())
        sps = [base / task_data["processes"][str(k) if isinstance(list(task_data["processes"].keys())[0], str) else k] for k in ks]
        ax.plot(ks, sps, marker="s", linewidth=2, label="Процеси")
    # Ідеальне лінійне прискорення
    max_k = max(ks) if ks else 8
    ax.plot([1, max_k], [1, max_k], color="gray", linestyle=":", label="Ідеальне (лінійне)")
    ax.axhline(1.0, color="red", linestyle="--", alpha=0.5)
    ax.set_xlabel("Кількість воркерів")
    ax.set_ylabel("Прискорення (Speedup)")
    ax.set_title(f"{title}\nПрискорення відносно послідовної версії")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_xscale("log", base=2)

    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, f"{task_key}.png")
    plt.savefig(out, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_overall_speedup(all_results: dict):
    """Один загальний графік найкращих прискорень для кожної задачі."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for task_key, task_data in all_results.items():
        if task_key.startswith("_"):
            continue
        if "threads" not in task_data:
            continue
        base = task_data["sequential"]
        ks = sorted(int(k) for k in task_data["threads"].keys())
        sps = [base / task_data["threads"][str(k) if isinstance(list(task_data["threads"].keys())[0], str) else k] for k in ks]
        ax.plot(ks, sps, marker="o", linewidth=2,
                label=TASK_TITLES.get(task_key, task_key))

    ax.axhline(1.0, color="red", linestyle="--", alpha=0.5, label="Без прискорення")
    ax.set_xlabel("Кількість потоків")
    ax.set_ylabel("Прискорення (Speedup)")
    ax.set_title("Порівняння прискорення (Threads) для всіх задач")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    ax.set_xscale("log", base=2)
    plt.tight_layout()
    out = os.path.join(PLOTS_DIR, "overall_threads_speedup.png")
    plt.savefig(out, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def main():
    with open(os.path.join(RESULTS_DIR, "benchmark_results.json"), "r", encoding="utf-8") as f:
        results = json.load(f)

    for task_key, task_data in results.items():
        if task_key.startswith("_"):
            continue
        plot_task(task_key, task_data)

    plot_overall_speedup(results)


if __name__ == "__main__":
    main()
