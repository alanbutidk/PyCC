/**
 * PyCCRuntime.h - PyCC Native Runtime Library
 * Provides syscall wrappers, socket, threading, signals, mmap,
 * process management, crypto, dynamic loading, and Windows APIs.
 * Compiled to PyCCRuntime.dll (Windows) / libPyCCRuntime.so (Linux/Mac)
 */
#pragma once
#ifndef PYCC_RUNTIME_H
#define PYCC_RUNTIME_H

#include <stdint.h>
#include <stddef.h>

#ifdef _WIN32
  #define PYCC_API __declspec(dllexport)
  #define PYCC_WIN 1
#else
  #define PYCC_API __attribute__((visibility("default")))
  #define PYCC_POSIX 1
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ── Types ─────────────────────────────────────────────────────────── */
typedef int64_t  pycc_int;
typedef double   pycc_float;
typedef char*    pycc_str;
typedef void*    pycc_ptr;
typedef int      pycc_fd;
typedef int      pycc_bool;

/* ── File I/O ──────────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_fopen(const char* path, const char* mode);
PYCC_API int       pycc_fclose(pycc_ptr fp);
PYCC_API pycc_int  pycc_fread(pycc_ptr buf, pycc_int sz, pycc_ptr fp);
PYCC_API pycc_int  pycc_fwrite(const char* buf, pycc_int sz, pycc_ptr fp);
PYCC_API char*     pycc_fgets(char* buf, int sz, pycc_ptr fp);
PYCC_API int       pycc_fputs(const char* s, pycc_ptr fp);
PYCC_API int       pycc_fseek(pycc_ptr fp, pycc_int off, int whence);
PYCC_API pycc_int  pycc_ftell(pycc_ptr fp);
PYCC_API int       pycc_feof(pycc_ptr fp);
PYCC_API void      pycc_fflush(pycc_ptr fp);
PYCC_API char*     pycc_freadall(const char* path);
PYCC_API int       pycc_fwriteall(const char* path, const char* data);
PYCC_API int       pycc_fappend(const char* path, const char* data);

/* ── Low-level POSIX fd ops ─────────────────────────────────────────── */
PYCC_API pycc_fd   pycc_open(const char* path, int flags, int mode);
PYCC_API int       pycc_close(pycc_fd fd);
PYCC_API pycc_int  pycc_read(pycc_fd fd, void* buf, pycc_int sz);
PYCC_API pycc_int  pycc_write(pycc_fd fd, const void* buf, pycc_int sz);
PYCC_API pycc_int  pycc_lseek(pycc_fd fd, pycc_int off, int whence);
PYCC_API int       pycc_dup(pycc_fd fd);
PYCC_API int       pycc_dup2(pycc_fd oldfd, pycc_fd newfd);
PYCC_API int       pycc_pipe(int fds[2]);
PYCC_API int       pycc_fcntl(pycc_fd fd, int cmd, int arg);
PYCC_API int       pycc_isatty(pycc_fd fd);

/* ── File system ────────────────────────────────────────────────────── */
PYCC_API int       pycc_unlink(const char* path);
PYCC_API int       pycc_rename(const char* src, const char* dst);
PYCC_API int       pycc_mkdir(const char* path, int mode);
PYCC_API int       pycc_rmdir(const char* path);
PYCC_API int       pycc_makedirs(const char* path, int mode);
PYCC_API int       pycc_removedirs(const char* path);
PYCC_API int       pycc_chmod(const char* path, int mode);
PYCC_API int       pycc_chown(const char* path, int uid, int gid);
PYCC_API int       pycc_symlink(const char* src, const char* dst);
PYCC_API int       pycc_link(const char* src, const char* dst);
PYCC_API char*     pycc_readlink(const char* path);
PYCC_API int       pycc_truncate(const char* path, pycc_int sz);
PYCC_API int       pycc_access(const char* path, int mode);
PYCC_API int       pycc_stat_isfile(const char* path);
PYCC_API int       pycc_stat_isdir(const char* path);
PYCC_API pycc_int  pycc_stat_size(const char* path);
PYCC_API pycc_int  pycc_stat_mtime(const char* path);
PYCC_API char*     pycc_getcwd(void);
PYCC_API int       pycc_chdir(const char* path);
PYCC_API char*     pycc_realpath(const char* path);
PYCC_API char*     pycc_basename(const char* path);
PYCC_API char*     pycc_dirname(const char* path);
PYCC_API char*     pycc_path_join(const char* a, const char* b);
PYCC_API char*     pycc_path_join3(const char* a, const char* b, const char* c);
PYCC_API char**    pycc_listdir(const char* path, pycc_int* count);
PYCC_API int       pycc_path_exists(const char* path);
PYCC_API char*     pycc_path_abspath(const char* path);

