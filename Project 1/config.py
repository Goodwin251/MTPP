# config.py — всі параметри в одному місці
GRID_SIZE    = 50          # розмір сітки N×N
N_PARTICLES  = 200         # кількість частинок (= кількість потоків)
N_STEPS      = 500         # кроків симуляції
SNAPSHOT_EVERY = 50        # знімок кожні K кроків
MASTER_SEED  = 42          # глобальний seed для відтворюваності

# Ймовірності кроку (мають суму 1.0)
P_UP    = 0.25
P_DOWN  = 0.25
P_LEFT  = 0.25
P_RIGHT = 0.25

RESULTS_DIR = "results"    # куди зберігати PNG і JSON
