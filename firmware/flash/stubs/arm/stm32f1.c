#include "common.h"

#define FLASH ((struct flash_s *)0x40022000)

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
#define STATUS_BUSY        0x01
#define STATUS_PAGE_ERR    0x04
#define STATUS_PROT_ERR    0x10
#define STATUS_EOP         0x20
#define CONTROL_PROG       0x01
#define CONTROL_ERASE      0x02
#define CONTROL_MASS_ERASE 0x04
#define CONTROL_OPT_PROG   0x10
#define CONTROL_OPT_ERASE  0x20
#define CONTROL_START      0x40
#define CONTROL_LOCK       0x80

static inline
void unlock(struct flash_s *flash)
{
    if (!(flash->control & CONTROL_LOCK))
        return;
    
    flash->key = KEY_1;
    flash->key = KEY_2;
}

void flash_erase(uintptr_t addr, size_t bytes, size_t page_size)
{
    uintptr_t end = addr + bytes;
    struct flash_s *flash = FLASH;

    addr &= ~(page_size - 1);

    unlock(flash);

    while (flash->status & STATUS_BUSY)
        ;

    while (addr < end) {
        flash->control = CONTROL_ERASE;

        flash->address = addr;

        flash->control = CONTROL_START | CONTROL_ERASE;

        while (flash->status & STATUS_BUSY)
            ;

        addr += page_size;
    }

    flash->control = 0;
}

void flash_write(uintptr_t dest_, const void *src_, size_t size)
{
    struct flash_s *flash = FLASH;
    volatile uint16_t *dest = (uint16_t*)(dest_);
    const uint16_t *src = (uint16_t*)src_;

    unlock(flash);

    for (size_t i = 0; i < size / 2; i++) {
        flash->control = CONTROL_PROG;

        dest[i] = src[i];

        while (flash->status & STATUS_BUSY)
            ;
    }

    flash->control = 0;
}
