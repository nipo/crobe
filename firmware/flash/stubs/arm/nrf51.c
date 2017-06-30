typedef unsigned long uint32_t;
typedef unsigned long uintptr_t;
typedef unsigned long size_t;

#define NVMC_READY       *((volatile uint32_t *)0x4001e400)
#define NVMC_READY_BUSY  0
#define NVMC_READY_READY 1
#define NVMC_CONFIG      *((volatile uint32_t *)0x4001e504)
#define NVMC_CONFIG_NONE 0
#define NVMC_CONFIG_WEN  1
#define NVMC_CONFIG_EEN  2
#define NVMC_ERASEPAGE   *((volatile uint32_t *)0x4001e508)
#define NVMC_ERASEUICR   *((volatile uint32_t *)0x4001e514)
#define FICR_CODEPAGESIZE *((volatile uint32_t *)0x10000010)

void flash_erase(uintptr_t addr, size_t size)
{
    size_t code_page_size = FICR_CODEPAGESIZE;
    uintptr_t end = addr + size;

    addr = addr & (code_page_size - 1);

    NVMC_CONFIG = NVMC_CONFIG_EEN;

    while (addr < end) {
        while (!(NVMC_READY & NVMC_READY_READY))
            ;

        NVMC_ERASEPAGE = addr;
    }

    while (!(NVMC_READY & NVMC_READY_READY))
        ;

    NVMC_CONFIG = NVMC_CONFIG_NONE;
}

void flash_write(uintptr_t dest_, const void *src_, size_t bytes)
{
    const uint32_t *src = src_;
    uint32_t *dst = (void *)dest_;
    size_t words = bytes / 4;

    NVMC_CONFIG = NVMC_CONFIG_WEN;
    
    while (words) {
        while (!(NVMC_READY & NVMC_READY_READY))
            ;
        *dst++ = *src++;
        words--;
    }

    while (!(NVMC_READY & NVMC_READY_READY))
        ;

    NVMC_CONFIG = NVMC_CONFIG_NONE;
}
