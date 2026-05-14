"""
Генератор тестових даних для лабораторної роботи №2.

Створює:
  - data/html/  — 1200 HTML-файлів різного розміру для задачі підрахунку тегів;
  - data/numbers.npy   — масив > 1 000 000 чисел (експоненційний розподіл);
  - data/matrix_a.npy  — матриця 1024 x 1024 для множення;
  - data/matrix_b.npy  — матриця 1024 x 1024 для множення;
  - data/transactions.csv — 200 000 фінансових транзакцій для Задачі 2.

Запуск:
    python generate_data.py
"""
import os
import random
import csv
from datetime import datetime, timedelta

import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
HTML_DIR = os.path.join(DATA_DIR, "html")

TAGS = ["div", "span", "p", "a", "img", "h1", "h2", "h3", "ul", "li",
        "table", "tr", "td", "section", "article", "header", "footer", "nav"]


def gen_html_documents(n_files: int = 1200, seed: int = 42) -> None:
    os.makedirs(HTML_DIR, exist_ok=True)
    rnd = random.Random(seed)
    for i in range(n_files):
        # Різний розмір документів: від 20 до 800 тегів
        n_tags = rnd.randint(20, 800)
        parts = ["<!DOCTYPE html><html><head><title>Doc</title></head><body>"]
        for _ in range(n_tags):
            tag = rnd.choice(TAGS)
            parts.append(f"<{tag}>text {rnd.randint(0,9999)}</{tag}>")
        parts.append("</body></html>")
        with open(os.path.join(HTML_DIR, f"doc_{i:05d}.html"), "w",
                  encoding="utf-8") as f:
            f.write("".join(parts))
    print(f"[ok] HTML: {n_files} файлів у {HTML_DIR}")


def gen_numbers(n: int = 2_000_000, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    # Експоненційний розподіл — навмисно не нормальний
    arr = rng.exponential(scale=10.0, size=n).astype(np.float64)
    path = os.path.join(DATA_DIR, "numbers.npy")
    np.save(path, arr)
    print(f"[ok] Масив: {n} чисел -> {path}")


def gen_matrices(size: int = 1024, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((size, size)).astype(np.float64)
    b = rng.standard_normal((size, size)).astype(np.float64)
    np.save(os.path.join(DATA_DIR, "matrix_a.npy"), a)
    np.save(os.path.join(DATA_DIR, "matrix_b.npy"), b)
    print(f"[ok] Матриці: {size}x{size} -> matrix_a.npy, matrix_b.npy")


def gen_transactions(n: int = 200_000, seed: int = 42) -> None:
    rnd = random.Random(seed)
    currencies = ["USD", "EUR", "UAH", "GBP", "PLN"]
    product_types = ["electronics", "food", "clothing", "books", "services"]
    start_date = datetime(2024, 1, 1)
    path = os.path.join(DATA_DIR, "transactions.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "amount", "currency", "date", "product_type"])
        for _ in range(n):
            uid = rnd.randint(1, 50_000)
            amount = round(rnd.uniform(1.0, 5000.0), 2)
            cur = rnd.choice(currencies)
            date = (start_date + timedelta(days=rnd.randint(0, 700))).date()
            ptype = rnd.choice(product_types)
            w.writerow([uid, amount, cur, date.isoformat(), ptype])
    print(f"[ok] Транзакції: {n} рядків -> {path}")


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    gen_html_documents()
    gen_numbers()
    gen_matrices()
    gen_transactions()
    print("[done] Дані згенеровано")
