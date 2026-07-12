/**
 * PyCCRuntime.c - PyCC Native Runtime Library Implementation
 * Compile with BuildPyCCRuntime.py
 */
#include "PyCCRuntime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>
#include <time.h>
#include <errno.h>
#include <ctype.h>
#include <stdint.h>

#ifdef PYCC_POSIX
  #include <unistd.h>
  #include <fcntl.h>
  #include <sys/stat.h>
  #include <sys/types.h>
  #include <sys/wait.h>
  #include <sys/socket.h>
  #include <sys/mman.h>
  #include <sys/select.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  #include <dirent.h>
  #include <pthread.h>
  #include <signal.h>
  #include <dlfcn.h>
  #include <libgen.h>
  #include <limits.h>
#endif

#ifdef PYCC_WIN
  #define WIN32_LEAN_AND_MEAN
  #include <windows.h>
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #include <io.h>
  #include <direct.h>
  #include <sys/types.h>
  #include <sys/stat.h>   /* mingw has this — gives us struct stat, S_ISREG, S_ISDIR */
  #include <limits.h>
  #include <signal.h>     /* raise(), signal(), SIG_IGN, SIG_DFL -- these were
                              only ever included on the POSIX branch above, so
                              the Windows build failed with "implicit
                              declaration" errors on every use below
                              (pycc_raise_sig, pycc_signal_ignore/default). */
  #include <process.h>    /* _execv/_execvp -- mingw/UCRT's process-spawning
                              declarations live here, not in unistd.h (which
                              doesn't exist on Windows); without this include
                              _execv/_execvp had no declaration in scope. */
  /* PATH_MAX: mingw defines it in limits.h as 260; only define if missing */
  #ifndef PATH_MAX
    #define PATH_MAX MAX_PATH
  #endif
  #define F_OK 0
  #define R_OK 4
  #define W_OK 2
  /* S_ISREG / S_ISDIR: mingw may not define these POSIX macros */
  #ifndef S_ISREG
    #define S_ISREG(m) (((m) & _S_IFMT) == _S_IFREG)
  #endif
  #ifndef S_ISDIR
    #define S_ISDIR(m) (((m) & _S_IFMT) == _S_IFDIR)
  #endif
#endif

/* ── Internal helpers ─────────────────────────────────────────────────── */
/* Renamed from _dup to pycc__strdup to avoid clash with io.h's _dup(int) */
static char* pycc__strdup(const char* s) {
    if (!s) return NULL;
    size_t n = strlen(s) + 1;
    char* r = (char*)malloc(n);
    memcpy(r, s, n);
    return r;
}
static char* _alloc_str(size_t n) { return (char*)calloc(n+1, 1); }

/* ── File I/O ─────────────────────────────────────────────────────────── */
PYCC_API pycc_ptr pycc_fopen(const char* path, const char* mode) { return (pycc_ptr)fopen(path, mode); }
PYCC_API int      pycc_fclose(pycc_ptr fp) { return fclose((FILE*)fp); }
PYCC_API pycc_int pycc_fread(pycc_ptr buf, pycc_int sz, pycc_ptr fp) { return (pycc_int)fread(buf, 1, (size_t)sz, (FILE*)fp); }
PYCC_API pycc_int pycc_fwrite(const char* buf, pycc_int sz, pycc_ptr fp) { return (pycc_int)fwrite(buf, 1, (size_t)sz, (FILE*)fp); }
PYCC_API char*    pycc_fgets(char* buf, int sz, pycc_ptr fp) { return fgets(buf, sz, (FILE*)fp); }
PYCC_API int      pycc_fputs(const char* s, pycc_ptr fp) { return fputs(s, (FILE*)fp); }
PYCC_API int      pycc_fseek(pycc_ptr fp, pycc_int off, int w) { return fseek((FILE*)fp, (long)off, w); }
PYCC_API pycc_int pycc_ftell(pycc_ptr fp) { return (pycc_int)ftell((FILE*)fp); }
PYCC_API int      pycc_feof(pycc_ptr fp) { return feof((FILE*)fp); }
PYCC_API void     pycc_fflush(pycc_ptr fp) { fflush((FILE*)fp); }

PYCC_API char* pycc_freadall(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return pycc__strdup("");
    fseek(f, 0, SEEK_END); long sz = ftell(f); rewind(f);
    char* buf = _alloc_str((size_t)sz);
    fread(buf, 1, (size_t)sz, f); fclose(f);
    return buf;
}
PYCC_API int pycc_fwriteall(const char* path, const char* data) {
    FILE* f = fopen(path, "wb");
    if (!f) return -1;
    int r = (int)fwrite(data, 1, strlen(data), f);
    fclose(f); return r;
}
PYCC_API int pycc_fappend(const char* path, const char* data) {
    FILE* f = fopen(path, "ab");
    if (!f) return -1;
    int r = (int)fwrite(data, 1, strlen(data), f);
    fclose(f); return r;
}

/* ── Low-level fd ops ─────────────────────────────────────────────────── */
#ifdef PYCC_POSIX
PYCC_API pycc_fd  pycc_open(const char* p, int f, int m) { return open(p, f, m); }
PYCC_API int      pycc_close(pycc_fd fd) { return close(fd); }
PYCC_API pycc_int pycc_read(pycc_fd fd, void* b, pycc_int s) { return (pycc_int)read(fd, b, (size_t)s); }
PYCC_API pycc_int pycc_write(pycc_fd fd, const void* b, pycc_int s) { return (pycc_int)write(fd, b, (size_t)s); }
PYCC_API pycc_int pycc_lseek(pycc_fd fd, pycc_int o, int w) { return (pycc_int)lseek(fd, (off_t)o, w); }
PYCC_API int      pycc_dup(pycc_fd fd) { return dup(fd); }
PYCC_API int      pycc_dup2(pycc_fd o, pycc_fd n) { return dup2(o, n); }
PYCC_API int      pycc_pipe(int fds[2]) { return pipe(fds); }
PYCC_API int      pycc_fcntl(pycc_fd fd, int cmd, int arg) { return fcntl(fd, cmd, arg); }
PYCC_API int      pycc_isatty(pycc_fd fd) { return isatty(fd); }
#else
/* Windows / mingw — use underscore variants, avoid name collision with io.h */
PYCC_API pycc_fd  pycc_open(const char* p, int f, int m) { return _open(p, f, m); }
PYCC_API int      pycc_close(pycc_fd fd) { return _close(fd); }
PYCC_API pycc_int pycc_read(pycc_fd fd, void* b, pycc_int s) { return (pycc_int)_read(fd, b, (unsigned)s); }
PYCC_API pycc_int pycc_write(pycc_fd fd, const void* b, pycc_int s) { return (pycc_int)_write(fd, b, (unsigned)s); }
PYCC_API pycc_int pycc_lseek(pycc_fd fd, pycc_int o, int w) { return (pycc_int)_lseek(fd, (long)o, w); }
PYCC_API int      pycc_dup(pycc_fd fd)              { return _dup(fd); }
PYCC_API int      pycc_dup2(pycc_fd o, pycc_fd n)   { return _dup2(o, n); }
PYCC_API int      pycc_pipe(int fds[2])              { return _pipe(fds, 4096, 0); }
PYCC_API int      pycc_fcntl(pycc_fd fd, int cmd, int arg) { (void)fd;(void)cmd;(void)arg; return 0; }
PYCC_API int      pycc_isatty(pycc_fd fd)            { return _isatty(fd); }
#endif

/* ── File system ──────────────────────────────────────────────────────── */
PYCC_API int  pycc_unlink(const char* p) { return remove(p); }
PYCC_API int  pycc_rename(const char* s, const char* d) { return rename(s, d); }
PYCC_API int  pycc_access(const char* p, int m) {
#ifdef PYCC_POSIX
    return access(p, m);
#else
    return _access(p, m);
#endif
}
PYCC_API int pycc_mkdir(const char* path, int mode) {
#ifdef PYCC_POSIX
    return mkdir(path, (mode_t)mode);
#else
    (void)mode; return _mkdir(path);
#endif
}
PYCC_API int pycc_rmdir(const char* path) {
#ifdef PYCC_POSIX
    return rmdir(path);
#else
    return _rmdir(path);
#endif
}
PYCC_API int pycc_makedirs(const char* path, int mode) {
    char tmp[PATH_MAX]; strncpy(tmp, path, PATH_MAX-1); tmp[PATH_MAX-1]=0;
    for (char* p = tmp+1; *p; p++) {
        if (*p == '/' || *p == '\\') { *p = 0; pycc_mkdir(tmp, mode); *p = '/'; }
    }
    return pycc_mkdir(tmp, mode);
}
PYCC_API int pycc_removedirs(const char* path) { return pycc_rmdir(path); }
PYCC_API int pycc_chmod(const char* p, int m) {
#ifdef PYCC_POSIX
    return chmod(p, (mode_t)m);
#else
    return _chmod(p, m);
#endif
}
PYCC_API int pycc_chown(const char* p, int u, int g) {
#ifdef PYCC_POSIX
    return chown(p, (uid_t)u, (gid_t)g);
#else
    (void)p;(void)u;(void)g; return 0;
#endif
}
PYCC_API int pycc_symlink(const char* s, const char* d) {
#ifdef PYCC_POSIX
    return symlink(s, d);
#else
    return CreateSymbolicLinkA(d, s, 0) ? 0 : -1;
#endif
}
PYCC_API int pycc_link(const char* s, const char* d) {
#ifdef PYCC_POSIX
    return link(s, d);
#else
    return CreateHardLinkA(d, s, NULL) ? 0 : -1;
#endif
}
PYCC_API char* pycc_readlink(const char* p) {
    char* buf = _alloc_str(PATH_MAX);
#ifdef PYCC_POSIX
    readlink(p, buf, PATH_MAX-1);
#else
    strncpy(buf, p, PATH_MAX-1);
#endif
    return buf;
}
PYCC_API int pycc_truncate(const char* p, pycc_int sz) {
#ifdef PYCC_POSIX
    return truncate(p, (off_t)sz);
#else
    (void)p;(void)sz; return 0;
#endif
}

/* stat helper: use struct stat on both platforms via mingw's sys/stat.h */
static int _stat_helper(const char* path, struct stat* st) {
#ifdef PYCC_POSIX
    return stat(path, st);
#else
    /* mingw provides struct stat and stat() via sys/stat.h */
    return stat(path, st);
#endif
}

PYCC_API int       pycc_stat_isfile(const char* p) { struct stat s; return !_stat_helper(p,&s) && S_ISREG(s.st_mode); }
PYCC_API int       pycc_stat_isdir(const char* p)  { struct stat s; return !_stat_helper(p,&s) && S_ISDIR(s.st_mode); }
PYCC_API pycc_int  pycc_stat_size(const char* p)   { struct stat s; return !_stat_helper(p,&s) ? (pycc_int)s.st_size : -1; }
PYCC_API pycc_int  pycc_stat_mtime(const char* p)  { struct stat s; return !_stat_helper(p,&s) ? (pycc_int)s.st_mtime : -1; }
PYCC_API int       pycc_path_exists(const char* p) { return pycc_access(p, F_OK) == 0; }

PYCC_API char* pycc_getcwd(void) {
    char* buf = _alloc_str(PATH_MAX);
#ifdef PYCC_POSIX
    getcwd(buf, PATH_MAX);
#else
    _getcwd(buf, PATH_MAX);
#endif
    return buf;
}
PYCC_API int pycc_chdir(const char* p) {
#ifdef PYCC_POSIX
    return chdir(p);
#else
    return _chdir(p);
#endif
}
PYCC_API char* pycc_realpath(const char* p) {
    char* buf = _alloc_str(PATH_MAX);
#ifdef PYCC_POSIX
    realpath(p, buf);
#else
    GetFullPathNameA(p, PATH_MAX, buf, NULL);
#endif
    return buf;
}
PYCC_API char* pycc_basename(const char* p) {
    char* tmp = pycc__strdup(p);
#ifdef PYCC_POSIX
    char* b = pycc__strdup(basename(tmp));
#else
    char fname[_MAX_FNAME], ext[_MAX_EXT];
    _splitpath(p, NULL, NULL, fname, ext);
    char* b = _alloc_str(strlen(fname)+strlen(ext)+2);
    strcat(b, fname); strcat(b, ext);
#endif
    free(tmp); return b;
}
PYCC_API char* pycc_dirname(const char* p) {
    char* tmp = pycc__strdup(p);
#ifdef PYCC_POSIX
    char* d = pycc__strdup(dirname(tmp));
#else
    char drive[_MAX_DRIVE], dir[_MAX_DIR];
    _splitpath(p, drive, dir, NULL, NULL);
    char* d = _alloc_str(strlen(drive)+strlen(dir)+2);
    strcat(d, drive); strcat(d, dir);
    size_t n = strlen(d);
    if (n > 1 && (d[n-1]=='/' || d[n-1]=='\\')) d[n-1]=0;
#endif
    free(tmp); return d;
}
PYCC_API char* pycc_path_join(const char* a, const char* b) {
    size_t n = strlen(a)+strlen(b)+3;
    char* r = _alloc_str(n);
    strcpy(r, a);
    if (strlen(a) && a[strlen(a)-1]!='/' && a[strlen(a)-1]!='\\') strcat(r, "/");
    strcat(r, b); return r;
}
PYCC_API char* pycc_path_join3(const char* a, const char* b, const char* c) {
    char* ab = pycc_path_join(a, b);
    char* r  = pycc_path_join(ab, c);
    free(ab); return r;
}
PYCC_API char* pycc_path_abspath(const char* p) { return pycc_realpath(p); }

PYCC_API char** pycc_listdir(const char* path, pycc_int* count) {
    char** arr = NULL; *count = 0;
#ifdef PYCC_POSIX
    DIR* d = opendir(path); if (!d) return arr;
    struct dirent* e;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name,".") || !strcmp(e->d_name,"..")) continue;
        arr = (char**)realloc(arr, (size_t)(*count+1)*sizeof(char*));
        arr[(*count)++] = pycc__strdup(e->d_name);
    }
    closedir(d);
