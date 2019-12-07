==============
Loadable files
==============

File formats
============

There are multiple file types used, among which:

* plain binary files,
* Intel HEX files,
* ELFs,
* Xilinx, Lattice bitstreams (.bit),
* Cypress FX2/FX3 images.

Crobe can understand and parse these files.

On the command line, some `options <file name options_>`_ may be
passed after a file name.

Plain binary files
------------------

Plain binaries are trated as-is.

Intel HEX files
---------------

Intel-HEX are ascii-encoded, have (limited) integrity assertion, and
provide support for multiple disjoint segments. They also support
setting an entry point for a program.

ELFs
----

ELF are typical output format for an embedded toolchain. Only
loadable sections are used.

Bitstreams
----------

Bitstreams are fingerprinted, crobe tries to extract the target part
type, it is then used for checking compatibility before programming.

Cypress FX2/FX3 images
----------------------

`.img` files are just another type of segmented binary file. This is
the expected format for FX startup eeprom/flash contents. They can be
parsed when loading firmware to connected chip is needed.

File name options
=================

After a file name, you may append options separated by colons (`:`).

Forcing file type
-----------------

You may specify a specific parser by using its name as an
option. Supported parser are "JED", "BIN", "BIT", "IMG", "IHEX",
"ELF".

For instance, a given bitstream can be parsed::

  $ python3 -m crobe.loadable dump crobe/adapter/proby/fw/jtag_swd_raw.bit.gz
  Program:
   + build_date: 2017-08-01 15:08:55
   + device: 6slx9tqg144
   + project: jtag_swd_raw_par.ncd
   + userid: 2961705645
   - <0x00000000:0x00022344 (140100 bytes)>

And can also be trated as a raw binary::

  $ python3 -m crobe.loadable dump crobe/adapter/proby/fw/jtag_swd_raw.bit.gz:BIN
  Program:
   - <0x00000000:0x00001d88 (7560 bytes)>

Offsetting a file
-----------------

You may specify an offset of add to all base addresses of file
sections (or only section in case of plain binaries).  This is mostly
useful for loading a blob to a given offset of a target chip.
Offsetting is done at load time, in a way multiple loadable files can
be merged as one::

  $ python3 -m crobe.loadable dump crobe/adapter/proby/fw/jtag_swd_raw.bit.gz:BIN:+0x1000
  Program:
   - <0x00001000:0x00002d88 (7560 bytes)>

This way, you may combine this bitstream with an ELF file and load it
to target flash::

  $ python3 -m crobe.loadable dump my_program.elf crobe/adapter/proby/fw/jtag_swd_raw.bit.gz:BIN:+0x10000
  Program:
   - <0x00000000:0x0000d9bc (55740 bytes)>
   - <0x00010000:0x00011d88 (7560 bytes)>
