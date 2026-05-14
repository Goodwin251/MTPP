"""
visualize.py — PNG-зображення знімків стану кристалу.

Генерує:
  - snapshot_XXXX.png   — теплова карта кристалу на кроці XXXX
  - all_snapshots.png   — всі знімки в одній фігурі (огляд еволюції)
  - race_vs_safe.png    — порівняння кількості частинок: race vs safe
  - reproducibility.png — порівняння двох запусків з однаковим seed
"""
import os
import math
from typing import List, Tuple
import matplotlib
matplotlib.use("Agg")   # без GUI — тільки файли
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import config


def _ensure_dir():
    os.makedirs(config.RESULTS_DIR, exist_ok=True)


def save_snapshot(step: int, grid: List[List[int]], vmax: int = None) -> str:
    """Зберігає один знімок як теплову карту."""
    _ensure_dir()
    arr = np.array(grid, dtype=float)
    if vmax is None:
        vmax = max(arr.max(), 1)

    fig, ax = plt.subplots(figsize=(6, 6))
    im = ax.imshow(arr, cmap="hot", vmin=0, vmax=vmax,
                   interpolation="nearest", origin="upper")
    plt.colorbar(im, ax=ax, label="Кількість частинок")
    ax.set_title(f"Кристал — крок {step}\n"
                 f"(сітка {config.GRID_SIZE}×{config.GRID_SIZE}, "
                 f"частинок: {int(arr.sum())})",
                 fontsize=12)
    ax.set_xlabel("Стовпець"); ax.set_ylabel("Рядок")
    path = os.path.join(config.RESULTS_DIR, f"snapshot_{step:04d}.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def save_all_snapshots(snapshots: List[Tuple[int, List[List[int]]]]) -> str:
    """Всі знімки в одній фігурі."""
    _ensure_dir()
    n = len(snapshots)
    cols = min(n, 4)
    rows = math.ceil(n / cols)
    # vmax — спільна шкала для всіх знімків
    vmax = max(max(grid[r][c]
                   for r in range(len(grid))
                   for c in range(len(grid[0])))
               for _, grid in snapshots)
    vmax = max(vmax, 1)

    fig, axes = plt.subplots(rows, cols,
                             figsize=(cols * 3.5, rows * 3.5))
    axes = np.array(axes).flatten()

    for i, (step, grid) in enumerate(snapshots):
        arr = np.array(grid, dtype=float)
        im = axes[i].imshow(arr, cmap="hot", vmin=0, vmax=vmax,
                            interpolation="nearest", origin="upper")
        axes[i].set_title(f"Крок {step}", fontsize=10)
        axes[i].axis("off")

    # Приховуємо зайві підграфіки
    for i in range(len(snapshots), len(axes)):
        axes[i].set_visible(False)

    # Спільна colorbar
    fig.subplots_adjust(right=0.88, hspace=0.3, wspace=0.1)
    cbar_ax = fig.add_axes([0.91, 0.15, 0.02, 0.7])
    fig.colorbar(im, cax=cbar_ax, label="Частинок у клітинці")

    fig.suptitle(
        f"Броунівський рух — еволюція розподілу частинок\n"
        f"Сітка {config.GRID_SIZE}×{config.GRID_SIZE}, "
        f"{config.N_PARTICLES} частинок, seed={config.MASTER_SEED}",
        fontsize=13, y=1.01
    )
    path = os.path.join(config.RESULTS_DIR, "all_snapshots.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def save_race_comparison(race_result: dict, safe_result: dict) -> str:
    """Бар-чарт: кількість частинок до/після у race і safe режимах."""
    _ensure_dir()
    fig, ax = plt.subplots(figsize=(7, 5))

    labels = ["Race (unsafe)\nДО", "Race (unsafe)\nПІСЛЯ",
              "Safe (lock ordering)\nДО", "Safe (lock ordering)\nПІСЛЯ"]
    values = [
        race_result["start_count"], race_result["end_count"],
        safe_result["start_count"], safe_result["end_count"],
    ]
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4"]
    bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor="black")

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5, str(val),
                ha="center", va="bottom", fontsize=11, fontweight="bold")

    expected = race_result["start_count"]
    ax.axhline(expected, color="red", linestyle="--", linewidth=1.5,
               label=f"Очікувана кількість ({expected})")

    ax.set_ylim(0, max(values) * 1.15)
    ax.set_ylabel("Кількість частинок")
    ax.set_title("Race Condition vs Safe: збереження інваріанту частинок", fontsize=12)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    delta_race = race_result["end_count"] - race_result["start_count"]
    ax.annotate(
        f"Δ = {delta_race:+d} (race condition!)" if delta_race != 0
        else "Δ = 0 ✓",
        xy=(0.5, 0.05), xycoords="axes fraction",
        ha="center", fontsize=11,
        color="red" if delta_race != 0 else "green",
        fontweight="bold"
    )

    path = os.path.join(config.RESULTS_DIR, "race_vs_safe.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def save_reproducibility(repro_result: dict,
                         grid1: List[List[int]],
                         grid2: List[List[int]]) -> str:
    """Два знімки поруч + їх різниця (має бути нуль)."""
    _ensure_dir()
    arr1 = np.array(grid1, dtype=float)
    arr2 = np.array(grid2, dtype=float)
    diff = np.abs(arr1 - arr2)
    vmax = max(arr1.max(), arr2.max(), 1)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

    for ax, arr, title in zip(
        axes,
        [arr1, arr2, diff],
        [f"Запуск 1 (seed={repro_result['master_seed']})",
         f"Запуск 2 (seed={repro_result['master_seed']})",
         "Різниця |run1 − run2|"]
    ):
        im = ax.imshow(arr, cmap="hot" if "Різниця" not in title else "Reds",
                       vmin=0, vmax=vmax if "Різниця" not in title else diff.max() + 0.1,
                       interpolation="nearest", origin="upper")
        plt.colorbar(im, ax=ax)
        ax.set_title(title, fontsize=11)
        ax.axis("off")

    identical = repro_result["grids_identical"]
    fig.suptitle(
        f"Відтворюваність симуляції (задача A)\n"
        f"Результат: {'✓ ідентичні' if identical else '✗ різняться'} "
        f"({repro_result['match_pct']}% клітинок збігаються)",
        fontsize=13, color="green" if identical else "red"
    )
    path = os.path.join(config.RESULTS_DIR, "reproducibility.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def save_performance_chart(sim_result: dict) -> str:
    """Інфо-графік: параметри та час виконання симуляції."""
    _ensure_dir()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.axis("off")

    rows = [
        ["Параметр", "Значення"],
        ["Розмір сітки", f"{sim_result['grid_size']}×{sim_result['grid_size']}"],
        ["Частинок / потоків", str(sim_result["n_particles"])],
        ["Кроків симуляції", str(sim_result["n_steps"])],
        ["Master seed", str(sim_result["master_seed"])],
        ["Частинок ДО", str(sim_result["start_count"])],
        ["Частинок ПІСЛЯ", str(sim_result["end_count"])],
        ["Інваріант збережено", "✓ Так" if sim_result["particle_conserved"] else "✗ Ні"],
        ["Знімків зроблено", str(sim_result["n_snapshots"])],
        ["Час виконання", f"{sim_result['elapsed_s']} с"],
    ]

    tbl = ax.table(cellText=rows[1:], colLabels=rows[0],
                   loc="center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1.4, 1.6)

    # Заголовок заливки
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c7bb6")
            cell.set_text_props(color="white", fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f0f4f8")

    ax.set_title("Параметри та результати симуляції", fontsize=13, pad=20)
    path = os.path.join(config.RESULTS_DIR, "performance.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path
