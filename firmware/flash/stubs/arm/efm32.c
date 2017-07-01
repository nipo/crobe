#include "common.h"

#define MSC (struct msc_s*)0x400c0000

struct msc_s {
    volatile uint32_t r0;
    volatile uint32_t r1;
    volatile uint32_t writectrl;
    volatile uint32_t writecmd;
    volatile uint32_t addrb;
    volatile uint32_t r5;
    volatile uint32_t wdata;
    volatile uint32_t status;
    volatile uint32_t r8;
    volatile uint32_t r9;
    volatile uint32_t r10;
    volatile uint32_t r11;
    volatile uint32_t r12;
    volatile uint32_t r13;
    volatile uint32_t r14;
    volatile uint32_t lock;
};

#define LOCK_KEY     0x1b71
#define WRITECTRL_WREN 0x1
#define WRITECMD_LADDRIM 0x1
#define WRITECMD_ERASEPAGE 0x2
#define WRITECMD_WRITEONCE 0x8
#define STATUS_BUSY   0x1
#define STATUS_LOCKED 0x2
#define STATUS_INVADDR 0x4
#define STATUS_WDATAREADY 0x8

void flash_erase(uintptr_t addr, size_t size, size_t page_size)
{
    uintptr_t end = addr + size;
    struct msc_s *msc = MSC;
    
    addr = addr & (page_size - 1);

    do {
        msc->lock = LOCK_KEY;
    } while (msc->lock);
    msc->writectrl = WRITECTRL_WREN;

    while (addr < end) {
        msc->addrb = addr;
        msc->writecmd = WRITECMD_LADDRIM;
        msc->writecmd = WRITECMD_ERASEPAGE;

        addr += page_size;

        while (msc->status & STATUS_BUSY)
            ;
    }

    while (msc->status & STATUS_BUSY)
        ;

    msc->writectrl = 0;
    msc->lock = 0;
}

void flash_write(uintptr_t dst, const void *src_, size_t bytes)
{
    const uint32_t *src = src_;
    size_t words = bytes / 4;
    size_t i;
    struct msc_s *msc = MSC;

    msc->lock = LOCK_KEY;
    msc->writectrl = WRITECTRL_WREN;

#ifndef GECKO
    msc->addrb = dst;
    msc->writecmd = WRITECMD_LADDRIM;
#endif
    
    for (i = 0; i < words; ++i) {
#ifdef GECKO
        msc->addrb = dst + i * 4;
        msc->writecmd = WRITECMD_LADDRIM;
#endif

        while (!(msc->status & STATUS_WDATAREADY))
            ;

        msc->wdata = src[i];
        msc->writecmd = WRITECMD_WRITEONCE;

        while (msc->status & STATUS_BUSY)
            ;
    }

    msc->writectrl = 0;
    msc->lock = 0;
}
