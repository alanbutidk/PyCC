# Test10 - Functions, return, recursion
def add(a, b):
    return a + b

def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def greet(name):
    return str(name)

print(add(3, 4))
print(add(10, 20))
print(factorial(5))
print(factorial(10))
result = add(factorial(3), factorial(4))
print(result)