/* ── Process ────────────────────────────────────────────────────────── */
PYCC_API int       pycc_getpid(void);
PYCC_API int       pycc_getppid(void);
PYCC_API int       pycc_system(const char* cmd);
PYCC_API pycc_ptr  pycc_popen(const char* cmd, const char* mode);
PYCC_API int       pycc_pclose(pycc_ptr fp);
PYCC_API char*     pycc_popen_read(const char* cmd);
PYCC_API int       pycc_fork(void);
PYCC_API int       pycc_waitpid(int pid, int* status, int opts);
PYCC_API int       pycc_execv(const char* path, char* const argv[]);
PYCC_API int       pycc_execvp(const char* file, char* const argv[]);
PYCC_API void      pycc_exit(int code);
PYCC_API void      pycc_abort(void);

/* ── Environment ────────────────────────────────────────────────────── */
PYCC_API char*     pycc_getenv(const char* key);
PYCC_API int       pycc_setenv(const char* key, const char* val, int overwrite);
PYCC_API int       pycc_unsetenv(const char* key);
PYCC_API char*     pycc_getenv_default(const char* key, const char* def);

/* ── Signals ────────────────────────────────────────────────────────── */
PYCC_API int       pycc_kill(int pid, int sig);
PYCC_API int       pycc_raise_sig(int sig);
PYCC_API void      pycc_signal_ignore(int sig);
PYCC_API void      pycc_signal_default(int sig);

/* ── Sockets ────────────────────────────────────────────────────────── */
PYCC_API pycc_fd   pycc_socket(int domain, int type, int proto);
PYCC_API int       pycc_bind(pycc_fd fd, const char* host, int port);
PYCC_API int       pycc_listen(pycc_fd fd, int backlog);
PYCC_API pycc_fd   pycc_accept(pycc_fd fd, char* client_host, int* client_port);
PYCC_API int       pycc_connect(pycc_fd fd, const char* host, int port);
PYCC_API pycc_int  pycc_send(pycc_fd fd, const char* buf, pycc_int sz, int flags);
PYCC_API pycc_int  pycc_recv(pycc_fd fd, char* buf, pycc_int sz, int flags);
PYCC_API int       pycc_setsockopt(pycc_fd fd, int level, int opt, int val);
PYCC_API int       pycc_getsockopt(pycc_fd fd, int level, int opt, int* val);
PYCC_API int       pycc_socket_close(pycc_fd fd);
PYCC_API int       pycc_gethostname(char* buf, int sz);
PYCC_API char*     pycc_gethostbyname(const char* host);
PYCC_API int       pycc_setnonblocking(pycc_fd fd);
PYCC_API int       pycc_select(pycc_fd fd, int read, int write, int timeout_ms);
PYCC_API char*     pycc_socket_send_recv(const char* host, int port, const char* data);

