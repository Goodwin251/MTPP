"""
I/O-bound задача: рекурсивний обхід директорії та підрахунок загальної
кількості слів у всіх текстових файлах.

Реалізовано:
  - генерацію тестового набору з ~1000 .txt файлів у вкладених директоріях;
  - послідовний підрахунок слів;
  - паралельний підрахунок на потоках (ThreadPoolExecutor);
  - паралельний підрахунок на процесах (ProcessPoolExecutor).

I/O-bound задачі чудово масштабуються кількістю потоків, що значно
перевищує кількість фізичних ядер, бо потоки більшу частину часу
заблоковані в очікуванні диску, а GIL відпускається на час системних викликів.
"""

import os
import random
import string
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


def generate_test_files(root: str, n_files: int = 1000,
                        min_words: int = 50, max_words: int = 500,
                        n_subdirs: int = 20, seed: int = 42) -> None:
    """Створює тестовий набір текстових файлів зі випадковим вмістом."""
    rng = random.Random(seed)
    root_p = Path(root)
    root_p.mkdir(parents=True, exist_ok=True)
    subdirs = []
    for i in range(n_subdirs):
        d = root_p / f"dir_{i:03d}"
        d.mkdir(exist_ok=True)
        subdirs.append(d)

    alphabet = string.ascii_lowercase
    for i in range(n_files):
        directory = rng.choice(subdirs)
        path = directory / f"file_{i:05d}.txt"
        n_words = rng.randint(min_words, max_words)
        words = []
        for _ in range(n_words):
            wlen = rng.randint(2, 10)
            words.append("".join(rng.choices(alphabet, k=wlen)))
        # 5–25 слів у рядку, щоб імітувати реальний текст.
        lines = []
        idx = 0
        while idx < n_words:
            line_len = rng.randint(5, 25)
            lines.append(" ".join(words[idx:idx + line_len]))
            idx += line_len
        path.write_text("\n".join(lines), encoding="utf-8")


def count_words_in_file(path: str) -> int:
    """Читає файл і повертає кількість слів у ньому."""
    with open(path, "r", encoding="utf-8") as f:
        return sum(len(line.split()) for line in f)


def list_text_files(root: str) -> list:
    """Рекурсивно повертає список усіх .txt файлів."""
    files = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".txt"):
                files.append(os.path.join(dirpath, fname))
    return files


def count_words_sequential(root: str) -> int:
    files = list_text_files(root)
    return sum(count_words_in_file(f) for f in files)


def count_words_parallel_threads(root: str, n_workers: int) -> int:
    files = list_text_files(root)
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        return sum(ex.map(count_words_in_file, files))


def count_words_parallel_processes(root: str, n_workers: int) -> int:
    files = list_text_files(root)
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        return sum(ex.map(count_words_in_file, files))


def time_it(fn, *args, **kwargs):
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    return res, time.perf_counter() - t0
