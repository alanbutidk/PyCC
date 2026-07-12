# Test33 - os.path operations
import os

p = os.path.join("usr", "local", "bin")
print(p)

base = os.path.basename("/usr/local/bin/python")
print(base)

dirn = os.path.dirname("/usr/local/bin/python")
print(dirn)

exists = os.path.exists(".")
print(exists)

isfile = os.path.isfile(".")
print(isfile)

isdir = os.path.isdir(".")
print(isdir)

cwd = os.getcwd()
abs_p = os.path.abspath(".")
print(len(abs_p) > 0)
