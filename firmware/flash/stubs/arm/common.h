#ifndef STUB_COMMON
#define STUB_COMMON

typedef unsigned long uint32_t;
typedef unsigned short uint16_t;
typedef unsigned char uint8_t;
typedef unsigned long uintptr_t;
typedef unsigned long size_t;

#define REG32(x) *((uint32_t*)(x))

void flash_erase(uintptr_t addr, size_t bytes, size_t page_size);
void flash_write(uintptr_t dest, const void *src, size_t bytes);

#endif
