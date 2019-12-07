==================
Supported hardware
==================

Supported components_ are numerous. Let's try to enumerate some of
them.

Basic programmable chips
========================

I2C EEPROM
----------

I2C EEPROMs are handled through generic code that handles varying
number of memory content address bytes, varying write-buffer length,
and even support eeproms that use I2C slave address as extension of
byte address, like `M24M02
<https://www.st.com/resource/en/datasheet/m24m02-dr.pdf>`_

I2C EEPROMS have no autodetection features. In order to use them, you
must explicitly instantiate them from an I2C bus handle::

  $ crobe memory -r "pro/i2c/eeprom(saddr=0x50,addr_bytes=2)" peek 0 0x10
  Bus: I2cEeprom
  0x0 42563100000000006299f9ff9fff9fff

Here, we explicitly look for an EEPROM at address 0x50, using 2 bytes
of memory content address.

Options:

* `saddr`: I2C Slave address,
* `addr_bytes`: Memory content address width, in bytes,
* `saddr_bits`: Count of bit in slave address that are an extension of
  memory content address,
* `size`: Byte count of memory data area (default to addressable count
  from content address width),
* `page_size`: Write buffer size, i.e. the count of bytes that are
  written in one transaction.

SPI Flash
---------

Historically, SPI flashes are underspecified. Old chips have nearly no
common command bytes. Newest chip are self-descriptive through SFDP, a
JEDEC standard. Crobe handles SFDP chips out of the box, and some
non-SFDP chips are also defined, among which:

* Adesto AT25SF,
* Cypress S25FL,
* ISSI IS24LQxx,
* Macronix MX25R,
* Winbond W25x.

There is no auto-discovery of presence of a flash chip for a given SPI
slave, even for SFDP chips, you'll have to explicitly look for a flash
chip on a given SPI bus::

  $ crobe memory -r "pro/spi/0/flash" peek 0 0x10
  Bus: W25Xxx
  0x0 ffffffffffffffffffffffffffffffff

FPGAs
=====

Xilinx
------

Programming port access for Series 6 (Spartan 6), Series 7 (Spartan 7,
Virtex 7, Kintex 7, Zynq 7000 PL) is supported. There is also support
for tweaking of fuses, or accessing XADC directly from JTAG.

Lattice
-------

Mach-XO2 is well supported. There is implementation for programming
SRAM, Flash and UFM from all communication channels (JTAG, SPI,
I2C). There is also code for parsing compressed bitstreams.

SoCs
====

ARM-based SoCs
--------------

ARM defines a common debugger communication model for all SoCs based
on its CPU cores.  They all share the same communication architecture
from wire protocol (SWD or JTAG) down to the memory bus.  All this
involves numerous components that are all layered.  Crobe implements
them all.

When implemented correctly, SoC self-enumeration memories (known as
"ROM Tables") provide an unique identifier for a given SoC or SoC
family.  When available, Crobe is able to identify the SoC in
presence.

Crobe Support the following SoCs:

* Nordic nRF51, nRF52 lineup,
* STM32 (most of the product line),
* Ti CC26xx,
* Silabs' EFM32 lineup,
* NXP LPC11u,
* NXP Kinetis MKL0x,
* Cypress PSoC 3, 4, 5 and their variants (like USB Type-C controllers),
* Zynq 7000's PS.

There is generic bridge support for accessing any SPI slave connected
to SPI controller of Spartan-6. This allows "Indirect" programming of
a SPI Flash attached to a FPGA.

ATMega
------

There is limited support for ATMega enumeration and programming.

Mips
----

Mips32 is basically supported for enumeration. Programming is not
performed yet.

Various sensors
===============

Melexis MLX90614
----------------

Melexis provides various sensors. There is support for MLX90614, a
contactless temperature sensor. This allows to poll for temperature
through any I2C host.

Boundary scan
=============

Any JTAG Tap exposing boundary scan may be supported through matching
BSDL file. BSDL definition will allow to use pin names for test and
control purposes.

.. _`components`: concepts.html#components