/* ── Threading ──────────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_thread_create(void (*fn)(void*), void* arg);
PYCC_API int       pycc_thread_join(pycc_ptr thread);
PYCC_API void      pycc_thread_detach(pycc_ptr thread);
PYCC_API pycc_ptr  pycc_mutex_create(void);
PYCC_API int       pycc_mutex_lock(pycc_ptr mutex);
PYCC_API int       pycc_mutex_unlock(pycc_ptr mutex);
PYCC_API int       pycc_mutex_trylock(pycc_ptr mutex);
PYCC_API void      pycc_mutex_destroy(pycc_ptr mutex);
PYCC_API pycc_ptr  pycc_cond_create(void);
PYCC_API int       pycc_cond_wait(pycc_ptr cond, pycc_ptr mutex);
PYCC_API int       pycc_cond_signal(pycc_ptr cond);
PYCC_API int       pycc_cond_broadcast(pycc_ptr cond);
PYCC_API void      pycc_cond_destroy(pycc_ptr cond);
PYCC_API pycc_ptr  pycc_rwlock_create(void);
PYCC_API int       pycc_rwlock_rdlock(pycc_ptr rw);
PYCC_API int       pycc_rwlock_wrlock(pycc_ptr rw);
PYCC_API int       pycc_rwlock_unlock(pycc_ptr rw);
PYCC_API void      pycc_rwlock_destroy(pycc_ptr rw);
PYCC_API int       pycc_thread_self_id(void);
PYCC_API void      pycc_thread_sleep_ms(int ms);

/* ── Memory mapping ──────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_mmap(pycc_int sz, int prot, int flags, pycc_fd fd, pycc_int off);
PYCC_API int       pycc_munmap(pycc_ptr addr, pycc_int sz);
PYCC_API int       pycc_mprotect(pycc_ptr addr, pycc_int sz, int prot);
PYCC_API pycc_ptr  pycc_mmap_file(const char* path, pycc_int* sz);
PYCC_API int       pycc_munmap_file(pycc_ptr addr, pycc_int sz);

/* ── Dynamic loading ─────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_dlopen(const char* path);
PYCC_API pycc_ptr  pycc_dlsym(pycc_ptr handle, const char* sym);
PYCC_API int       pycc_dlclose(pycc_ptr handle);
PYCC_API char*     pycc_dlerror(void);

/* ── Crypto / hashing ────────────────────────────────────────────────── */
PYCC_API char*     pycc_sha256(const char* data, pycc_int sz);
PYCC_API char*     pycc_md5(const char* data, pycc_int sz);
PYCC_API char*     pycc_sha1(const char* data, pycc_int sz);
PYCC_API int       pycc_rand_bytes(char* buf, pycc_int sz);
PYCC_API char*     pycc_base64_encode(const char* data, pycc_int sz);
PYCC_API char*     pycc_base64_decode(const char* data, pycc_int* out_sz);
PYCC_API uint32_t  pycc_crc32(const char* data, pycc_int sz);
PYCC_API uint64_t  pycc_fnv1a(const char* data, pycc_int sz);

/* ── String utilities ────────────────────────────────────────────────── */
PYCC_API char*     pycc_str_upper(const char* s);
PYCC_API char*     pycc_str_lower(const char* s);
PYCC_API char*     pycc_str_strip(const char* s);
PYCC_API char*     pycc_str_lstrip(const char* s);
PYCC_API char*     pycc_str_rstrip(const char* s);
PYCC_API char*     pycc_str_replace(const char* s, const char* old, const char* new_s);
PYCC_API char**    pycc_str_split(const char* s, const char* delim, pycc_int* count);
PYCC_API char*     pycc_str_join(const char* sep, char** parts, pycc_int count);
PYCC_API int       pycc_str_startswith(const char* s, const char* prefix);
PYCC_API int       pycc_str_endswith(const char* s, const char* suffix);
PYCC_API char*     pycc_str_repeat(const char* s, pycc_int n);
PYCC_API pycc_int  pycc_str_find(const char* s, const char* sub);
PYCC_API pycc_int  pycc_str_count(const char* s, const char* sub);
PYCC_API char*     pycc_str_slice(const char* s, pycc_int start, pycc_int end);
PYCC_API char*     pycc_str_format(const char* fmt, ...);
PYCC_API char*     pycc_str_zfill(const char* s, pycc_int width);
PYCC_API char*     pycc_str_center(const char* s, pycc_int width, char fill);
PYCC_API char*     pycc_str_ljust(const char* s, pycc_int width, char fill);
PYCC_API char*     pycc_str_rjust(const char* s, pycc_int width, char fill);
PYCC_API int       pycc_str_isdigit(const char* s);
PYCC_API int       pycc_str_isalpha(const char* s);
PYCC_API int       pycc_str_isalnum(const char* s);
PYCC_API int       pycc_str_isspace(const char* s);
PYCC_API int       pycc_str_isupper(const char* s);
PYCC_API int       pycc_str_islower(const char* s);
PYCC_API char*     pycc_int_to_str(pycc_int n);
PYCC_API char*     pycc_float_to_str(pycc_float n);
PYCC_API pycc_int  pycc_str_to_int(const char* s);
PYCC_API pycc_float pycc_str_to_float(const char* s);
PYCC_API char*     pycc_str_from_char(char c);
PYCC_API char*     pycc_str_concat(const char* a, const char* b);
PYCC_API char*     pycc_str_concat3(const char* a, const char* b, const char* c);

