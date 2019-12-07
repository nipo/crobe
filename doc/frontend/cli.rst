======================
Command line interface
======================

General command line parsing
============================

Crobe's command line interface script follows general parsing rules
from Click_.  There is a hierarchical tree of command and subcommands.
Some options may be available at various levels of the command line
parsing.

General options
===============

Logging context
---------------

Crobe's logger context is configured before selecting actual
command. Therefore verbosity modifiers (`-v` and `-q`), and logger
filters (`--silent NAME`) must be specified before the first command
level.

Example::

  $ crobe -vv info enumerate
  0:00:00.000312  root            Starting at 2019-11-17 14:48:52.897240
   Roots
   Targets

Informational commands
======================

Listing adapters
----------------

Crobe can enumerate all available adapter_\s.  For each adapter type,
it can tell what features are supported.

Example::

  $ crobe info adapters
  * Enumerator Adapters
    * Enumerator Digilent HS2
    * Enumerator Digilent Board
    * Enumerator Proby
      * Adapter proby-0 supported interfaces: swd, swd-pt, jtag, jtag-raw, jtag-int, spi, cc, i2c
    * Enumerator Busblaster
    * Enumerator Lattice HW-USBN-2B
    * Enumerator JLink
      * Adapter PCA10040-2 supported interfaces: swd, jtag, spi
    * Enumerator XVCD
    * Enumerator IceStick
    * Enumerator SF2-Maker
    * Enumerator fx
    * Enumerator fx2
    * Enumerator xpc
    * Enumerator KitProg
    * Enumerator CH341A
    * Enumerator LTC DC590B
    * Enumerator fx3

Here, one `Proby` and one `JLink` probe are connected.

Enumerating an interface
------------------------

For a given adapter, you may ask `crobe` to autodiscover as much as
it can on a given interface::

  $ crobe info enumerate -r proby-0/jtag-int
   Roots
     proby-0-ATE
       proby-0-Chain
         Spartan6-LX9 (TAP#0, irlen:6)
   Targets
     FPGA: Spartan6-LX9
       Memory RAM 'config' from 0x00000000 to 0x0007d000 (500kiB)

Here, starting from "jtag-int" adapter in "proby-0", it discovered one
Spartan-6 on JTAG chain. Then it gets translated as one target.

I2C bus scan
------------

Even if not specified, Crobe can scan an I2C bus for presence of
slaves on all addresses::

  $ crobe info i2c-scan -r proby/i2c

SVF player
==========

Serial Vector Format is a de-facto standard for appying test vectors
to a JTAG chain. Crobe is able to play a SVF file, either on a full
JTAG chain, or on a specific TAP. This way, a SVF file that was
created for a specific chip without knowing its target chain can be
played back anyway::

  $ crobe svf play -r pro/jtag/0/0 program.svf

Chip manipulation commands
==========================

Subcommand help::

  $ crobe chip --help
  Usage: crobe chip [OPTIONS] COMMAND [ARGS]...
  
    Target chip manipulation
  
  Options:
    -r, --root ROOT
    -t, --target INDEX  Target index
    --help              Show this message and exit.
  
  Commands:
    check     Check target
    program   Program target
    readback  Readback target

Programming a chip
------------------

Programming a chip with a given firmware is one of the most common
tasks. Crobe can do it without effort. All you need to give it is path
to discovery root and payload to program.

Example::

  $ crobe chip -r pca/swd program --erase --run some.hex
  Target: nRF52832
  flashing...: 100%|████████████████████████████████████████████████████████████| 128/128 [00:20<00:00, 26481.85it/s]

Crobe can optionally erase the target before, and release CPU to run
after programming.

You can specify multiple files of various formats.  In case multiple
files defines the same location multiple times, file specified last
takes precedence. There are other options that can be injected when
parsing programming files. See loadables_.

Other chip operations
---------------------

The other way, Crobe can read all memory regions it knows in a chip
and store them to a file.  It can also check a target is matching a
given (set of) binaries.

Crobe can store plain binary files and intel-hex files.

See command line help for more.

Xilinx-specific commands
========================

XVC Server
----------

Crobe can expose a JTAG interface to Xilinx-specific *Virtual Cable*
interface::

  $ crobe xilinx vcd-server -r pro/jtag --port 4141

Security key programming
------------------------

There is support for Series-7 security keys programming, either for
*Battery-backed RAM* (BBRAM) or fuses. These commands require that
root is a TAP::

  $ crobe xilinx bbram-key-set -r pro/jtag/0/0 [64 hex digits]
  $ crobe xilinx efuse-key-set -r pro/jtag/0/0 [64 hex digits]

Dumping fuses
-------------

  $ crobe xilinx efuse-dump -r pro/jtag/0/0

Probing intenral temperature through XADC
-----------------------------------------

  $ crobe xilinx xadc-temp -r pro/jtag/0/0



.. _click: https://click.palletsprojects.com/en/7.x/
.. _adapter: concepts.html#adapters
.. _loadables: loadables.html
