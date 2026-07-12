# PyCC

**PyCC** is a compiler made for python, in python.

PyCC offers **BLAZING FAST** speeds, as it is direct native compilation.

It uses its own *IR*, called PyCC IR, It has a good API, Very small in compiled form.

Heres a example of a average compilation run.

```bash
# Testing with prebuilt tests in Tests\

$ cd src
src/ $ python PyCC.py -o Test ..\Tests\Test1.py -no -npdb
Compiled -> Test
src/ $ ./Test

# Should output:
10 3 13
30
7
3
1

```
---
# PyCCRuntime

**PyCCRuntime** is the runtime that expands runtime features for compiled executables.
It allows features such as:

- Networking/Socket
- More file management

## How to build

### Dependencies

The dependencies needed to build PyCC are:

- Zig/GCC/Clang
- Python (in order to run the build script)


To build PyCC runtime, do these steps:

```bash
cd runtime
runtime/ $ python BuildPyCCRuntime.py

# <RUNTIME BUILD OUTPUT>

# should make a .a or .so OR .dll, .lib, .a etc...
```

And use PyCC with -runtime flag.

---

# LICENSE

**PyCC** uses the GPLv3 License.




