# Test22 - Generators (compiled as eager functions)
def first_n(n):
    i = 0
    while i < n:
        yield i
        i += 1

def squares(n):
    i = 0
    while i < n:
        yield i * i
        i += 1

print(first_n(5))
print(squares(4))

def fibonacci_gen(n):
    a = 0
    b = 1
    i = 0
    while i < n:
        yield a
        temp = a + b
        a = b
        b = temp
        i += 1

print(fibonacci_gen(10))
