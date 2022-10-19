from . import model
import struct

@model.Program.ext_db.register("uf2")
@model.Program.format_db.register("uf2")
class Uf2Program(model.Program):
    NOT_MAIN_FLASH = 0x00000001
    FILE_CONTAINER = 0x00001000
    FAMILY_ID      = 0x00002000
    MD5_PRESENT    = 0x00004000
    EXT_PRESENT    = 0x00008000

    def __init__(self, filename, offset = 0):
        super().__init__(filename)

        family_id = None
        file_size = None
        block_count = None

        data_blocks = {}
        
        with open(filename, 'rb') as fd:
            while True:
                block = fd.read(512)
                if len(block) < 512:
                    break

                magic, magic2, flags, address, data_len, seq_no, total_no, fz_fam \
                    = struct.unpack("<LLLLLLLL", block[:32])
                magic_end, = struct.unpack("<L", block[-4:])

                if magic != 0x0A324655 \
                   or magic2 != 0x9E5D5157 \
                   or magic_end != 0x0AB16F30:
                    continue

                if flags & self.FAMILY_ID:
                    family_id = fz_fam

                if flags & self.FILE_CONTAINER:
                    pass
                elif not (flags & self.NOT_MAIN_FLASH):
                    data_blocks[seq_no] = address, block[32:32+data_len]

                if flags & self.EXT_PRESENT:
                    tag_data = block[32+data_len:-4]
                    while tag_data and tag_data[0]:
                        size = tag_data[0]
                        type = int.from_bytes(tag_data[1:4], "little")
                        tag = tag_data[4:size]
                        size += (-size) % 4
                        tag_data = tag_data[:size]

                        if type == 0x9fc7bc:
                            self.info["version"] = tag
                        elif type == 0x650d9d:
                            self.info["device_description"] = tag
                        elif type == 0x0be9f7:
                            self.info["page_size"] = int.from_bytes(tag[:4], "little")
                        elif type == 0xb46db0:
                            self.info["sha2"] = tag
                        elif type == 0xc8a729:
                            self.info["device_type"] = tag
                        else:
                            self.info[f"tag_{type:06x}"] = tag

            if set(data_blocks.keys()) != set(range(len(data_blocks))):
                raise ValueError("Bad data in blocks")

            p = model.Program()
            for address, data in data_blocks.values():
                p.append(model.Segment(address, data))
            for s in p.simplified():
                self.append(model.Segment(s.address + offset, s.data))

            if family_id is not None:
                self.info["family_id"] = family_id
                for family in FAMILY_IDS:
                    if int(family["id"], 16) == family_id:
                        self.info["family_name"] = family["short_name"]
                        self.info["family_description"] = family["description"]
                        break

            if "family_name" in self.info and self.info["family_name"].startswith("RP2"):
                self.binary_info_extract()
    def binary_info_extract(self):
        from .rp2.binary_info import Marker, IdAndInt, IdAndString
        try:
            marker = Marker(self)
        except ValueError:
            return

        for datum in marker:
            if isinstance(datum, IdAndString):
                self.info[str(datum.tag, 'utf-8') + "_" + datum.key] = datum.value
            elif isinstance(datum, IdAndInt):
                self.info[str(datum.tag, 'utf-8') + "_" + datum.key] = datum.value

                    
