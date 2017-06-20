from ....part_id import PartId
from .soc import SoC

@SoC.db.register(PartId(2, 0x44, 1))
def nrf51x22(dp):
    return SoC("nRF51x22", dp)

@SoC.db.register(PartId(2, 0x44, 6))
def nrf52832(dp):
    return SoC("nRF52832", dp)

@SoC.db.register(PartId(2, 0x44, 8))
def nrf52840(dp):
    return SoC("nRF52840", dp)
