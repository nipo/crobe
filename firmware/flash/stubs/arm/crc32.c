#include "common.h"

static inline
uint32_t lookup_04c11db7_lsb_slow(uint8_t index)
{
    const uint32_t poly = 0xedb88320;
    uint32_t ret = index;

    for (uint8_t bit = 0; bit < 8; ++bit) {
        if (ret & 1)
            ret = (ret >> 1) ^ poly;
        else
            ret = (ret >> 1);
    }

    return ret;
}

typedef uint32_t crc32_lookup_f(uint8_t index);

static inline
uint32_t crc32_lsb(crc32_lookup_f *f, uint32_t crc, const uint8_t *data, size_t len)
{
  for (size_t i = 0; i < len; ++i)
      crc = (crc >> 8) ^ f((crc ^ data[i]) & 0xff);

  return crc;
}

#define CRC32_ZLIB_INIT 0
static inline
uint32_t crc32_zlib(uint32_t crc, const uint8_t *data, size_t len)
{
    return ~crc32_lsb(lookup_04c11db7_lsb_slow, ~crc, data, len);
}

uint32_t memory_crc32(const uint8_t *data, size_t len)
{
    return crc32_zlib(CRC32_ZLIB_INIT, data, len);
}

struct crc32_zone
{
    union {
        const uint8_t *address;
        uint32_t crc;
    };
    uint32_t size;
};

void memory_crc32_many(struct crc32_zone *zone, size_t zone_count)
{
    for (size_t i = 0; i < zone_count; ++i)
        zone[i].crc = crc32_zlib(CRC32_ZLIB_INIT, zone[i].address, zone[i].size);
}
