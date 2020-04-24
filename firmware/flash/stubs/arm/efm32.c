#include "common.h"

#if defined(EFM32S0) || defined(EFM32S0G)
#define MSC (struct msc_s*)0x400c0000
#elif defined(EFM32S1)
#define MSC (struct msc_s*)0x400e0000
#elif defined(EFM32S1GG)
#define MSC (struct msc_s*)0x40000000
#else
# error
#endif

struct msc_s {
    volatile uint32_t ctrl;
    volatile uint32_t readctrl;
    volatile uint32_t writectrl;
    volatile uint32_t writecmd;
    volatile uint32_t addrb;
    volatile uint32_t pad0;
    volatile uint32_t wdata;
    volatile uint32_t status;
#if defined(EFM32S1) || defined(EFM32S1GG)
    volatile uint32_t pad1[4];
#else
    volatile uint32_t pad1[3];
#endif
    volatile uint32_t irq[4];
    volatile uint32_t lock;
    volatile uint32_t cachecmd;
    volatile uint32_t cachehits;
    volatile uint32_t cachemisses;
    volatile uint32_t pad2;
    volatile uint32_t masslock;
#if 0 // defined(EFM32S1) || defined(EFM32S1GG)
    volatile uint32_t pad3;
    volatile uint32_t startup;
    volatile uint32_t pad4[4];
    volatile uint32_t bankswitchlock;
    volatile uint32_t cmd;
    volatile uint32_t pad5[6];
    volatile uint32_t bootloaderctrl;
    volatile uint32_t aapunlockcmd;
    volatile uint32_t cacheconfig0;
    volatile uint32_t pad6[2];
    volatile uint32_t ramctrl;
    volatile uint32_t eccctrl;
    volatile uint32_t rameccaddr;
    volatile uint32_t ram1eccaddr;
#endif
};

#define LOCK_KEY     0x1b71
#define WRITECTRL_WREN 0x1
#define WRITECMD_LADDRIM 0x1
#define WRITECMD_ERASEPAGE 0x2
#define WRITECMD_WRITEONCE 0x8
#define STATUS_BUSY   0x1
#define STATUS_LOCKED 0x2
#define STATUS_INVADDR 0x4

void flash_erase(uintptr_t addr, size_t size, size_t page_size)
{
    uintptr_t end = addr + size;
    struct msc_s *msc = MSC;

    addr = addr & ~(page_size - 1);

    while (msc->status & STATUS_BUSY)
        ;

    msc->lock = LOCK_KEY;
    msc->writectrl = WRITECTRL_WREN;

    while (addr < end) {
        msc->addrb = addr;
        msc->writecmd = WRITECMD_LADDRIM;

        msc->writecmd = WRITECMD_ERASEPAGE;
        addr += page_size;

        while (msc->status & STATUS_BUSY)
            ;
    }

    msc->writectrl = 0;
    msc->lock = 0;
}

void flash_write(uintptr_t dst, const void *src_, size_t bytes)
{
    const uint32_t *src = src_;
    size_t words = bytes / 4;
    size_t i;
    struct msc_s *msc = MSC;

    while (msc->status & STATUS_BUSY)
        ;

    msc->lock = LOCK_KEY;
    msc->writectrl = WRITECTRL_WREN;

#ifndef EFM32S0G
    msc->addrb = dst;
    msc->writecmd = WRITECMD_LADDRIM;
#endif
    
    for (i = 0; i < words; ++i) {
#ifdef EFM32S0G
        msc->addrb = dst + i * 4;
        msc->writecmd = WRITECMD_LADDRIM;
#endif

        msc->wdata = src[i];
        msc->writecmd = WRITECMD_WRITEONCE;

        while (msc->status & STATUS_BUSY)
            ;
    }

    msc->writectrl = 0;
    msc->lock = 0;
}
