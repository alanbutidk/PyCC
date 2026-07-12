# Test21 - Decorators
def my_decorator(func):
    return func

@my_decorator
def greet(name):
    return 42

print(greet(0))

def repeat(func):
    return func

@repeat
def say_hello(x):
    return x + 1

print(say_hello(5))

def staticmethod(func):
    return func

def classmethod(func):
    return func

class MyClass:
    @staticmethod
    def static_add(a, b):
        return a + b

    @classmethod
    def class_mul(cls, a, b):
        return a * b

print(MyClass__static_add(0, 3, 4))
print(MyClass__class_mul(0, 5, 6))
