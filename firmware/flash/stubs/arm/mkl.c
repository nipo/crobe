#include "common.h"

struct ftfa
{
    uint8_t fstat;
    uint8_t fcnfg;
    uint8_t fsec;
    uint8_t fopt;
    uint32_t fccob_cmd_addr;
    uint32_t fccob_data;
};

enum ftfa_command
{
    FTFA_PROGRAM_LONGWORD = 0x06,
    FTFA_ERASE_SECTOR = 0x09,
};

#define FTFA ((volatile struct ftfa *)0x40020000)
#define FTFA_FSTAT_CCIF_MASK 0x80
#define MCM_PLACR REG32(0xf000300c)
#define SIM_SCGC6 REG32(0x4004803c)
#define SIM_SCGC6_FTF_MASK 0x01

static inline
void flash_init(void)
{
	__asm__ volatile ("cpsid i" ::: "memory");
	SIM_SCGC6	|= SIM_SCGC6_FTF_MASK;
	MCM_PLACR = 0x00010000;
}

static inline
void flash_command_execute(uint8_t command, uint32_t address)
{
	FTFA->fcnfg = 0x00;

    FTFA->fccob_cmd_addr = ((uint32_t)command << 24) | (address & 0xffffff);
	
	FTFA->fstat = FTFA_FSTAT_CCIF_MASK;
	while (!(FTFA->fstat & FTFA_FSTAT_CCIF_MASK))
        ;
}

void flash_erase(uintptr_t addr, size_t size, size_t page_size)
{
    flash_init();

    uintptr_t end = addr + size;

    addr = addr & (page_size - 1);

    while (addr < end) {
        flash_command_execute(FTFA_ERASE_SECTOR, addr);
        addr += page_size;
    }
}

void flash_write(uintptr_t dest, const void *src_, size_t bytes)
{
    const uint32_t *src = src_;
    size_t words = bytes / 4;
    size_t i;
    
    flash_init();

    for (i = 0; i < words; ++i) {
        FTFA->fccob_data = src[i];
        flash_command_execute(FTFA_PROGRAM_LONGWORD, dest + i * 4);
    }
}
