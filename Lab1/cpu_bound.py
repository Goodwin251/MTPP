"""
CPU-bound задачі для Лабораторної роботи №1.

Реалізовано три CPU-bound задачі:
  1) Обчислення числа π методом Монте-Карло.
  2) Факторизація великих чисел методом пробного ділення.
  3) Обчислення простих чисел в заданому діапазоні (тест простоти).

Для кожної задачі реалізовано три варіанти виконання:
  - послідовний (sequential);
  - паралельний на потоках (ThreadPoolExecutor);
  - паралельний на процесах (ProcessPoolExecutor).

ProcessPool використовується для того, щоб обійти обмеження GIL у CPython
для CPU-інтенсивних задач.
"""

import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


# ---------------------------------------------------------------------------
# 1) Обчислення π методом Монте-Карло
# ---------------------------------------------------------------------------

def monte_carlo_pi_chunk(n_points: int) -> int:
    """Кидаємо n_points точок у квадрат [0,1] x [0,1] і повертаємо кількість
    точок, що потрапили у чверть кола радіусом 1."""
    rng = random.Random()
    hits = 0
    for _ in range(n_points):
        x = rng.random()
        y = rng.random()
        if x * x + y * y <= 1.0:
            hits += 1
    return hits


def pi_sequential(total_points: int) -> float:
    hits = monte_carlo_pi_chunk(total_points)
    return 4.0 * hits / total_points


def pi_parallel_threads(total_points: int, n_workers: int) -> float:
    chunk = total_points // n_workers
    sizes = [chunk] * n_workers
    sizes[-1] += total_points - chunk * n_workers
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        hits = sum(ex.map(monte_carlo_pi_chunk, sizes))
    return 4.0 * hits / total_points


def pi_parallel_processes(total_points: int, n_workers: int) -> float:
    chunk = total_points // n_workers
    sizes = [chunk] * n_workers
    sizes[-1] += total_points - chunk * n_workers
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        hits = sum(ex.map(monte_carlo_pi_chunk, sizes))
    return 4.0 * hits / total_points


# ---------------------------------------------------------------------------
# 2) Факторизація великих чисел (пробне ділення)
# ---------------------------------------------------------------------------

def factorize(n: int) -> list:
    """Повертає список простих множників числа n."""
    factors = []
    # Виокремлюємо двійки.
    while n % 2 == 0:
        factors.append(2)
        n //= 2
    # Перевіряємо непарні дільники до sqrt(n).
    i = 3
    while i * i <= n:
        while n % i == 0:
            factors.append(i)
            n //= i
        i += 2
    if n > 1:
        factors.append(n)
    return factors


def factor_sequential(numbers):
    return [factorize(n) for n in numbers]


def factor_parallel_threads(numbers, n_workers: int):
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        return list(ex.map(factorize, numbers))


def factor_parallel_processes(numbers, n_workers: int):
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        return list(ex.map(factorize, numbers))


# ---------------------------------------------------------------------------
# 3) Підрахунок простих чисел у діапазоні
# ---------------------------------------------------------------------------

def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    limit = int(math.isqrt(n))
    while i <= limit:
        if n % i == 0:
            return False
        i += 2
    return True


def count_primes_in_range(args):
    start, end = args
    return sum(1 for n in range(start, end) if is_prime(n))


def primes_sequential(low: int, high: int) -> int:
    return count_primes_in_range((low, high))


def primes_parallel_threads(low: int, high: int, n_workers: int) -> int:
    step = (high - low) // n_workers
    ranges = []
    for i in range(n_workers):
        s = low + i * step
        e = high if i == n_workers - 1 else s + step
        ranges.append((s, e))
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        return sum(ex.map(count_primes_in_range, ranges))


def primes_parallel_processes(low: int, high: int, n_workers: int) -> int:
    step = (high - low) // n_workers
    ranges = []
    for i in range(n_workers):
        s = low + i * step
        e = high if i == n_workers - 1 else s + step
        ranges.append((s, e))
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        return sum(ex.map(count_primes_in_range, ranges))


# ---------------------------------------------------------------------------
# Допоміжна функція вимірювання часу
# ---------------------------------------------------------------------------

def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    t1 = time.perf_counter()
    return result, t1 - t0