# Retrieved from https://github.com/microsoft/uf2/blob/master/utils/uf2families.json
FAMILY_IDS = [
    {
        "id": "0x16573617",
        "short_name": "ATMEGA32",
        "description": "Microchip (Atmel) ATmega32"
    },
    {
        "id": "0x1851780a",
        "short_name": "SAML21",
        "description": "Microchip (Atmel) SAML21"
    },
    {
        "id": "0x1b57745f",
        "short_name": "NRF52",
        "description": "Nordic NRF52"
    },
    {
        "id": "0x1c5f21b0",
        "short_name": "ESP32",
        "description": "ESP32"
    },
    {
        "id": "0x1e1f432d",
        "short_name": "STM32L1",
        "description": "ST STM32L1xx"
    },
    {
        "id": "0x202e3a91",
        "short_name": "STM32L0",
        "description": "ST STM32L0xx"
    },
    {
        "id": "0x21460ff0",
        "short_name": "STM32WL",
        "description": "ST STM32WLxx"
    },
    {
        "id": "0x2abc77ec",
        "short_name": "LPC55",
        "description": "NXP LPC55xx"
    },
    {
        "id": "0x300f5633",
        "short_name": "STM32G0",
        "description": "ST STM32G0xx"
    },
    {
        "id": "0x31d228c6",
        "short_name": "GD32F350",
        "description": "GD32F350"
    },
    {
        "id": "0x04240bdf",
        "short_name": "STM32L5",
        "description": "ST STM32L5xx"
    },
    {
        "id": "0x4c71240a",
        "short_name": "STM32G4",
        "description": "ST STM32G4xx"
    },
    {
        "id": "0x4fb2d5bd",
        "short_name": "MIMXRT10XX",
        "description": "NXP i.MX RT10XX"
    },
    {
        "id": "0x53b80f00",
        "short_name": "STM32F7",
        "description": "ST STM32F7xx"
    },
    {
        "id": "0x55114460",
        "short_name": "SAMD51",
        "description": "Microchip (Atmel) SAMD51"
    },
    {
        "id": "0x57755a57",
        "short_name": "STM32F4",
        "description": "ST STM32F4xx"
    },
    {
        "id": "0x5a18069b",
        "short_name": "FX2",
        "description": "Cypress FX2"
    },
    {
        "id": "0x5d1a0a2e",
        "short_name": "STM32F2",
        "description": "ST STM32F2xx"
    },
    {
        "id": "0x5ee21072",
        "short_name": "STM32F1",
        "description": "ST STM32F103"
    },
    {
        "id": "0x621e937a",
        "short_name": "NRF52833",
        "description": "Nordic NRF52833"
    },
    {
        "id": "0x647824b6",
        "short_name": "STM32F0",
        "description": "ST STM32F0xx"
    },
    {
        "id": "0x68ed2b88",
        "short_name": "SAMD21",
        "description": "Microchip (Atmel) SAMD21"
    },
    {
        "id": "0x6b846188",
        "short_name": "STM32F3",
        "description": "ST STM32F3xx"
    },
    {
        "id": "0x6d0922fa",
        "short_name": "STM32F407",
        "description": "ST STM32F407"
    },
    {
        "id": "0x6db66082",
        "short_name": "STM32H7",
        "description": "ST STM32H7xx"
    },
    {
        "id": "0x70d16653",
        "short_name": "STM32WB",
        "description": "ST STM32WBxx"
    },
    {
        "id": "0x7eab61ed",
        "short_name": "ESP8266",
        "description": "ESP8266"
    },
    {
        "id": "0x7f83e793",
        "short_name": "KL32L2",
        "description": "NXP KL32L2x"
    },
    {
        "id": "0x8fb060fe",
        "short_name": "STM32F407VG",
        "description": "ST STM32F407VG"
    },
    {
        "id": "0xada52840",
        "short_name": "NRF52840",
        "description": "Nordic NRF52840"
    },
    {
        "id": "0xbfdd4eee",
        "short_name": "ESP32S2",
        "description": "ESP32-S2"
    },
    {
        "id": "0xc47e5767",
        "short_name": "ESP32S3",
        "description": "ESP32-S3"
    },
    {
        "id": "0xd42ba06c",
        "short_name": "ESP32C3",
        "description": "ESP32-C3"
    },
    {
        "id": "0x2b88d29c",
        "short_name": "ESP32C2",
        "description": "ESP32-C2"
    },
    {
        "id": "0x332726f6",
        "short_name": "ESP32H2",
        "description": "ESP32-H2"
    },
    {
        "id": "0xe48bff56",
        "short_name": "RP2040",
        "description": "Raspberry Pi RP2040"
    },
    {
        "id": "0x00ff6919",
        "short_name": "STM32L4",
        "description": "ST STM32L4xx"
    },
    {
        "id": "0x9af03e33",
        "short_name": "GD32VF103",
        "description": "GigaDevice GD32VF103"
    },
    {
        "id": "0x4f6ace52",
        "short_name": "CSK4",
        "description": "LISTENAI CSK300x/400x"
    },
    {
        "id": "0x6e7348a8",
        "short_name": "CSK6",
        "description": "LISTENAI CSK60xx"
    }
]