#else
    WIN32_FIND_DATAA fd; char pat[MAX_PATH];
    snprintf(pat, MAX_PATH, "%s\\*", path);
    HANDLE h = FindFirstFileA(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return arr;
    do {
        if (!strcmp(fd.cFileName,".") || !strcmp(fd.cFileName,"..")) continue;
        arr = (char**)realloc(arr, (size_t)(*count+1)*sizeof(char*));
        arr[(*count)++] = pycc__strdup(fd.cFileName);
    } while (FindNextFileA(h, &fd));
    FindClose(h);
#endif
    return arr;
}

/* ── Process ──────────────────────────────────────────────────────────── */
PYCC_API int  pycc_getpid(void)  {
#ifdef PYCC_POSIX
    return (int)getpid();
#else
    return (int)GetCurrentProcessId();
#endif
}
PYCC_API int  pycc_getppid(void) {
#ifdef PYCC_POSIX
    return (int)getppid();
#else
    return 0;
#endif
}
PYCC_API int  pycc_system(const char* cmd) { return system(cmd); }
PYCC_API pycc_ptr pycc_popen(const char* cmd, const char* mode) {
#ifdef PYCC_POSIX
    return (pycc_ptr)popen(cmd, mode);
#else
    return (pycc_ptr)_popen(cmd, mode);
#endif
}
PYCC_API int pycc_pclose(pycc_ptr fp) {
#ifdef PYCC_POSIX
    return pclose((FILE*)fp);
#else
    return _pclose((FILE*)fp);
#endif
}
PYCC_API char* pycc_popen_read(const char* cmd) {
    FILE* p = (FILE*)pycc_popen(cmd, "r");
    if (!p) return pycc__strdup("");
    char* buf = _alloc_str(65536); size_t n = 0; int c;
    while ((c = fgetc(p)) != EOF && n < 65535) buf[n++] = (char)c;
    pycc_pclose((pycc_ptr)p); return buf;
}
PYCC_API int pycc_fork(void) {
#ifdef PYCC_POSIX
    return (int)fork();
#else
    return -1;
#endif
}
PYCC_API int pycc_waitpid(int pid, int* st, int opts) {
#ifdef PYCC_POSIX
    return (int)waitpid((pid_t)pid, st, opts);
#else
    (void)pid;(void)st;(void)opts; return -1;
#endif
}
PYCC_API int pycc_execv(const char* p, char* const a[]) {
#ifdef PYCC_POSIX
    return execv(p, a);
#else
    return _execv(p, (const char* const*)a);
#endif
}
PYCC_API int pycc_execvp(const char* f, char* const a[]) {
#ifdef PYCC_POSIX
    return execvp(f, a);
#else
    return _execvp(f, (const char* const*)a);
#endif
}
PYCC_API void pycc_exit(int code) { exit(code); }
PYCC_API void pycc_abort(void) { abort(); }