/* ── List / array ────────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_list_new(pycc_int capacity);
PYCC_API int       pycc_list_append(pycc_ptr list, pycc_int val);
PYCC_API int       pycc_list_append_str(pycc_ptr list, const char* val);
PYCC_API pycc_int  pycc_list_get(pycc_ptr list, pycc_int idx);
PYCC_API char*     pycc_list_get_str(pycc_ptr list, pycc_int idx);
PYCC_API int       pycc_list_set(pycc_ptr list, pycc_int idx, pycc_int val);
PYCC_API pycc_int  pycc_list_len(pycc_ptr list);
PYCC_API int       pycc_list_pop(pycc_ptr list, pycc_int idx);
PYCC_API int       pycc_list_clear(pycc_ptr list);
PYCC_API pycc_ptr  pycc_list_copy(pycc_ptr list);
PYCC_API int       pycc_list_sort(pycc_ptr list);
PYCC_API int       pycc_list_reverse(pycc_ptr list);
PYCC_API pycc_int  pycc_list_index(pycc_ptr list, pycc_int val);
PYCC_API pycc_int  pycc_list_count(pycc_ptr list, pycc_int val);
PYCC_API void      pycc_list_free(pycc_ptr list);

/* ── Dict / hashmap ──────────────────────────────────────────────────── */
PYCC_API pycc_ptr  pycc_dict_new(void);
PYCC_API int       pycc_dict_set(pycc_ptr dict, const char* key, const char* val);
PYCC_API int       pycc_dict_set_int(pycc_ptr dict, const char* key, pycc_int val);
PYCC_API char*     pycc_dict_get(pycc_ptr dict, const char* key);
PYCC_API pycc_int  pycc_dict_get_int(pycc_ptr dict, const char* key, pycc_int def);
PYCC_API int       pycc_dict_has(pycc_ptr dict, const char* key);
PYCC_API int       pycc_dict_del(pycc_ptr dict, const char* key);
PYCC_API pycc_int  pycc_dict_len(pycc_ptr dict);
PYCC_API char**    pycc_dict_keys(pycc_ptr dict, pycc_int* count);
PYCC_API char**    pycc_dict_values(pycc_ptr dict, pycc_int* count);
PYCC_API pycc_ptr  pycc_dict_copy(pycc_ptr dict);
PYCC_API void      pycc_dict_update(pycc_ptr dst, pycc_ptr src);
PYCC_API void      pycc_dict_clear(pycc_ptr dict);
PYCC_API void      pycc_dict_free(pycc_ptr dict);

/* ── Time ────────────────────────────────────────────────────────────── */
PYCC_API pycc_int  pycc_time_now(void);
PYCC_API pycc_float pycc_time_now_f(void);
PYCC_API void      pycc_sleep(pycc_float seconds);
PYCC_API void      pycc_sleep_ms(pycc_int ms);
PYCC_API char*     pycc_time_str(void);
PYCC_API char*     pycc_time_format(const char* fmt);

/* ── Math extras ─────────────────────────────────────────────────────── */
PYCC_API pycc_float pycc_math_pow(pycc_float base, pycc_float exp);
PYCC_API pycc_float pycc_math_sqrt(pycc_float x);
PYCC_API pycc_float pycc_math_log(pycc_float x);
PYCC_API pycc_float pycc_math_log2(pycc_float x);
PYCC_API pycc_float pycc_math_log10(pycc_float x);
PYCC_API pycc_int   pycc_math_gcd(pycc_int a, pycc_int b);
PYCC_API pycc_int   pycc_math_lcm(pycc_int a, pycc_int b);
PYCC_API pycc_float pycc_math_hypot(pycc_float a, pycc_float b);

