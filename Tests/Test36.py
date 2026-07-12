# Test36 - file I/O low level with os.open/os.read/os.write/os.close
import os

fd = os.open("pycc_lowlevel_test.txt", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
os.write(fd, "Low level write!\n")
os.close(fd)

fd = os.open("pycc_lowlevel_test.txt", os.O_RDONLY)
data = os.read(fd, 1024)
os.close(fd)
print(data)

os.remove("pycc_lowlevel_test.txt")
print("low level IO done")