/* ── Environment ──────────────────────────────────────────────────────── */
PYCC_API char* pycc_getenv(const char* k) { char* v = getenv(k); return v ? pycc__strdup(v) : NULL; }
PYCC_API char* pycc_getenv_default(const char* k, const char* d) { char* v = getenv(k); return v ? pycc__strdup(v) : pycc__strdup(d); }
PYCC_API int pycc_setenv(const char* k, const char* v, int ow) {
#ifdef PYCC_POSIX
    return setenv(k, v, ow);
#else
    (void)ow; char buf[32768]; snprintf(buf, sizeof(buf), "%s=%s", k, v); return _putenv(buf);
#endif
}
PYCC_API int pycc_unsetenv(const char* k) {
#ifdef PYCC_POSIX
    return unsetenv(k);
#else
    char buf[8192]; snprintf(buf, sizeof(buf), "%s=", k); return _putenv(buf);
#endif
}
PYCC_API int pycc_putenv(const char* s) { return putenv((char*)s); }

/* ── Signals ──────────────────────────────────────────────────────────── */
PYCC_API int  pycc_kill(int pid, int sig) {
#ifdef PYCC_POSIX
    return kill((pid_t)pid, sig);
#else
    (void)pid;(void)sig; return -1;
#endif
}
PYCC_API int  pycc_raise_sig(int sig) { return raise(sig); }
PYCC_API void pycc_signal_ignore(int sig)  { signal(sig, SIG_IGN); }
PYCC_API void pycc_signal_default(int sig) { signal(sig, SIG_DFL); }

/* ── Sockets ──────────────────────────────────────────────────────────── */
#ifdef PYCC_WIN
static int _wsa_init = 0;
static void _wsa_ensure(void) { if (!_wsa_init) { WSADATA w; WSAStartup(MAKEWORD(2,2),&w); _wsa_init=1; } }
#else
static void _wsa_ensure(void) {}
#endif

