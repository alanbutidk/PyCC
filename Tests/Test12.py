# Test12 - Comparisons, bool ops, ternary
a = 10
b = 20

print(a == b)
print(a != b)
print(a < b)
print(a > b)
print(a <= 10)
print(b >= 20)

print(a < b and b > 15)
print(a > b or b > 15)
print(not a == b)

result = "yes" if a < b else "no"
print(result)

x = 5
label = "big" if x > 10 else "medium" if x > 3 else "small"
print(label)
