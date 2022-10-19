#include "common.h"

#define XIP_CTRL_BASE 0x14000000
#define XIP_SSI_BASE 0x18000000
#define IO_QSPI_BASE 0x40018000

typedef struct {
    volatile uint32_t ctrl;
    volatile uint32_t flush;
    volatile uint32_t stat;
    volatile uint32_t ctr_hit;
    volatile uint32_t ctr_acc;
    volatile uint32_t stream_addr;
    volatile uint32_t stream_ctr;
    volatile uint32_t stream_fifo;
} xip_ctrl_hw_t;

typedef struct {
    volatile uint32_t ctrlr0;
    volatile uint32_t ctrlr1;
    volatile uint32_t ssienr;
    volatile uint32_t mwcr;
    volatile uint32_t ser;
    volatile uint32_t baudr;
    volatile uint32_t txftlr;
    volatile uint32_t rxftlr;
    volatile uint32_t txflr;
    volatile uint32_t rxflr;
    volatile uint32_t sr;
    volatile uint32_t imr;
    volatile uint32_t isr;
    volatile uint32_t risr;
    volatile uint32_t txoicr;
    volatile uint32_t rxoicr;
    volatile uint32_t rxuicr;
    volatile uint32_t msticr;
    volatile uint32_t icr;
    volatile uint32_t dmacr;
    volatile uint32_t dmatdlr;
    volatile uint32_t dmardlr;
    volatile uint32_t idr;
    volatile uint32_t ssi_version_id;
    volatile uint32_t dr0;
    uint32_t _pad0[35];
    volatile uint32_t rx_sample_dly;
    volatile uint32_t spi_ctrlr0;
    volatile uint32_t txd_drive_edge;
} ssi_hw_t;

enum {
    QSPI_GPIO_SCK,
    QSPI_GPIO_CS,
    QSPI_GPIO_SD0,
    QSPI_GPIO_SD1,
    QSPI_GPIO_SD2,
    QSPI_GPIO_SD3,
    QSPI_GPIO_COUNT,
};

typedef struct {
    volatile uint32_t status;
    volatile uint32_t ctrl;
} ioqspi_status_ctrl_hw_t;

typedef struct {
    volatile uint32_t inte;
    volatile uint32_t intf;
    volatile uint32_t ints;
} io_qspi_ctrl_hw_t;

typedef struct {
    ioqspi_status_ctrl_hw_t io[QSPI_GPIO_COUNT];
    volatile uint32_t intr;
    io_qspi_ctrl_hw_t proc0_qspi_ctrl;
    io_qspi_ctrl_hw_t proc1_qspi_ctrl;
    io_qspi_ctrl_hw_t dormant_wake_qspi_ctrl;
} ioqspi_hw_t;

#define xip ((xip_ctrl_hw_t *)XIP_CTRL_BASE)
#define ssi ((ssi_hw_t *) XIP_SSI_BASE)
#define ioqspi ((ioqspi_hw_t *)IO_QSPI_BASE)

typedef enum {
    OUTOVER_NORMAL = 0,
    OUTOVER_INVERT,
    OUTOVER_LOW,
    OUTOVER_HIGH
} outover_t;

static inline
void flash_cs_force(outover_t over)
{
    volatile uint32_t *reg = &ioqspi->io[QSPI_GPIO_CS].ctrl;
    *reg = over << 8;
    (void) *reg;
}

static inline
void flash_put_get(const uint8_t *tx, uint8_t *rx, size_t count)
{
    const uint32_t max_in_flight = 16 - 2;
    size_t tx_count = count;
    size_t rx_count = count;

    while (tx_count || rx_count) {
        uint32_t tx_level = ssi->txflr;
        uint32_t rx_level = ssi->rxflr;

        if (tx_count && tx_level + rx_level < max_in_flight) {
            ssi->dr0 = (uint32_t)(tx ? (*tx++) : 0);
            --tx_count;
        }

        if (rx_level) {
            uint8_t rxbyte = ssi->dr0;

            if (rx)
                *rx++ = rxbyte;
            --rx_count;
        }
    }
}

struct command
{
    uint32_t tx_ptr;
    uint32_t rx_ptr;
    uint32_t size;
};

void flash_spi_transact(void)
{
    const struct command *cmd = (const struct command *)0xdeadbee0;
    
    while (cmd->size) {
        if (cmd->size & 0x80000000) {
            flash_cs_force((cmd->size & 1) ? OUTOVER_HIGH : OUTOVER_LOW);
        } else {
            flash_put_get((const uint8_t *)cmd->tx_ptr, (uint8_t *)cmd->rx_ptr, cmd->size);
        }
        cmd++;
    }
}
