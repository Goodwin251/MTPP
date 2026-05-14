"""
main.py — головний файл проекту «Броунівський рух».

Запуск:
    python main.py

Що відбувається:
  1. Race Condition demo        → results/race_vs_safe.png
  2. Deadlock demo              → друкує результат у консоль
  3. Основна безпечна симуляція → results/snapshot_XXXX.png
                                  results/all_snapshots.png
                                  results/performance.png
  4. Відтворюваність (задача A) → results/reproducibility.png
  5. Зберігає results/results.json з усіма числами
"""
import json
import os
import time

import config
import problems
import reproducibility
import simulation
import visualize


def section(title: str):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def main():
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    all_results = {}

    # ── 1. RACE CONDITION ────────────────────────────────────────
    section("1. Race Condition — демонстрація")
    race = problems.demonstrate_race_condition(
        n_particles=80, n_steps=200, grid_size=15
    )
    print(f"  Частинок ДО:    {race['start_count']}")
    print(f"  Частинок ПІСЛЯ: {race['end_count']}")
    print(f"  Δ = {race['delta']:+d}  ← {'RACE DETECTED ✗' if race['race_detected'] else 'no race (спробуй ще раз)'}")
    all_results["race_condition"] = race

    # ── 2. DEADLOCK ──────────────────────────────────────────────
    section("2. Deadlock — демонстрація")
    dl = problems.demonstrate_deadlock()
    print(f"  Потік A: {dl['thread_a_result']}")
    print(f"  Потік B: {dl['thread_b_result']}")
    print(f"  Deadlock: {'DETECTED ✗' if dl['deadlock_detected'] else 'не виявлено'}")
    all_results["deadlock"] = dl

    section("2b. Deadlock — вирішення (lock ordering)")
    dl_fix = problems.demonstrate_deadlock_solution()
    print(f"  Потік A: {dl_fix['thread_a_result']}")
    print(f"  Потік B: {dl_fix['thread_b_result']}")
    print(f"  Deadlock: {'є' if dl_fix['deadlock_detected'] else 'відсутній ✓'}")
    all_results["deadlock_solution"] = dl_fix

    # Графік race vs safe (safe буде після симуляції)
    # — спочатку запустимо симуляцію

    # ── 3. ОСНОВНА СИМУЛЯЦІЯ ─────────────────────────────────────
    section("3. Основна симуляція (safe, seed-based RNG)")
    print(f"  Сітка: {config.GRID_SIZE}×{config.GRID_SIZE}, "
          f"частинок: {config.N_PARTICLES}, кроків: {config.N_STEPS}")
    print("  Запуск...", flush=True)

    sim = simulation.SafeSimulation()
    sim_result = sim.run()

    print(f"  Частинок ДО:    {sim_result['start_count']}")
    print(f"  Частинок ПІСЛЯ: {sim_result['end_count']}")
    print(f"  Інваріант: {'✓ збережено' if sim_result['particle_conserved'] else '✗ порушено!'}")
    print(f"  Знімків: {sim_result['n_snapshots']}")
    print(f"  Час: {sim_result['elapsed_s']} с")
    all_results["simulation"] = sim_result

    # Зберігаємо кожен знімок окремо
    print("\n  Зберігаємо знімки...")
    vmax = max(
        max(sim.snapshots[i][1][r][c]
            for r in range(config.GRID_SIZE)
            for c in range(config.GRID_SIZE))
        for i in range(len(sim.snapshots))
    )
    vmax = max(vmax, 1)
    saved = []
    for step, grid in sim.snapshots:
        p = visualize.save_snapshot(step, grid, vmax=vmax)
        saved.append(p)
        print(f"    {p}")

    # Всі знімки разом
    p = visualize.save_all_snapshots(sim.snapshots)
    print(f"  Зведений: {p}")

    # Таблиця параметрів
    p = visualize.save_performance_chart(sim_result)
    print(f"  Параметри: {p}")

    # Race vs Safe графік
    p = visualize.save_race_comparison(race, sim_result)
    print(f"  Race vs Safe: {p}")

    # ── 4. ВІДТВОРЮВАНІСТЬ (задача A) ────────────────────────────
    section("4. Відтворюваність — два запуски з однаковим seed")
    print("  Запуск (може зайняти ~30 с)...", flush=True)

    repro = reproducibility.demonstrate_reproducibility()
    print(f"  Запуск 1: {repro['run1_elapsed_s']} с")
    print(f"  Запуск 2: {repro['run2_elapsed_s']} с")
    print(f"  Сітки ідентичні: {'✓ ТАК' if repro['grids_identical'] else '✗ НІ'}")
    print(f"  Збігів клітинок: {repro['matching_cells']}/{repro['total_cells']} "
          f"({repro['match_pct']}%)")
    all_results["reproducibility"] = repro

    # Для візуалізації reproducibility нам потрібні обидві сітки
    # Запускаємо ще раз (швидко — маленька конфіг)
    from reproducibility import run_reproducible
    g1, _ = run_reproducible(config.MASTER_SEED, 20, 50, 200)
    g2, _ = run_reproducible(config.MASTER_SEED, 20, 50, 200)
    p = visualize.save_reproducibility(repro, g1, g2)
    print(f"  Графік: {p}")

    # ── 5. ЗБЕРЕЖЕННЯ JSON ───────────────────────────────────────
    section("5. Збереження результатів")
    json_path = os.path.join(config.RESULTS_DIR, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  JSON: {json_path}")

    # Підсумок
    section("ПІДСУМОК")
    print(f"  Race condition виявлено:  {'✓' if race['race_detected'] else '—'}")
    print(f"  Deadlock виявлено:        {'✓' if dl['deadlock_detected'] else '—'}")
    print(f"  Інваріант симуляції:      {'✓' if sim_result['particle_conserved'] else '✗'}")
    print(f"  Відтворюваність (seed A): {'✓' if repro['grids_identical'] else '✗'}")
    print(f"\n  Файли у папці: {os.path.abspath(config.RESULTS_DIR)}/")
    for fn in sorted(os.listdir(config.RESULTS_DIR)):
        print(f"    {fn}")


if __name__ == "__main__":
    main()