/* ── Print helpers ───────────────────────────────────────────────────── */
PYCC_API void      pycc_print_int(pycc_int n);
PYCC_API void      pycc_print_float(pycc_float n);
PYCC_API void      pycc_print_str(const char* s);
PYCC_API void      pycc_print_bool(int b);
PYCC_API void      pycc_println(void);
PYCC_API void      pycc_print_repr(const char* s);

/* ── Error handling ──────────────────────────────────────────────────── */
PYCC_API int       pycc_errno(void);
PYCC_API char*     pycc_strerror(int err);
PYCC_API void      pycc_perror(const char* msg);
PYCC_API void      pycc_panic(const char* msg);

/* ── Windows-specific ────────────────────────────────────────────────── */
#ifdef PYCC_WIN
PYCC_API void*     pycc_win_create_file(const char* path, int access, int share, int create, int flags);
PYCC_API int       pycc_win_read_file(void* handle, char* buf, int sz, int* read);
PYCC_API int       pycc_win_write_file(void* handle, const char* buf, int sz, int* written);
PYCC_API int       pycc_win_close_handle(void* handle);
PYCC_API void*     pycc_win_create_process(const char* cmd);
PYCC_API int       pycc_win_wait_process(void* handle);
PYCC_API void*     pycc_win_reg_open(const char* key, const char* subkey);
PYCC_API char*     pycc_win_reg_get_str(void* hkey, const char* name);
PYCC_API int       pycc_win_reg_set_str(void* hkey, const char* name, const char* val);
PYCC_API void      pycc_win_reg_close(void* hkey);
PYCC_API char*     pycc_win_get_temp_path(void);
PYCC_API char*     pycc_win_get_appdata(void);
PYCC_API char*     pycc_win_get_username(void);
PYCC_API int       pycc_win_messagebox(const char* title, const char* msg);
#endif

#ifdef __cplusplus
}
#endif

#endif /* PYCC_RUNTIME_H */

/* ── CPython embedding (full Python support) ─────────────────────────── */
/* Enable with -DPYCC_CPYTHON. Requires Python dev headers.               */
#ifdef PYCC_CPYTHON
  #include <Python.h>

  PYCC_API int       pycc_py_init(const char* prog);
  PYCC_API void      pycc_py_finalize(void);
  PYCC_API pycc_ptr  pycc_py_eval(const char* expr);
  PYCC_API pycc_ptr  pycc_py_exec(const char* code);
  PYCC_API pycc_ptr  pycc_py_import(const char* mod);
  PYCC_API pycc_ptr  pycc_py_getattr(pycc_ptr obj, const char* name);
  PYCC_API int       pycc_py_setattr(pycc_ptr obj, const char* name, pycc_ptr val);
  PYCC_API int       pycc_py_hasattr(pycc_ptr obj, const char* name);
  PYCC_API pycc_ptr  pycc_py_call(pycc_ptr func, pycc_ptr args);
  PYCC_API pycc_ptr  pycc_py_call_str(const char* mod, const char* func, const char* arg);
  PYCC_API char*     pycc_py_str(pycc_ptr obj);
  PYCC_API pycc_int  pycc_py_int(pycc_ptr obj);
  PYCC_API pycc_float pycc_py_float(pycc_ptr obj);
  PYCC_API pycc_ptr  pycc_py_from_str(const char* s);
  PYCC_API pycc_ptr  pycc_py_from_int(pycc_int n);
  PYCC_API pycc_ptr  pycc_py_from_float(pycc_float n);
  PYCC_API int       pycc_py_isinstance(pycc_ptr obj, const char* type_name);
  PYCC_API char*     pycc_py_type_name(pycc_ptr obj);
  PYCC_API pycc_ptr  pycc_py_getitem(pycc_ptr obj, pycc_ptr key);
  PYCC_API int       pycc_py_setitem(pycc_ptr obj, pycc_ptr key, pycc_ptr val);
  PYCC_API pycc_int  pycc_py_len(pycc_ptr obj);
  PYCC_API int       pycc_py_err_occurred(void);
  PYCC_API char*     pycc_py_err_str(void);
  PYCC_API void      pycc_py_err_clear(void);
#endif
