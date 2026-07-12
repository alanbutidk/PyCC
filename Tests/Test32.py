# Test32 - os module syscalls
import os

print(os.getcwd())
print(os.name)
print(os.sep)
print(os.pathsep)

exists = os.path.exists(".")
print(exists)

cwd = os.getcwd()
print(len(cwd) > 0)

pid = os.getpid()
print(pid > 0)

home = os.getenv("HOME")
print(home)
