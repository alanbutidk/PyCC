# Test19 - Comprehensive stress test
import os
import sys

def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

def is_prime(n):
    if n < 2:
        return 0
    i = 2
    while i * i <= n:
        if n % i == 0:
            return 0
        i += 1
    return 1

def sum_range(start, end):
    total = 0
    for i in range(start, end):
        total += i
    return total

print(fib(0))
print(fib(1))
print(fib(10))

count = 0
for i in range(2, 20):
    if is_prime(i):
        count += 1
        print(i)
print(count)

print(sum_range(1, 101))

x = 255
print(hex(x))
print(bin(x))
print(oct(x))

msg = f"OS: {os.name} | Python: {sys.version}"
print(msg)

a = 10
b = 3
print(a + b, a - b, a * b, a // b, a % b, a ** b)
print(max(a, b), min(a, b), abs(-99))