PYCC_API pycc_fd pycc_socket(int domain, int type, int proto) {
    _wsa_ensure(); return (pycc_fd)socket(domain, type, proto);
}
PYCC_API int pycc_bind(pycc_fd fd, const char* host, int port) {
    struct sockaddr_in addr; memset(&addr,0,sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons((uint16_t)port);
    addr.sin_addr.s_addr = (host && strcmp(host,"")) ? inet_addr(host) : INADDR_ANY;
    return bind((int)fd, (struct sockaddr*)&addr, sizeof(addr));
}
PYCC_API int     pycc_listen(pycc_fd fd, int bl) { return listen((int)fd, bl); }
PYCC_API pycc_fd pycc_accept(pycc_fd fd, char* host, int* port) {
    struct sockaddr_in addr; memset(&addr,0,sizeof(addr)); socklen_t len = sizeof(addr);
    int c = (int)accept((int)fd, (struct sockaddr*)&addr, &len);
    if (host) strcpy(host, inet_ntoa(addr.sin_addr));
    if (port) *port = ntohs(addr.sin_port);
    return (pycc_fd)c;
}
PYCC_API int pycc_connect(pycc_fd fd, const char* host, int port) {
    struct addrinfo hints, *res; memset(&hints,0,sizeof(hints));
    hints.ai_family=AF_INET; hints.ai_socktype=SOCK_STREAM;
    char ps[16]; snprintf(ps,16,"%d",port);
    if (getaddrinfo(host, ps, &hints, &res)) return -1;
    int r = connect((int)fd, res->ai_addr, (int)res->ai_addrlen);
    freeaddrinfo(res); return r;
}
PYCC_API pycc_int pycc_send(pycc_fd fd, const char* b, pycc_int s, int f) { return (pycc_int)send((int)fd, b, (size_t)s, f); }
PYCC_API pycc_int pycc_recv(pycc_fd fd, char* b, pycc_int s, int f)       { return (pycc_int)recv((int)fd, b, (size_t)s, f); }
PYCC_API int pycc_setsockopt(pycc_fd fd, int lv, int opt, int val) {
    return setsockopt((int)fd, lv, opt, (char*)&val, sizeof(val));
}
PYCC_API int pycc_getsockopt(pycc_fd fd, int lv, int opt, int* val) {
    socklen_t l = sizeof(int); return getsockopt((int)fd, lv, opt, (char*)val, &l);
}
PYCC_API int pycc_socket_close(pycc_fd fd) {
#ifdef PYCC_WIN
    return closesocket((SOCKET)fd);
#else
    return close(fd);
#endif
}
PYCC_API int   pycc_gethostname(char* buf, int sz) { return gethostname(buf, sz); }
PYCC_API char* pycc_gethostbyname(const char* host) {
    struct hostent* h = gethostbyname(host);
    if (!h) return pycc__strdup("");
    return pycc__strdup(inet_ntoa(*(struct in_addr*)h->h_addr));
}
PYCC_API int pycc_setnonblocking(pycc_fd fd) {
#ifdef PYCC_POSIX
    int f = fcntl(fd, F_GETFL, 0); return fcntl(fd, F_SETFL, f | O_NONBLOCK);
#else
    u_long m=1; return ioctlsocket((SOCKET)fd, FIONBIO, &m);
#endif
}
PYCC_API int pycc_select(pycc_fd fd, int rd, int wr, int timeout_ms) {
    fd_set r, w; FD_ZERO(&r); FD_ZERO(&w);
    if (rd) FD_SET((unsigned)fd, &r);
    if (wr) FD_SET((unsigned)fd, &w);
    struct timeval tv; tv.tv_sec=timeout_ms/1000; tv.tv_usec=(timeout_ms%1000)*1000;
    return select(fd+1, rd?&r:NULL, wr?&w:NULL, NULL, timeout_ms>=0?&tv:NULL);
}
PYCC_API char* pycc_socket_send_recv(const char* host, int port, const char* data) {
    _wsa_ensure();
    int fd = (int)pycc_socket(AF_INET, SOCK_STREAM, 0);
    if (pycc_connect((pycc_fd)fd, host, port)) return pycc__strdup("");
    pycc_send((pycc_fd)fd, data, (pycc_int)strlen(data), 0);
    char* buf = _alloc_str(65536);
    pycc_recv((pycc_fd)fd, buf, 65535, 0);
    pycc_socket_close((pycc_fd)fd);
    return buf;
}

/* ── Threading ────────────────────────────────────────────────────────── */
#ifdef PYCC_POSIX
PYCC_API pycc_ptr pycc_thread_create(void (*fn)(void*), void* arg) {
    pthread_t* t = (pthread_t*)malloc(sizeof(pthread_t));
    pthread_create(t, NULL, (void*(*)(void*))fn, arg);
    return (pycc_ptr)t;
}
PYCC_API int  pycc_thread_join(pycc_ptr t) { int r = pthread_join(*(pthread_t*)t, NULL); free(t); return r; }
PYCC_API void pycc_thread_detach(pycc_ptr t) { pthread_detach(*(pthread_t*)t); free(t); }
PYCC_API pycc_ptr pycc_mutex_create(void) { pthread_mutex_t* m=(pthread_mutex_t*)malloc(sizeof(pthread_mutex_t)); pthread_mutex_init(m,NULL); return m; }
PYCC_API int  pycc_mutex_lock(pycc_ptr m)    { return pthread_mutex_lock((pthread_mutex_t*)m); }
PYCC_API int  pycc_mutex_unlock(pycc_ptr m)  { return pthread_mutex_unlock((pthread_mutex_t*)m); }
PYCC_API int  pycc_mutex_trylock(pycc_ptr m) { return pthread_mutex_trylock((pthread_mutex_t*)m); }
PYCC_API void pycc_mutex_destroy(pycc_ptr m) { pthread_mutex_destroy((pthread_mutex_t*)m); free(m); }
PYCC_API pycc_ptr pycc_cond_create(void) { pthread_cond_t* c=(pthread_cond_t*)malloc(sizeof(pthread_cond_t)); pthread_cond_init(c,NULL); return c; }
PYCC_API int  pycc_cond_wait(pycc_ptr c, pycc_ptr m) { return pthread_cond_wait((pthread_cond_t*)c,(pthread_mutex_t*)m); }
PYCC_API int  pycc_cond_signal(pycc_ptr c)    { return pthread_cond_signal((pthread_cond_t*)c); }
PYCC_API int  pycc_cond_broadcast(pycc_ptr c) { return pthread_cond_broadcast((pthread_cond_t*)c); }
PYCC_API void pycc_cond_destroy(pycc_ptr c)   { pthread_cond_destroy((pthread_cond_t*)c); free(c); }
PYCC_API pycc_ptr pycc_rwlock_create(void) { pthread_rwlock_t* rw=(pthread_rwlock_t*)malloc(sizeof(pthread_rwlock_t)); pthread_rwlock_init(rw,NULL); return rw; }
PYCC_API int  pycc_rwlock_rdlock(pycc_ptr rw) { return pthread_rwlock_rdlock((pthread_rwlock_t*)rw); }
PYCC_API int  pycc_rwlock_wrlock(pycc_ptr rw) { return pthread_rwlock_wrlock((pthread_rwlock_t*)rw); }
PYCC_API int  pycc_rwlock_unlock(pycc_ptr rw) { return pthread_rwlock_unlock((pthread_rwlock_t*)rw); }
PYCC_API void pycc_rwlock_destroy(pycc_ptr rw) { pthread_rwlock_destroy((pthread_rwlock_t*)rw); free(rw); }
PYCC_API int  pycc_thread_self_id(void) { return (int)(size_t)pthread_self(); }
PYCC_API void pycc_thread_sleep_ms(int ms) { struct timespec ts; ts.tv_sec=ms/1000; ts.tv_nsec=(ms%1000)*1000000L; nanosleep(&ts,NULL); }
#else
PYCC_API pycc_ptr pycc_thread_create(void (*fn)(void*), void* arg) {
    HANDLE h = CreateThread(NULL,0,(LPTHREAD_START_ROUTINE)fn,arg,0,NULL); return (pycc_ptr)h;
}
PYCC_API int  pycc_thread_join(pycc_ptr t) { WaitForSingleObject((HANDLE)t,INFINITE); CloseHandle((HANDLE)t); return 0; }
PYCC_API void pycc_thread_detach(pycc_ptr t) { CloseHandle((HANDLE)t); }
PYCC_API pycc_ptr pycc_mutex_create(void) { CRITICAL_SECTION* cs=(CRITICAL_SECTION*)malloc(sizeof(CRITICAL_SECTION)); InitializeCriticalSection(cs); return cs; }
PYCC_API int  pycc_mutex_lock(pycc_ptr m)    { EnterCriticalSection((CRITICAL_SECTION*)m); return 0; }
PYCC_API int  pycc_mutex_unlock(pycc_ptr m)  { LeaveCriticalSection((CRITICAL_SECTION*)m); return 0; }
PYCC_API int  pycc_mutex_trylock(pycc_ptr m) { return TryEnterCriticalSection((CRITICAL_SECTION*)m)?0:1; }
PYCC_API void pycc_mutex_destroy(pycc_ptr m) { DeleteCriticalSection((CRITICAL_SECTION*)m); free(m); }
PYCC_API pycc_ptr pycc_cond_create(void) { CONDITION_VARIABLE* cv=(CONDITION_VARIABLE*)malloc(sizeof(CONDITION_VARIABLE)); InitializeConditionVariable(cv); return cv; }
PYCC_API int  pycc_cond_wait(pycc_ptr c, pycc_ptr m) { SleepConditionVariableCS((CONDITION_VARIABLE*)c,(CRITICAL_SECTION*)m,INFINITE); return 0; }
PYCC_API int  pycc_cond_signal(pycc_ptr c)    { WakeConditionVariable((CONDITION_VARIABLE*)c); return 0; }
PYCC_API int  pycc_cond_broadcast(pycc_ptr c) { WakeAllConditionVariable((CONDITION_VARIABLE*)c); return 0; }
PYCC_API void pycc_cond_destroy(pycc_ptr c)   { free(c); }
PYCC_API pycc_ptr pycc_rwlock_create(void) { SRWLOCK* rw=(SRWLOCK*)malloc(sizeof(SRWLOCK)); InitializeSRWLock(rw); return rw; }
PYCC_API int  pycc_rwlock_rdlock(pycc_ptr rw) { AcquireSRWLockShared((SRWLOCK*)rw); return 0; }
PYCC_API int  pycc_rwlock_wrlock(pycc_ptr rw) { AcquireSRWLockExclusive((SRWLOCK*)rw); return 0; }
PYCC_API int  pycc_rwlock_unlock(pycc_ptr rw) { ReleaseSRWLockExclusive((SRWLOCK*)rw); return 0; }
PYCC_API void pycc_rwlock_destroy(pycc_ptr rw) { free(rw); }
PYCC_API int  pycc_thread_self_id(void) { return (int)GetCurrentThreadId(); }
PYCC_API void pycc_thread_sleep_ms(int ms) { Sleep((DWORD)ms); }
#endif

/* ── Memory mapping ───────────────────────────────────────────────────── */
#ifdef PYCC_POSIX
PYCC_API pycc_ptr pycc_mmap(pycc_int sz, int prot, int flags, pycc_fd fd, pycc_int off) { return mmap(NULL,(size_t)sz,prot,flags,fd,(off_t)off); }
PYCC_API int pycc_munmap(pycc_ptr a, pycc_int sz) { return munmap(a,(size_t)sz); }
PYCC_API int pycc_mprotect(pycc_ptr a, pycc_int sz, int prot) { return mprotect(a,(size_t)sz,prot); }
PYCC_API pycc_ptr pycc_mmap_file(const char* path, pycc_int* sz) {
    int fd = open(path, O_RDONLY); if (fd<0) return NULL;
    struct stat st; fstat(fd,&st); *sz=(pycc_int)st.st_size;
    void* m = mmap(NULL,(size_t)st.st_size,PROT_READ,MAP_PRIVATE,fd,0); close(fd); return m;
}
PYCC_API int pycc_munmap_file(pycc_ptr a, pycc_int sz) { return munmap(a,(size_t)sz); }
#else
PYCC_API pycc_ptr pycc_mmap(pycc_int sz, int prot, int flags, pycc_fd fd, pycc_int off) {
    (void)prot;(void)flags;(void)fd;(void)off;
    HANDLE fm = CreateFileMappingA(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,0,(DWORD)sz,NULL);
    return MapViewOfFile(fm,FILE_MAP_ALL_ACCESS,0,0,(SIZE_T)sz);
}
PYCC_API int  pycc_munmap(pycc_ptr a, pycc_int sz) { (void)sz; return UnmapViewOfFile(a)?0:-1; }
PYCC_API int  pycc_mprotect(pycc_ptr a, pycc_int sz, int prot) { (void)a;(void)sz;(void)prot; return 0; }
PYCC_API pycc_ptr pycc_mmap_file(const char* path, pycc_int* sz) {
    HANDLE f=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    if(f==INVALID_HANDLE_VALUE) return NULL;
    *sz=(pycc_int)GetFileSize(f,NULL);
    HANDLE m=CreateFileMappingA(f,NULL,PAGE_READONLY,0,0,NULL);
    void* v=MapViewOfFile(m,FILE_MAP_READ,0,0,0); CloseHandle(m); CloseHandle(f); return v;
}
PYCC_API int pycc_munmap_file(pycc_ptr a, pycc_int sz) { (void)sz; return UnmapViewOfFile(a)?0:-1; }
#endif

/* ── Dynamic loading ──────────────────────────────────────────────────── */
PYCC_API pycc_ptr pycc_dlopen(const char* path) {
#ifdef PYCC_POSIX
    return dlopen(path, RTLD_LAZY|RTLD_GLOBAL);
#else
    return (pycc_ptr)LoadLibraryA(path);
#endif
}
PYCC_API pycc_ptr pycc_dlsym(pycc_ptr h, const char* sym) {
#ifdef PYCC_POSIX
    return dlsym(h, sym);
#else
    return (pycc_ptr)GetProcAddress((HMODULE)h, sym);
#endif
}
PYCC_API int pycc_dlclose(pycc_ptr h) {
#ifdef PYCC_POSIX
    return dlclose(h);
#else
    return FreeLibrary((HMODULE)h)?0:-1;
#endif
}
PYCC_API char* pycc_dlerror(void) {
#ifdef PYCC_POSIX
    const char* e = dlerror(); return pycc__strdup(e ? e : "");
#else
    return pycc__strdup("dlerror not available on Windows");
#endif
}

/* ── Crypto / hashing ─────────────────────────────────────────────────── */
PYCC_API uint32_t pycc_crc32(const char* data, pycc_int sz) {
    uint32_t crc = 0xFFFFFFFF;
    for (pycc_int i=0; i<sz; i++) {
        crc ^= (uint8_t)data[i];
        for (int j=0; j<8; j++) crc = (crc>>1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc&1)));
    }
    return ~crc;
}
PYCC_API uint64_t pycc_fnv1a(const char* data, pycc_int sz) {
    uint64_t h = 14695981039346656037ULL;
    for (pycc_int i=0; i<sz; i++) { h ^= (uint8_t)data[i]; h *= 1099511628211ULL; }
    return h;
}
PYCC_API int pycc_rand_bytes(char* buf, pycc_int sz) {
#ifdef PYCC_POSIX
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd<0) { for(pycc_int i=0;i<sz;i++) buf[i]=(char)rand(); return 0; }
    read(fd, buf, (size_t)sz); close(fd); return 0;
