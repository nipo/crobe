#include "common.h"

#define FLASH ((struct flash_s *)FLASH_BASE)

struct flash_s {
    volatile uint32_t access_control;
    volatile uint32_t key;
    volatile uint32_t optkey;
    volatile uint32_t status;
    volatile uint32_t control;
    volatile uint32_t address;
    uint32_t pad;
    volatile uint32_t option;
    volatile uint32_t write_protect;
};

#define KEY_RDPRT          0x00A5
#define KEY_1              0x45670123
#define KEY_2              0xCDEF89AB
#define STATUS_BUSY        0x00000001
#define STATUS_PAGE_ERR    0x00000004
#define STATUS_PROT_ERR    0x00000010
#define STATUS_EOP         0x00000020
#define CONTROL_PROG       0x00000001
#define CONTROL_ERASE      0x00000002
#define CONTROL_MASS_ERASE 0x00000004
#define CONTROL_OPT_PROG   0x00000010
#define CONTROL_OPT_ERASE  0x00000020
#define CONTROL_OPT_WRE    0x00000200
#define CONTROL_START      0x00000040
#define CONTROL_LOCK       0x00000080

static inline __attribute__((always_inline))
void unlock(struct flash_s *flash)
{
    while (flash->status & STATUS_BUSY)
        ;

    if (flash->control & CONTROL_LOCK)
        flash->control = 0;
    else
        flash->control = CONTROL_LOCK;

    while (flash->status & STATUS_BUSY)
        ;

    flash->key = KEY_1;
    flash->key = KEY_2;
}

void flash_erase(uintptr_t addr, size_t bytes, size_t page_size)
{
    uintptr_t end = addr + bytes;
    struct flash_s *flash = FLASH;

    addr &= ~(page_size - 1);

    unlock(flash);

    while (addr < end) {
        flash->control |= CONTROL_ERASE;

        flash->address = addr;

        flash->control |= CONTROL_START;

        while (flash->status & STATUS_BUSY)
            ;

        addr += page_size;
    }

    flash->control = CONTROL_LOCK;
}

void flash_write(uintptr_t dest_, const void *src_, size_t size)
{
    struct flash_s *flash = FLASH;
    volatile uint16_t *dest = (uint16_t*)(dest_);
    const uint16_t *src = (uint16_t*)src_;

    unlock(flash);

    for (size_t i = 0; i < size / 2; i++) {
        flash->control |= CONTROL_PROG;

        dest[i] = src[i];

        while (flash->status & STATUS_BUSY)
            ;
    }

    flash->control = CONTROL_LOCK;
}

void opt_erase(void)
{
    struct flash_s *flash = FLASH;

    unlock(flash);

    flash->optkey = KEY_1;
    flash->optkey = KEY_2;

    flash->control |= CONTROL_OPT_ERASE | CONTROL_OPT_WRE;
    flash->control |= CONTROL_OPT_ERASE | CONTROL_OPT_WRE | CONTROL_START;

    while (flash->status & STATUS_BUSY)
        ;

    flash->control = CONTROL_LOCK;
}

void mass_erase(void)
{
    struct flash_s *flash = FLASH;

    unlock(flash);
    flash->control = CONTROL_MASS_ERASE;
    flash->control |= CONTROL_START;

    while (flash->status & STATUS_BUSY)
        ;

    flash->control = CONTROL_LOCK;
}

void opt_write(uintptr_t dest_, const void *src_, size_t size)
{
    struct flash_s *flash = FLASH;
    volatile uint16_t *dest = (uint16_t*)(dest_);
    const uint16_t *src = (uint16_t*)src_;

    unlock(flash);

    flash->optkey = KEY_1;
    flash->optkey = KEY_2;

    flash->control |= CONTROL_OPT_ERASE;
    flash->control |= CONTROL_START;

    while (flash->status & STATUS_BUSY)
        ;

    flash->control &= ~CONTROL_OPT_ERASE;

    for (size_t i = 0; i < size / 2; i++) {
        flash->control |= CONTROL_OPT_PROG;

        dest[i] = src[i];

        while (flash->status & STATUS_BUSY)
            ;
    }

    flash->control = CONTROL_LOCK;
}
