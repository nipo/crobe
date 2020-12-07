#include "common.h"

#define inline inline __attribute__((always_inline))

static inline
uint32_t dcc_control_read(void)
{
	uint32_t ret;

	__asm__ volatile(
        "mrc p14, 0, %[ret], c0, c0\n\t"
        : [ret] "=r"(ret)
        );

	return ret;
}

static inline
uint32_t dcc_data_read(void)
{
	uint32_t ret;

	__asm__ volatile(
        "mrc p14, 0, %[ret], c1, c0\n\t"
        : [ret] "=r"(ret)
        );

	return ret;
}

static inline
void dcc_data_write(uint32_t data)
{
	__asm__ volatile(
        "mcr p14, 0, %[data], c1, c0\n\t"
        :: [data] "r"(data)
        );
}

static inline
uint32_t dcc_data_pop(void)
{
    while (!(dcc_control_read() & 1))
        ;

    return dcc_data_read();
}

static inline
void dcc_data_push(uint32_t data)
{
    while (dcc_control_read() & 2)
        ;

    dcc_data_write(data);
}

static inline
__attribute__((noreturn))
void breakpoint(void)
{
    __asm__ volatile("bkpt 0");
    __builtin_unreachable();
}

#define CMD_DATA_ADDR 0
#define CMD_DATA_DATA 1
#define CMD_DATA_CRC  2
#define CMD_DATA_DCC  3
#define CMD_DATA_VOID 4
#define CMD_DATA_PC   5

#define CMD_DATA_SRC_GET(x) (((x) >> 29) & 7)
#define CMD_CRC_UPDATE        0x02000000
#define CMD_PTR_INC           0x01000000
#define CMD_DATA_DST_GET(x) (((x) >> 26) & 7)
#define CMD_CTR_GET(x) ((x) & 0x00ffffff)

static inline
uint32_t crc32e(uint32_t crc, const void *data, size_t size)
{
    const uint8_t *message = data;

	do {
		crc = crc ^ *message++;
        for (int i = 0; i < 8; ++i) {
            crc = (crc >> 1) | (crc << 31);
            if (crc & 0x80000000)
                crc ^= 0xedb88320 ^ 0x80000000;
        }
	} while (--size);

	return crc;
}

static inline
__attribute__((noreturn))
void jump_to(uint32_t entry)
{
    typedef __attribute__((noreturn)) void (*fptr)(void);
    fptr e = (fptr)entry;

    e();
    __builtin_unreachable();
}

__attribute__((noreturn))
void dcc_cnc(void)
{
    uint32_t *addr = 0;
    uint32_t crc = 0;

    dcc_data_read();
    dcc_data_read();
    dcc_data_read();
    
    for (;;) {
        const uint32_t cmd = dcc_data_pop();

        if (cmd == 0)
            break;
        
        for (int count = CMD_CTR_GET(cmd); count >= 0; --count) {
            uint32_t data;

            switch (CMD_DATA_SRC_GET(cmd)) {
            case CMD_DATA_CRC: data = crc; break;
            case CMD_DATA_DCC: data = dcc_data_pop(); break;
            case CMD_DATA_DATA: data = *addr; break;
            case CMD_DATA_ADDR: data = (uint32_t)addr; break;
            default:
            case CMD_DATA_VOID: data = 0; break;
            }

            if (cmd & CMD_CRC_UPDATE)
                crc = crc32e(crc, &data, 4);

            switch (CMD_DATA_DST_GET(cmd)) {
            case CMD_DATA_CRC: crc = data; break;
            case CMD_DATA_DCC: dcc_data_push(data); break;
            case CMD_DATA_DATA: *addr = data; break;
            case CMD_DATA_ADDR: addr = (uint32_t*)data; break;
            case CMD_DATA_PC: jump_to(data); break;
            default:
            case CMD_DATA_VOID: break;
            }

            if (cmd & CMD_PTR_INC)
                addr++;
        }
    }

    breakpoint();
}