#else
    for(pycc_int i=0;i<sz;i++) buf[i]=(char)rand(); return 0;
#endif
}

#define ROTR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static const uint32_t _K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};
PYCC_API char* pycc_sha256(const char* data, pycc_int sz) {
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    uint8_t buf[64]; pycc_int i; uint64_t bits=(uint64_t)sz*8;
    const uint8_t* msg=(const uint8_t*)data; pycc_int rem=sz;
    while(rem>=64){
        uint32_t w[64];
        for(i=0;i<16;i++) w[i]=((uint32_t)msg[i*4]<<24)|((uint32_t)msg[i*4+1]<<16)|((uint32_t)msg[i*4+2]<<8)|msg[i*4+3];
        for(i=16;i<64;i++){uint32_t s0=ROTR(w[i-15],7)^ROTR(w[i-15],18)^(w[i-15]>>3);uint32_t s1=ROTR(w[i-2],17)^ROTR(w[i-2],19)^(w[i-2]>>10);w[i]=w[i-16]+s0+w[i-7]+s1;}
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for(i=0;i<64;i++){uint32_t S1=ROTR(e,6)^ROTR(e,11)^ROTR(e,25);uint32_t ch=(e&f)^(~e&g);uint32_t t1=hh+S1+ch+_K[i]+w[i];uint32_t S0=ROTR(a,2)^ROTR(a,13)^ROTR(a,22);uint32_t maj=(a&b)^(a&c)^(b&c);uint32_t t2=S0+maj;hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh; msg+=64; rem-=64;
    }
    memset(buf,0,64); memcpy(buf,msg,(size_t)rem); buf[rem]=0x80;
    if(rem<56){buf[56]=(uint8_t)(bits>>56);buf[57]=(uint8_t)(bits>>48);buf[58]=(uint8_t)(bits>>40);buf[59]=(uint8_t)(bits>>32);buf[60]=(uint8_t)(bits>>24);buf[61]=(uint8_t)(bits>>16);buf[62]=(uint8_t)(bits>>8);buf[63]=(uint8_t)bits;}
    char* out = _alloc_str(65); for(i=0;i<8;i++) snprintf(out+i*8,9,"%08x",h[i]); return out;
}
PYCC_API char* pycc_md5(const char* data, pycc_int sz)  { return pycc_sha256(data, sz); }
PYCC_API char* pycc_sha1(const char* data, pycc_int sz) { return pycc_sha256(data, sz); }

static const char _b64c[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
PYCC_API char* pycc_base64_encode(const char* data, pycc_int sz) {
    pycc_int out_sz = 4*((sz+2)/3);
    char* out = _alloc_str((size_t)out_sz+1); pycc_int j=0;
    for(pycc_int i=0;i<sz;i+=3){
        uint32_t v=((uint8_t)data[i]<<16)|(i+1<sz?(uint8_t)data[i+1]<<8:0)|(i+2<sz?(uint8_t)data[i+2]:0);
        out[j++]=_b64c[(v>>18)&63]; out[j++]=_b64c[(v>>12)&63];
        out[j++]=(i+1<sz)?_b64c[(v>>6)&63]:'='; out[j++]=(i+2<sz)?_b64c[v&63]:'=';
    }
    return out;
}
PYCC_API char* pycc_base64_decode(const char* data, pycc_int* out_sz) {
    pycc_int len=(pycc_int)strlen(data); *out_sz=3*len/4;
    char* out=_alloc_str((size_t)*out_sz+1); pycc_int j=0;
    for(pycc_int i=0;i<len;i+=4){
        uint32_t v=0;
        for(int k=0;k<4;k++){
            char c=data[i+k];
            uint32_t bv=(c>='A'&&c<='Z')?(uint32_t)(c-'A'):(c>='a'&&c<='z')?(uint32_t)(c-'a'+26):(c>='0'&&c<='9')?(uint32_t)(c-'0'+52):(c=='+')?62u:63u;
            v=(v<<6)|bv;
        }
        if(j<*out_sz) out[j++]=(char)(v>>16);
        if(j<*out_sz) out[j++]=(char)(v>>8);
        if(j<*out_sz) out[j++]=(char)v;
    }
    return out;
}

/* ── String utilities ─────────────────────────────────────────────────── */
PYCC_API char* pycc_str_upper(const char* s) { char* r=pycc__strdup(s); for(char* p=r;*p;p++) *p=(char)toupper((unsigned char)*p); return r; }
PYCC_API char* pycc_str_lower(const char* s) { char* r=pycc__strdup(s); for(char* p=r;*p;p++) *p=(char)tolower((unsigned char)*p); return r; }
PYCC_API char* pycc_str_strip(const char* s) {
    while(isspace((unsigned char)*s)) s++;
    char* r=pycc__strdup(s); int n=(int)strlen(r);
    while(n>0 && isspace((unsigned char)r[n-1])) r[--n]=0;
    return r;
}
PYCC_API char* pycc_str_lstrip(const char* s) { while(isspace((unsigned char)*s)) s++; return pycc__strdup(s); }
PYCC_API char* pycc_str_rstrip(const char* s) { char* r=pycc__strdup(s); int n=(int)strlen(r); while(n>0&&isspace((unsigned char)r[n-1])) r[--n]=0; return r; }
PYCC_API char* pycc_str_replace(const char* s, const char* old, const char* new_s) {
    size_t olen=strlen(old), nlen=strlen(new_s), slen=strlen(s);
    if(!olen) return pycc__strdup(s);
    char* r=_alloc_str(slen*(nlen>olen?nlen:olen)+1024);
    const char* p=s; char* q=r;
    while(*p){ const char* f=strstr(p,old); if(!f){strcpy(q,p);break;} memcpy(q,p,(size_t)(f-p));q+=f-p;memcpy(q,new_s,nlen);q+=nlen;p=f+olen; }
    return r;
}
PYCC_API char** pycc_str_split(const char* s, const char* delim, pycc_int* count) {
    char** arr=NULL; *count=0; char* tmp=pycc__strdup(s);
    char* tok=strtok(tmp, delim);
    while(tok){ arr=(char**)realloc(arr,(size_t)(*count+1)*sizeof(char*)); arr[(*count)++]=pycc__strdup(tok); tok=strtok(NULL,delim); }
    free(tmp); return arr;
}
PYCC_API char* pycc_str_join(const char* sep, char** parts, pycc_int count) {
    if(!count) return pycc__strdup("");
    size_t slen=strlen(sep), total=0;
    for(pycc_int i=0;i<count;i++) total+=strlen(parts[i])+slen;
    char* r=_alloc_str(total+1);
    for(pycc_int i=0;i<count;i++){ strcat(r,parts[i]); if(i<count-1) strcat(r,sep); }
    return r;
}
PYCC_API int   pycc_str_startswith(const char* s, const char* p) { return strncmp(s,p,strlen(p))==0; }
PYCC_API int   pycc_str_endswith(const char* s, const char* suf) { size_t sl=strlen(s),el=strlen(suf); return sl>=el && strcmp(s+sl-el,suf)==0; }
PYCC_API char* pycc_str_repeat(const char* s, pycc_int n) { size_t l=strlen(s); char* r=_alloc_str(l*(size_t)n+1); for(pycc_int i=0;i<n;i++) strcat(r,s); return r; }
PYCC_API pycc_int pycc_str_find(const char* s, const char* sub) { const char* p=strstr(s,sub); return p?(pycc_int)(p-s):-1; }
PYCC_API pycc_int pycc_str_count(const char* s, const char* sub) { pycc_int c=0; size_t l=strlen(sub); const char* p=s; while((p=strstr(p,sub))){c++;p+=l;} return c; }
PYCC_API char* pycc_str_slice(const char* s, pycc_int start, pycc_int end) { pycc_int l=(pycc_int)strlen(s); if(start<0)start=l+start; if(end<0)end=l+end; if(start<0)start=0; if(end>l)end=l; if(start>=end) return pycc__strdup(""); char* r=_alloc_str((size_t)(end-start)+1); memcpy(r,s+start,(size_t)(end-start)); return r; }
PYCC_API char* pycc_str_format(const char* fmt, ...) { char* r=_alloc_str(4096); va_list a; va_start(a,fmt); vsnprintf(r,4095,fmt,a); va_end(a); return r; }
PYCC_API char* pycc_str_zfill(const char* s, pycc_int w) { pycc_int l=(pycc_int)strlen(s); if(l>=w) return pycc__strdup(s); char* r=_alloc_str((size_t)w+1); memset(r,'0',(size_t)(w-l)); strcpy(r+(w-l),s); return r; }
PYCC_API char* pycc_str_center(const char* s, pycc_int w, char fill) { pycc_int l=(pycc_int)strlen(s); if(l>=w) return pycc__strdup(s); pycc_int lp=(w-l)/2; char* r=_alloc_str((size_t)w+1); memset(r,fill,(size_t)w); memcpy(r+lp,s,(size_t)l); return r; }
PYCC_API char* pycc_str_ljust(const char* s, pycc_int w, char fill) { pycc_int l=(pycc_int)strlen(s); if(l>=w) return pycc__strdup(s); char* r=_alloc_str((size_t)w+1); memcpy(r,s,(size_t)l); memset(r+l,fill,(size_t)(w-l)); return r; }
PYCC_API char* pycc_str_rjust(const char* s, pycc_int w, char fill) { pycc_int l=(pycc_int)strlen(s); if(l>=w) return pycc__strdup(s); char* r=_alloc_str((size_t)w+1); memset(r,fill,(size_t)(w-l)); memcpy(r+(w-l),s,(size_t)l); return r; }
PYCC_API int   pycc_str_isdigit(const char* s) { for(;*s;s++) if(!isdigit((unsigned char)*s)) return 0; return 1; }
PYCC_API int   pycc_str_isalpha(const char* s) { for(;*s;s++) if(!isalpha((unsigned char)*s)) return 0; return 1; }
PYCC_API int   pycc_str_isalnum(const char* s) { for(;*s;s++) if(!isalnum((unsigned char)*s)) return 0; return 1; }
PYCC_API int   pycc_str_isspace(const char* s) { for(;*s;s++) if(!isspace((unsigned char)*s)) return 0; return 1; }
PYCC_API int   pycc_str_isupper(const char* s) { int u=0; for(;*s;s++){if(islower((unsigned char)*s))return 0; if(isupper((unsigned char)*s))u=1;} return u; }
PYCC_API int   pycc_str_islower(const char* s) { int l=0; for(;*s;s++){if(isupper((unsigned char)*s))return 0; if(islower((unsigned char)*s))l=1;} return l; }
PYCC_API char* pycc_int_to_str(pycc_int n)    { char* r=_alloc_str(32); snprintf(r,31,"%lld",(long long)n); return r; }
PYCC_API char* pycc_float_to_str(pycc_float n){ char* r=_alloc_str(64); snprintf(r,63,"%g",n); return r; }
PYCC_API pycc_int   pycc_str_to_int(const char* s)   { return (pycc_int)atoll(s); }
PYCC_API pycc_float pycc_str_to_float(const char* s) { return (pycc_float)atof(s); }
PYCC_API char* pycc_str_from_char(char c)  { char* r=_alloc_str(2); r[0]=c; return r; }
PYCC_API char* pycc_str_concat(const char* a, const char* b) { size_t n=strlen(a)+strlen(b)+1; char* r=_alloc_str(n); strcpy(r,a); strcat(r,b); return r; }
PYCC_API char* pycc_str_concat3(const char* a, const char* b, const char* c) { size_t n=strlen(a)+strlen(b)+strlen(c)+1; char* r=_alloc_str(n); strcpy(r,a); strcat(r,b); strcat(r,c); return r; }

/* ── List ─────────────────────────────────────────────────────────────── */
typedef struct { pycc_int* data; pycc_int len; pycc_int cap; char** sdata; int is_str; } PyccList;
PYCC_API pycc_ptr pycc_list_new(pycc_int cap) {
    PyccList* l=(PyccList*)malloc(sizeof(PyccList)); l->len=0; l->cap=cap>0?cap:8;
    l->data=(pycc_int*)malloc(sizeof(pycc_int)*(size_t)l->cap);
    l->sdata=(char**)malloc(sizeof(char*)*(size_t)l->cap); l->is_str=0; return (pycc_ptr)l;
}
PYCC_API int pycc_list_append(pycc_ptr lp, pycc_int v) {
    PyccList* l=(PyccList*)lp;
    if(l->len>=l->cap){l->cap*=2;l->data=(pycc_int*)realloc(l->data,sizeof(pycc_int)*(size_t)l->cap);l->sdata=(char**)realloc(l->sdata,sizeof(char*)*(size_t)l->cap);}
    l->data[l->len++]=v; return 0;
}
PYCC_API int pycc_list_append_str(pycc_ptr lp, const char* v) {
    PyccList* l=(PyccList*)lp; l->is_str=1;
    if(l->len>=l->cap){l->cap*=2;l->data=(pycc_int*)realloc(l->data,sizeof(pycc_int)*(size_t)l->cap);l->sdata=(char**)realloc(l->sdata,sizeof(char*)*(size_t)l->cap);}
    l->sdata[l->len++]=pycc__strdup(v); return 0;
}
PYCC_API pycc_int pycc_list_get(pycc_ptr lp, pycc_int i) { PyccList* l=(PyccList*)lp; return (i>=0&&i<l->len)?l->data[i]:0; }
PYCC_API char*    pycc_list_get_str(pycc_ptr lp, pycc_int i) { PyccList* l=(PyccList*)lp; return (i>=0&&i<l->len)?l->sdata[i]:NULL; }
PYCC_API int      pycc_list_set(pycc_ptr lp, pycc_int i, pycc_int v) { PyccList* l=(PyccList*)lp; if(i>=0&&i<l->len)l->data[i]=v; return 0; }
PYCC_API pycc_int pycc_list_len(pycc_ptr lp) { return ((PyccList*)lp)->len; }
PYCC_API int      pycc_list_pop(pycc_ptr lp, pycc_int i) { PyccList* l=(PyccList*)lp; if(i<0||i>=l->len)return -1; memmove(l->data+i,l->data+i+1,(size_t)(l->len-i-1)*sizeof(pycc_int)); l->len--; return 0; }
PYCC_API int      pycc_list_clear(pycc_ptr lp) { ((PyccList*)lp)->len=0; return 0; }
PYCC_API pycc_ptr pycc_list_copy(pycc_ptr lp) { PyccList* s=(PyccList*)lp; pycc_ptr n=pycc_list_new(s->cap); PyccList* d=(PyccList*)n; memcpy(d->data,s->data,(size_t)s->len*sizeof(pycc_int)); if(s->sdata) memcpy(d->sdata,s->sdata,(size_t)s->len*sizeof(char*)); d->len=s->len; d->is_str=s->is_str; return n; }
static int _cmp_int(const void* a, const void* b) { return (*(pycc_int*)a>*(pycc_int*)b)-(*(pycc_int*)a<*(pycc_int*)b); }
PYCC_API int      pycc_list_sort(pycc_ptr lp)    { PyccList* l=(PyccList*)lp; qsort(l->data,(size_t)l->len,sizeof(pycc_int),_cmp_int); return 0; }
PYCC_API int      pycc_list_reverse(pycc_ptr lp) { PyccList* l=(PyccList*)lp; for(pycc_int i=0,j=l->len-1;i<j;i++,j--){pycc_int t=l->data[i];l->data[i]=l->data[j];l->data[j]=t;} return 0; }
PYCC_API pycc_int pycc_list_index(pycc_ptr lp, pycc_int v) { PyccList* l=(PyccList*)lp; for(pycc_int i=0;i<l->len;i++) if(l->data[i]==v) return i; return -1; }
PYCC_API pycc_int pycc_list_count(pycc_ptr lp, pycc_int v) { PyccList* l=(PyccList*)lp; pycc_int c=0; for(pycc_int i=0;i<l->len;i++) if(l->data[i]==v) c++; return c; }
PYCC_API void     pycc_list_free(pycc_ptr lp) { PyccList* l=(PyccList*)lp; free(l->data); free(l->sdata); free(l); }

/* ── Dict ─────────────────────────────────────────────────────────────── */
#define DICT_BUCKETS 256
typedef struct DictEntry { char* key; char* val; pycc_int ival; int is_int; struct DictEntry* next; } DictEntry;
typedef struct { DictEntry* buckets[DICT_BUCKETS]; pycc_int len; } PyccDict;
static int _hash(const char* k) { unsigned h=5381; while(*k) h=((h<<5)+h)+(unsigned char)*k++; return (int)(h%DICT_BUCKETS); }
PYCC_API pycc_ptr pycc_dict_new(void) { return (pycc_ptr)calloc(1,sizeof(PyccDict)); }
PYCC_API int pycc_dict_set(pycc_ptr dp, const char* k, const char* v) {
    PyccDict* d=(PyccDict*)dp; int h=_hash(k);
    for(DictEntry* e=d->buckets[h];e;e=e->next) if(!strcmp(e->key,k)){free(e->val);e->val=pycc__strdup(v);e->is_int=0;return 0;}
    DictEntry* e=(DictEntry*)malloc(sizeof(DictEntry)); e->key=pycc__strdup(k);e->val=pycc__strdup(v);e->is_int=0;e->next=d->buckets[h];d->buckets[h]=e;d->len++; return 0;
}
PYCC_API int pycc_dict_set_int(pycc_ptr dp, const char* k, pycc_int v) {
    PyccDict* d=(PyccDict*)dp; int h=_hash(k);
    for(DictEntry* e=d->buckets[h];e;e=e->next) if(!strcmp(e->key,k)){e->ival=v;e->is_int=1;return 0;}
    DictEntry* e=(DictEntry*)malloc(sizeof(DictEntry)); e->key=pycc__strdup(k);e->val=NULL;e->ival=v;e->is_int=1;e->next=d->buckets[h];d->buckets[h]=e;d->len++; return 0;
}
PYCC_API char*    pycc_dict_get(pycc_ptr dp, const char* k) { PyccDict* d=(PyccDict*)dp; for(DictEntry* e=d->buckets[_hash(k)];e;e=e->next) if(!strcmp(e->key,k)) return e->val?e->val:pycc__strdup(""); return NULL; }
PYCC_API pycc_int pycc_dict_get_int(pycc_ptr dp, const char* k, pycc_int def) { PyccDict* d=(PyccDict*)dp; for(DictEntry* e=d->buckets[_hash(k)];e;e=e->next) if(!strcmp(e->key,k)) return e->ival; return def; }
PYCC_API int      pycc_dict_has(pycc_ptr dp, const char* k) { PyccDict* d=(PyccDict*)dp; for(DictEntry* e=d->buckets[_hash(k)];e;e=e->next) if(!strcmp(e->key,k)) return 1; return 0; }
PYCC_API int pycc_dict_del(pycc_ptr dp, const char* k) {
    PyccDict* d=(PyccDict*)dp; int h=_hash(k); DictEntry** pp=&d->buckets[h];
    while(*pp){if(!strcmp((*pp)->key,k)){DictEntry* t=*pp;*pp=t->next;free(t->key);free(t->val);free(t);d->len--;return 0;}pp=&(*pp)->next;}
    return -1;
}
PYCC_API pycc_int pycc_dict_len(pycc_ptr dp) { return ((PyccDict*)dp)->len; }
PYCC_API char** pycc_dict_keys(pycc_ptr dp, pycc_int* count) {
    PyccDict* d=(PyccDict*)dp; char** r=(char**)malloc((size_t)d->len*sizeof(char*)); *count=0;
    for(int i=0;i<DICT_BUCKETS;i++) for(DictEntry* e=d->buckets[i];e;e=e->next) r[(*count)++]=pycc__strdup(e->key);
    return r;
}
PYCC_API char** pycc_dict_values(pycc_ptr dp, pycc_int* count) {
    PyccDict* d=(PyccDict*)dp; char** r=(char**)malloc((size_t)d->len*sizeof(char*)); *count=0;
    for(int i=0;i<DICT_BUCKETS;i++) for(DictEntry* e=d->buckets[i];e;e=e->next) r[(*count)++]=e->val?pycc__strdup(e->val):pycc_int_to_str(e->ival);
    return r;
}
PYCC_API pycc_ptr pycc_dict_copy(pycc_ptr dp) {
    PyccDict* d=(PyccDict*)dp; pycc_ptr n=pycc_dict_new();
    for(int i=0;i<DICT_BUCKETS;i++) for(DictEntry* e=d->buckets[i];e;e=e->next) { if(e->is_int) pycc_dict_set_int(n,e->key,e->ival); else pycc_dict_set(n,e->key,e->val); }
    return n;
}
PYCC_API void pycc_dict_update(pycc_ptr dst, pycc_ptr src) {
    PyccDict* d=(PyccDict*)src;
    for(int i=0;i<DICT_BUCKETS;i++) for(DictEntry* e=d->buckets[i];e;e=e->next) { if(e->is_int) pycc_dict_set_int(dst,e->key,e->ival); else pycc_dict_set(dst,e->key,e->val); }
}
PYCC_API void pycc_dict_clear(pycc_ptr dp) {
    PyccDict* d=(PyccDict*)dp;
    for(int i=0;i<DICT_BUCKETS;i++){DictEntry* e=d->buckets[i];while(e){DictEntry* nx=e->next;free(e->key);free(e->val);free(e);e=nx;}d->buckets[i]=NULL;}
    d->len=0;
}
PYCC_API void pycc_dict_free(pycc_ptr dp) { pycc_dict_clear(dp); free(dp); }

/* ── Time ─────────────────────────────────────────────────────────────── */
PYCC_API pycc_int   pycc_time_now(void)   { return (pycc_int)time(NULL); }
PYCC_API pycc_float pycc_time_now_f(void) { return (pycc_float)time(NULL); }
PYCC_API void pycc_sleep(pycc_float s) {
#ifdef PYCC_POSIX
    struct timespec ts; ts.tv_sec=(long)s; ts.tv_nsec=(long)((s-(long)s)*1e9); nanosleep(&ts,NULL);
#else
    Sleep((DWORD)(s*1000));
#endif
}
PYCC_API void  pycc_sleep_ms(pycc_int ms) { pycc_sleep((pycc_float)ms/1000.0); }
PYCC_API char* pycc_time_str(void) { time_t t=time(NULL); char* s=pycc__strdup(ctime(&t)); int n=(int)strlen(s); if(n>0&&s[n-1]=='\n')s[n-1]=0; return s; }
PYCC_API char* pycc_time_format(const char* fmt) { time_t t=time(NULL); struct tm* tm_=localtime(&t); char* buf=_alloc_str(256); strftime(buf,255,fmt,tm_); return buf; }

/* ── Math extras ──────────────────────────────────────────────────────── */
PYCC_API pycc_float pycc_math_pow(pycc_float b, pycc_float e) { return pow(b,e); }
PYCC_API pycc_float pycc_math_sqrt(pycc_float x) { return sqrt(x); }
PYCC_API pycc_float pycc_math_log(pycc_float x)  { return log(x); }
PYCC_API pycc_float pycc_math_log2(pycc_float x) { return log2(x); }
PYCC_API pycc_float pycc_math_log10(pycc_float x){ return log10(x); }
PYCC_API pycc_int   pycc_math_gcd(pycc_int a, pycc_int b) { while(b){pycc_int t=b;b=a%b;a=t;} return a<0?-a:a; }
PYCC_API pycc_int   pycc_math_lcm(pycc_int a, pycc_int b) { return a/pycc_math_gcd(a,b)*b; }
PYCC_API pycc_float pycc_math_hypot(pycc_float a, pycc_float b) { return sqrt(a*a+b*b); }

/* ── Print helpers ────────────────────────────────────────────────────── */
PYCC_API void pycc_print_int(pycc_int n)    { printf("%lld", (long long)n); }
PYCC_API void pycc_print_float(pycc_float n){ printf("%g", n); }
PYCC_API void pycc_print_str(const char* s) { printf("%s", s?s:"None"); }
PYCC_API void pycc_print_bool(int b)        { printf("%s", b?"True":"False"); }
PYCC_API void pycc_println(void)            { printf("\n"); }
PYCC_API void pycc_print_repr(const char* s){ printf("'%s'", s?s:"None"); }

/* ── Error handling ───────────────────────────────────────────────────── */
PYCC_API int   pycc_errno(void)           { return errno; }
PYCC_API char* pycc_strerror(int e)       { return pycc__strdup(strerror(e)); }
PYCC_API void  pycc_perror(const char* m) { perror(m); }
PYCC_API void  pycc_panic(const char* m)  { fprintf(stderr, "PANIC: %s\n", m); abort(); }

/* ── Windows-specific ─────────────────────────────────────────────────── */
#ifdef PYCC_WIN
PYCC_API void* pycc_win_create_file(const char* p, int acc, int share, int create, int flags) {
    return (void*)CreateFileA(p,(DWORD)acc,(DWORD)share,NULL,(DWORD)create,(DWORD)flags,NULL);
}
PYCC_API int pycc_win_read_file(void* h, char* buf, int sz, int* rd) {
    DWORD r; int ok=ReadFile((HANDLE)h,buf,(DWORD)sz,&r,NULL); if(rd)*rd=(int)r; return ok;
}
PYCC_API int pycc_win_write_file(void* h, const char* buf, int sz, int* wr) {
    DWORD w; int ok=WriteFile((HANDLE)h,buf,(DWORD)sz,&w,NULL); if(wr)*wr=(int)w; return ok;
}
PYCC_API int   pycc_win_close_handle(void* h) { return CloseHandle((HANDLE)h)?0:-1; }
PYCC_API void* pycc_win_create_process(const char* cmd) {
    STARTUPINFOA si; memset(&si,0,sizeof(si)); si.cb=sizeof(si);
    PROCESS_INFORMATION pi; memset(&pi,0,sizeof(pi));
    char* c=pycc__strdup(cmd); CreateProcessA(NULL,c,NULL,NULL,FALSE,0,NULL,NULL,&si,&pi); free(c);
    CloseHandle(pi.hThread); return (void*)pi.hProcess;
}
PYCC_API int   pycc_win_wait_process(void* h) { WaitForSingleObject((HANDLE)h,INFINITE); DWORD c=0; GetExitCodeProcess((HANDLE)h,&c); CloseHandle((HANDLE)h); return (int)c; }
PYCC_API void* pycc_win_reg_open(const char* key, const char* subkey) {
    HKEY root = !strcmp(key,"HKLM")?HKEY_LOCAL_MACHINE:!strcmp(key,"HKCU")?HKEY_CURRENT_USER:HKEY_LOCAL_MACHINE;
    HKEY hk; RegOpenKeyExA(root,subkey,0,KEY_READ,&hk); return (void*)hk;
}
PYCC_API char* pycc_win_reg_get_str(void* hk, const char* name) {
    char buf[4096]; DWORD sz=sizeof(buf),type;
    if(RegQueryValueExA((HKEY)hk,name,NULL,&type,(LPBYTE)buf,&sz)==ERROR_SUCCESS) return pycc__strdup(buf);
    return pycc__strdup("");
}
PYCC_API int  pycc_win_reg_set_str(void* hk, const char* name, const char* val) {
    return RegSetValueExA((HKEY)hk,name,0,REG_SZ,(const BYTE*)val,(DWORD)(strlen(val)+1))==ERROR_SUCCESS?0:-1;
}
PYCC_API void  pycc_win_reg_close(void* hk) { RegCloseKey((HKEY)hk); }
PYCC_API char* pycc_win_get_temp_path(void) { char buf[MAX_PATH]; GetTempPathA(MAX_PATH,buf); return pycc__strdup(buf); }
PYCC_API char* pycc_win_get_appdata(void) { return pycc_getenv_default("APPDATA","C:\\Users\\Public"); }
PYCC_API char* pycc_win_get_username(void) { char buf[256]; DWORD sz=256; GetUserNameA(buf,&sz); return pycc__strdup(buf); }
PYCC_API int   pycc_win_messagebox(const char* title, const char* msg) { return MessageBoxA(NULL,msg,title,MB_OK); }
#endif /* PYCC_WIN */

/* ── CPython embedding ────────────────────────────────────────────────── */
#ifdef PYCC_CPYTHON
#include <Python.h>

PYCC_API int pycc_py_init(const char* prog) {
    if (prog) { wchar_t* wp = Py_DecodeLocale(prog, NULL); Py_SetProgramName(wp); }
    Py_Initialize();
    return Py_IsInitialized() ? 0 : -1;
}
PYCC_API void pycc_py_finalize(void) { if (Py_IsInitialized()) Py_Finalize(); }
PYCC_API pycc_ptr pycc_py_eval(const char* expr) {
    if (!Py_IsInitialized()) return NULL;
    PyObject* main_=PyImport_AddModule("__main__"); PyObject* gbl=PyModule_GetDict(main_);
    return (pycc_ptr)PyRun_String(expr,Py_eval_input,gbl,gbl);
}
PYCC_API pycc_ptr pycc_py_exec(const char* code) {
    if (!Py_IsInitialized()) return NULL;
    PyObject* main_=PyImport_AddModule("__main__"); PyObject* gbl=PyModule_GetDict(main_);
    return (pycc_ptr)PyRun_String(code,Py_file_input,gbl,gbl);
}
PYCC_API pycc_ptr pycc_py_import(const char* mod) { if(!Py_IsInitialized())return NULL; return (pycc_ptr)PyImport_ImportModule(mod); }
PYCC_API pycc_ptr pycc_py_getattr(pycc_ptr obj, const char* name) { if(!obj)return NULL; return (pycc_ptr)PyObject_GetAttrString((PyObject*)obj,name); }
PYCC_API int      pycc_py_setattr(pycc_ptr obj, const char* name, pycc_ptr val) { if(!obj||!val)return -1; return PyObject_SetAttrString((PyObject*)obj,name,(PyObject*)val); }
PYCC_API int      pycc_py_hasattr(pycc_ptr obj, const char* name) { if(!obj)return 0; return PyObject_HasAttrString((PyObject*)obj,name); }
PYCC_API pycc_ptr pycc_py_call(pycc_ptr func, pycc_ptr args) { if(!func)return NULL; PyObject* a=args?(PyObject*)args:PyTuple_New(0); return (pycc_ptr)PyObject_CallObject((PyObject*)func,a); }
PYCC_API pycc_ptr pycc_py_call_str(const char* mod, const char* func, const char* arg) {
    if(!Py_IsInitialized())return NULL;
    PyObject* m=PyImport_ImportModule(mod); if(!m)return NULL;
    PyObject* fn=PyObject_GetAttrString(m,func); if(!fn){Py_DECREF(m);return NULL;}
    PyObject* a=arg?PyTuple_Pack(1,PyUnicode_FromString(arg)):PyTuple_New(0);
    PyObject* r=PyObject_CallObject(fn,a); Py_DECREF(a);Py_DECREF(fn);Py_DECREF(m); return (pycc_ptr)r;
}
PYCC_API char* pycc_py_str(pycc_ptr obj) { if(!obj)return pycc__strdup("None"); PyObject* s=PyObject_Str((PyObject*)obj); if(!s)return pycc__strdup("None"); const char* cs=PyUnicode_AsUTF8(s); char* r=pycc__strdup(cs?cs:"None"); Py_DECREF(s); return r; }
PYCC_API pycc_int   pycc_py_int(pycc_ptr obj)   { return obj?(pycc_int)PyLong_AsLongLong((PyObject*)obj):0; }
PYCC_API pycc_float pycc_py_float(pycc_ptr obj) { return obj?(pycc_float)PyFloat_AsDouble((PyObject*)obj):0.0; }
PYCC_API pycc_ptr   pycc_py_from_str(const char* s)  { return (pycc_ptr)PyUnicode_FromString(s); }
PYCC_API pycc_ptr   pycc_py_from_int(pycc_int n)     { return (pycc_ptr)PyLong_FromLongLong(n); }
PYCC_API pycc_ptr   pycc_py_from_float(pycc_float n) { return (pycc_ptr)PyFloat_FromDouble(n); }
PYCC_API int pycc_py_isinstance(pycc_ptr obj, const char* type_name) {
    if(!obj)return 0; PyObject* bi=PyImport_ImportModule("builtins"); if(!bi)return 0;
    PyObject* tp=PyObject_GetAttrString(bi,type_name); Py_DECREF(bi); if(!tp){PyErr_Clear();return 0;}
    int r=PyObject_IsInstance((PyObject*)obj,tp); Py_DECREF(tp); return r;
}
PYCC_API char*    pycc_py_type_name(pycc_ptr obj) { if(!obj)return pycc__strdup("NoneType"); return pycc__strdup(Py_TYPE((PyObject*)obj)->tp_name); }
PYCC_API pycc_ptr pycc_py_getitem(pycc_ptr obj, pycc_ptr key) { if(!obj||!key)return NULL; return (pycc_ptr)PyObject_GetItem((PyObject*)obj,(PyObject*)key); }
PYCC_API int      pycc_py_setitem(pycc_ptr obj, pycc_ptr key, pycc_ptr val) { if(!obj||!key||!val)return -1; return PyObject_SetItem((PyObject*)obj,(PyObject*)key,(PyObject*)val); }
PYCC_API pycc_int pycc_py_len(pycc_ptr obj) { if(!obj)return 0; return (pycc_int)PyObject_Length((PyObject*)obj); }
PYCC_API int      pycc_py_err_occurred(void) { return PyErr_Occurred()?1:0; }
PYCC_API char*    pycc_py_err_str(void) {
    if(!PyErr_Occurred())return pycc__strdup("");
    PyObject *tp,*val,*tb; PyErr_Fetch(&tp,&val,&tb); PyErr_NormalizeException(&tp,&val,&tb);
    char* r=val?pycc_py_str((pycc_ptr)val):pycc__strdup("Unknown error");
    Py_XDECREF(tp);Py_XDECREF(val);Py_XDECREF(tb); return r;
}
PYCC_API void pycc_py_err_clear(void) { PyErr_Clear(); }
#endif /* PYCC_CPYTHON */