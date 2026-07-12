# Test20 - *args, default args, closures, nonlocal
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b

def apply(func, a, b):
    return add(a, b)

print(add(3, 4))
print(multiply(5, 6))
print(apply(add, 10, 20))

def counter_start(start):
    count = start
    def increment(n):
        return count + n
    return increment

inc = counter_start(10)
print(inc(5))

def power(base, exp):
    result = 1
    i = 0
    while i < exp:
        result = result * base
        i += 1
    return result

print(power(2, 8))
print(power(3, 4))
