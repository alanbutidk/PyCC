# PyCCRuntime

Native runtime library for PyCC compiled binaries.

## What it provides

- Full POSIX syscalls: `open`, `read`, `write`, `close`, `lseek`, `stat`, `chmod`, `chown`, `symlink`, `link`, `readlink`, `truncate`, `dup`, `dup2`, `pipe`, `fcntl`
- Directory ops: `mkdir`, `rmdir`, `makedirs`, `listdir`, `getcwd`, `chdir`, `realpath`, `basename`, `dirname`
- Process: `fork`, `exec`, `waitpid`, `system`, `popen`, `getpid`, `getppid`, `exit`, `abort`
- Environment: `getenv`, `setenv`, `unsetenv`
- Signals: `kill`, `raise`, `signal_ignore`, `signal_default`
- Sockets: `socket`, `bind`, `listen`, `accept`, `connect`, `send`, `recv`, `setsockopt`, `gethostname`, `gethostbyname`, select/poll
- Threading: `pthread_create/join/detach`, `mutex`, `cond`, `rwlock` (POSIX) / `CreateThread`, `CriticalSection`, `SRWLOCK` (Windows)
- Memory mapping: `mmap`, `munmap`, `mprotect`, `mmap_file`
- Dynamic loading: `dlopen`, `dlsym`, `dlclose`
- Crypto: SHA-256, CRC32, FNV-1a, base64, random bytes
- String utils: `upper`, `lower`, `strip`, `replace`, `split`, `join`, `startswith`, `endswith`, `find`, `count`, `slice`, `format`, `zfill`, `center`, `ljust`, `rjust`, `isdigit`, `isalpha`, etc.
- List: dynamic array with `append`, `pop`, `sort`, `reverse`, `index`, `count`
- Dict: hashmap with `set`, `get`, `has`, `del`, `keys`, `values`, `update`, `copy`
- Time: `time_now`, `sleep`, `sleep_ms`, `time_str`, `time_format`
- Math: `pow`, `sqrt`, `log`, `log2`, `log10`, `gcd`, `lcm`, `hypot`
- File I/O: `fopen`, `fclose`, `fread`, `fwrite`, `fgets`, `fputs`, `freadall`, `fwriteall`, `fappend`
- Windows extras: `CreateFile`, `ReadFile`, `WriteFile`, `CreateProcess`, `Registry`, `GetTempPath`, `GetUserName`, `MessageBox`
- CPython embedding (optional): `getattr`, `setattr`, `hasattr`, `isinstance`, `eval`, `exec`, `import`, full Python object access

## Build

```bash
# Build for host platform
python BuildPyCCRuntime.py

# Build for specific arch
python BuildPyCCRuntime.py --arch aarch64 --os Linux

# Build all platforms
python BuildPyCCRuntime.py --all

# Build with CPython embedding (requires Python dev headers)
python BuildPyCCRuntime.py --cpython

# Clean
python BuildPyCCRuntime.py --clean
```

Output goes to `runtime/lib/`.

## Usage with PyCC

```bash
# Compile with runtime linked
python PyCC.py myfile.py -runtime

# Compile with runtime + CPython (full setattr/getattr/isinstance support)
python PyCC.py myfile.py -runtime

# Cross-compile
python PyCC.py myfile.py --arch aarch64 --target-os Linux --ir
```

## Supported Architectures

| Arch | Linux | Windows | macOS |
|------|-------|---------|-------|
| x86_64 | ✓ | ✓ | ✓ |
| aarch64 | ✓ | ✓ | ✓ (Apple Silicon) |
| x86 | ✓ | ✓ | - |
| riscv64 | ✓ | - | - |
| armv7 | ✓ | - | - |
