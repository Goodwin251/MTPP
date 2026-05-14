"""
Задача 2: Система обробки фінансових транзакцій.

Конвеєр з трьох етапів:
  1) currency_convert  — конвертація валюти у USD.
  2) cashback          — нарахування cashback за статусом користувача
                          (тут: 20% повернення, якщо user_id парний — простий
                          критерій "VIP").
  3) aggregate         — підрахунок фінальної суми (по продукту або загалом).

Реалізації:
  - sequential: один потік, передаємо transaction'и через функції.
  - Pipeline (threads): три воркер-потоки, з'єднані queue.Queue.
    Кожен етап — окремий thread, що читає вхідну чергу й пише у вихідну.
  - Producer-Consumer (threads): N producer-потоків читають partitions CSV,
    M consumer-потоків паралельно виконують ВЕСЬ конвеєр (3 етапи) над
    кожною транзакцією. Між ними — спільна обмежена queue.Queue.

Чому потоки, а не процеси? Робота над одною транзакцією — це переважно
просте арифметичне округлення + словникове агрегування. Це I/O-bound на
зчитуванні CSV + дуже легка CPU-частина, тому потоки виграють у накладних
витратах. Pickle для процесів був би катастрофою на 200k транзакцій.
"""
import csv
import queue
import threading
from collections import defaultdict


# Курси конвертації у USD (синтетичні, фіксовані)
RATES_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "UAH": 0.024,
    "GBP": 1.27,
    "PLN": 0.25,
}


# ---------------- Етапи конвеєра ----------------
def stage_convert(tx: dict) -> dict:
    rate = RATES_TO_USD[tx["currency"]]
    tx["amount_usd"] = float(tx["amount"]) * rate
    return tx


def stage_cashback(tx: dict) -> dict:
    # Простий "VIP-критерій": парний user_id = 20% cashback
    if int(tx["user_id"]) % 2 == 0:
        tx["cashback_usd"] = tx["amount_usd"] * 0.20
    else:
        tx["cashback_usd"] = 0.0
    tx["net_usd"] = tx["amount_usd"] - tx["cashback_usd"]
    return tx


def stage_aggregate(tx: dict, acc: dict) -> None:
    """Акумулює статистику. acc — спільний dict (під захистом lock'а)."""
    acc["total_amount_usd"] += tx["amount_usd"]
    acc["total_cashback_usd"] += tx["cashback_usd"]
    acc["total_net_usd"] += tx["net_usd"]
    acc["count"] += 1
    acc["by_product"][tx["product_type"]] += tx["net_usd"]


def new_accumulator():
    return {
        "total_amount_usd": 0.0,
        "total_cashback_usd": 0.0,
        "total_net_usd": 0.0,
        "count": 0,
        "by_product": defaultdict(float),
    }


def read_transactions(csv_path: str):
    """Генератор транзакцій з CSV."""
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            yield row


# ---------------- Sequential ----------------
def run_sequential(csv_path: str):
    acc = new_accumulator()
    for tx in read_transactions(csv_path):
        tx = stage_convert(tx)
        tx = stage_cashback(tx)
        stage_aggregate(tx, acc)
    acc["by_product"] = dict(acc["by_product"])
    return acc


# ---------------- Pipeline (3 потоки, по етапу на кожен) ----------------
SENTINEL = object()


def _pipeline_stage(in_q: queue.Queue, out_q: queue.Queue, fn):
    while True:
        tx = in_q.get()
        if tx is SENTINEL:
            out_q.put(SENTINEL)
            return
        out_q.put(fn(tx))


def _pipeline_aggregator(in_q: queue.Queue, acc: dict):
    while True:
        tx = in_q.get()
        if tx is SENTINEL:
            return
        stage_aggregate(tx, acc)


def run_pipeline(csv_path: str, queue_size: int = 1000):
    """Класичний Pipeline: 3 потоки = 3 етапи, послідовно з'єднані."""
    q1 = queue.Queue(maxsize=queue_size)
    q2 = queue.Queue(maxsize=queue_size)
    q3 = queue.Queue(maxsize=queue_size)
    acc = new_accumulator()

    t_conv = threading.Thread(target=_pipeline_stage, args=(q1, q2, stage_convert))
    t_cash = threading.Thread(target=_pipeline_stage, args=(q2, q3, stage_cashback))
    t_agg = threading.Thread(target=_pipeline_aggregator, args=(q3, acc))
    t_conv.start(); t_cash.start(); t_agg.start()

    # Головний потік — producer: читає CSV
    for tx in read_transactions(csv_path):
        q1.put(tx)
    q1.put(SENTINEL)

    t_conv.join(); t_cash.join(); t_agg.join()
    acc["by_product"] = dict(acc["by_product"])
    return acc


# ---------------- Producer-Consumer (N producers, M consumers) ----------------
def _pc_consumer(in_q: queue.Queue, acc: dict, lock: threading.Lock):
    """Consumer виконує ВСІ етапи над транзакцією (currency, cashback, aggregate)."""
    local = new_accumulator()
    while True:
        tx = in_q.get()
        if tx is SENTINEL:
            # злити локальний акумулятор у глобальний
            with lock:
                acc["total_amount_usd"] += local["total_amount_usd"]
                acc["total_cashback_usd"] += local["total_cashback_usd"]
                acc["total_net_usd"] += local["total_net_usd"]
                acc["count"] += local["count"]
                for k, v in local["by_product"].items():
                    acc["by_product"][k] += v
            return
        tx = stage_convert(tx)
        tx = stage_cashback(tx)
        stage_aggregate(tx, local)


def _pc_producer(csv_path: str, start_row: int, end_row: int,
                 out_q: queue.Queue):
    """Кожен producer читає свій діапазон рядків CSV."""
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for i, row in enumerate(r):
            if i < start_row:
                continue
            if i >= end_row:
                return
            out_q.put(row)


def _count_csv_rows(csv_path: str) -> int:
    with open(csv_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # мінус заголовок


def run_producer_consumer(csv_path: str, n_producers: int, n_consumers: int,
                          queue_size: int = 2000):
    q = queue.Queue(maxsize=queue_size)
    acc = new_accumulator()
    lock = threading.Lock()

    # Запускаємо consumer'ів
    consumers = [threading.Thread(target=_pc_consumer, args=(q, acc, lock))
                 for _ in range(n_consumers)]
    for c in consumers:
        c.start()

    # Розрахуємо діапазони для producer'ів
    total = _count_csv_rows(csv_path)
    chunk = total // n_producers
    ranges = [(i * chunk, total if i == n_producers - 1 else (i + 1) * chunk)
              for i in range(n_producers)]

    producers = [threading.Thread(target=_pc_producer,
                                  args=(csv_path, s, e, q))
                 for s, e in ranges]
    for p in producers:
        p.start()
    for p in producers:
        p.join()

    # Сигнал кінця для кожного consumer'а
    for _ in range(n_consumers):
        q.put(SENTINEL)
    for c in consumers:
        c.join()

    acc["by_product"] = dict(acc["by_product"])
    return acc
