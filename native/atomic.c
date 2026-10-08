#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

/* These are compiler intrinsics on Win64, not kernel32 DLL exports. */
__declspec(dllexport) int32_t mc_exchange32(volatile LONG *p, int32_t value) {
    return InterlockedExchange(p, value);
}
__declspec(dllexport) int64_t mc_exchange64(volatile LONG64 *p, int64_t value) {
    return InterlockedExchange64(p, value);
}
__declspec(dllexport) int64_t mc_load64(volatile LONG64 *p) {
    return InterlockedCompareExchange64(p, 0, 0);
}
