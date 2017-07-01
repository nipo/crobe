#include "common.h"

struct nvmc_s {
    volatile uint32_t  reserved0[256];
    volatile uint32_t  ready;
    volatile uint32_t  reserved1[64];
    volatile uint32_t  config;
    volatile uint32_t  erasepage;
    volatile uint32_t  eraseall;
    volatile uint32_t  eraseprotectedpage;
    volatile uint32_t  eraseuicr;
};

#define NVMC_ADDR (void*)0x4001e000
#define NVMC_READY 1
#define NVMC_CONFIG_NONE 0
#define NVMC_CONFIG_WEN  1
#define NVMC_CONFIG_EEN  2

void flash_erase(uintptr_t addr, size_t size, size_t page_size)
{
    uintptr_t end = addr + size;
    struct nvmc_s *nvmc = NVMC_ADDR;
    
    addr = addr & (page_size - 1);

    nvmc->config = NVMC_CONFIG_EEN;

    while (addr < end) {
        while (!(nvmc->ready & NVMC_READY))
            ;

        nvmc->erasepage = addr;
        addr += page_size;
    }

    while (!(nvmc->ready & NVMC_READY))
        ;

    nvmc->config = NVMC_CONFIG_NONE;
}

void flash_write(uintptr_t dest_, const void *src_, size_t bytes)
{
    const uint32_t *src = src_;
    volatile uint32_t *dst = (void *)dest_;
    size_t words = bytes / 4;
    size_t i;
    struct nvmc_s *nvmc = NVMC_ADDR;

    nvmc->config = NVMC_CONFIG_WEN;
    
    for (i = 0; i < words; ++i) {
        while (!(nvmc->ready & NVMC_READY))
            ;
        
        dst[i] = src[i];
    }

    while (!(nvmc->ready & NVMC_READY))
        ;

    nvmc->config = NVMC_CONFIG_NONE;
}
