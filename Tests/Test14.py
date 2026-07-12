# Test14 - try/except/finally, assert, raise
try:
    x = 10
    print(x)
except:
    print("error")
finally:
    print("finally ran")

try:
    y = 20
    print(y)
except:
    print("error2")

assert 1 == 1
print("assert passed")

assert 2 > 1, "math is broken"
print("assert with msg passed")
