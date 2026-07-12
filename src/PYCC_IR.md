# PyCC IR - Custom Intermediate Representation
# Replaces llvmlite. Emits x86_64 assembly via NASM/zig cc.
#
# Design principles:
# - Simple flat instruction list per function
# - SSA-lite: temporaries are named %0, %1, %2...
# - Types: i64, f64, i8, i1, ptr
# - No implicit conversions
#
# Example PyCC IR for: x = 5; print(x)
#
# .func main() -> i32
#   %0 = const i64 5
#   store i64 %0 -> @x
#   %1 = load i64 @x
#   call printf("%lld\n", %1)
#   ret i32 0
# .endfunc
#
# Instruction set:
#
# ARITHMETIC
#   %t = add i64 %a, %b
#   %t = sub i64 %a, %b
#   %t = mul i64 %a, %b
#   %t = div i64 %a, %b
#   %t = mod i64 %a, %b
#   %t = neg i64 %a
#   %t = fadd f64 %a, %b
#   %t = fsub f64 %a, %b
#   %t = fmul f64 %a, %b
#   %t = fdiv f64 %a, %b
#
# MEMORY
#   %t = alloca i64
#   store i64 %val -> @name
#   %t = load i64 @name
#   %t = const i64 <value>
#   %t = sconst "<string>"
#
# CONTROL FLOW
#   label <name>:
#   jmp <label>
#   jz %cond, <label>
#   jnz %cond, <label>
#
# COMPARE
#   %t = cmp_eq i64 %a, %b
#   %t = cmp_ne i64 %a, %b
#   %t = cmp_lt i64 %a, %b
#   %t = cmp_gt i64 %a, %b
#   %t = cmp_le i64 %a, %b
#   %t = cmp_ge i64 %a, %b
#
# FUNCTIONS
#   .func <name>(<type> <arg>, ...) -> <type>
#   ret <type> %val
#   %t = call <name>(<arg>, ...)
#   .endfunc
#
# EXTERN
#   .extern <name>
#
# GLOBAL
#   .global @<name> i64 <value>
#   .global @<name> str "<value>"
#
# TYPE CONVERSIONS
#   %t = itof f64 %a    # i64 -> f64
#   %t = ftoi i64 %a    # f64 -> i64
#   %t = zext i64 %a    # i1 -> i64
#   %t = trunc i8 %a    # i64 -> i8
