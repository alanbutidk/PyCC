# Test28 - Real world stability test
import os
import sys

VERSION = "1.0"
DEBUG = False

def clamp(val, lo, hi):
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val

def lerp(a, b, t):
    return a + (b - a) * t

def is_even(n):
    return n % 2 == 0

def fizzbuzz(n):
    i = 1
    while i <= n:
        if i % 15 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)
        i += 1

def gcd(a, b):
    while b != 0:
        temp = b
        b = a % b
        a = temp
    return a

def lcm(a, b):
    return a * b // gcd(a, b)

print(clamp(5, 0, 10))
print(clamp(-1, 0, 10))
print(clamp(15, 0, 10))
print(lerp(0, 100, 0))
print(lerp(0, 100, 1))
print(is_even(4))
print(is_even(7))
fizzbuzz(15)
print(gcd(48, 18))
print(lcm(4, 6))
print(f"Version: {VERSION}")
print(f"Platform: {os.name}")
