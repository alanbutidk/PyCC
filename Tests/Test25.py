# Test25 - print sep/end, __name__ guard, global
x = 10
y = 20
z = 30

print(x, y, z, sep=", ")
print(x, y, z, sep=" | ")
print("no newline", end=" ")
print("same line")
print("a", "b", "c", sep="-", end="!\n")

if __name__ == "__main__":
    print("main guard works")
    print(__name__)

global_val = 99
print(global_val)
