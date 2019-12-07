========
Concepts
========

Adapters and Enumerators
========================

.. _adapters:

Adapters are the software counterpart for a hardware probe. Various
Enumerators are able to scan host platform for presence and
capabilities of currently connecter adapters.

Interfaces
==========

Adapters may expose multiple interfaces. Sometimes they are
multiplexed and mutually exclusive, sometimes they are concurrent.
Whether they can actually be used concurrently depends on the adapter
and its driver implementation.

Interfaces are designated by names.  Names are supposed to be matching
underlying protocol, but sometimes adapters expose the same wire
protocol with multiple variants, then interface names may be
adapter-specific. Nonetheless, names try to stay explicit::

  $ crobe info adapters 
  * Enumerator Adapters
    [...]
    * Enumerator Proby
      * Adapter proby-0 supported interfaces: swd, swd-pt, jtag, jtag-raw, jtag-int, spi, cc, i2c
    [...]
    * Enumerator JLink
      * Adapter PCA10040-2 supported interfaces: swd, jtag, spi

Here, there is a JLink adapter named "PCA10040-2", it exposes SWD,
JTAG and SPI protocols with matching interface names.  On the other
hand, Proby instance named "proby-0" exposes two SWD variants named
"swd" and "swd-pt", three JTAG variants, one SPI, one CC and one I2C.

Paths
=====

Internally, components are stored in a tree that tries to match the
hardware topology.  In order to designate a node, somes rules are used
to walk through the tree.

Paths are a list of labels separated by slashes "/". Each label may be
followed by a list of options separated by commas ",", enclosed in
parenthesis::

  first/second(option=value,boolean_option)/third

At each level, dereferencing is done in the following order:

* First, node is looked up in existing node children.

  * If the label is a number, it is used as child index.

  * If the label matches any substring of exactly one child, this
    child is used.

* Then system tries to create a node from scratch.  Depending on the
  type of parent of node to be created, various registries store
  databases of components that can be created as child.

If node was successfully retrieved or created, options are applied to
it, and then lookup continues one level deeper in the tree.

Roots
=====

Discovery of components (either hardware, bridge, software, or
conceptual) can be either automatic (when there is some sort of
enumeration mechanism) or manual.  Root is the path from an adapter to
a component where autodiscovery should start. Sometimes, autodiscovery
is impossible, and root is also the leaf of the autodiscovery tree.

In this first example, we'll autodiscover a supported SWD device.
Discovery will start from interface "swd" of adapter matching "pca".
SWD has standard enumeration features down to the memory-mapped debug
components and attached CPUs, can even tell SoC type::

  $ crobe info enumerate -r pca/swd
   Roots
     PCA10040-2/SWD
       SW-DP v.1r2
         AHB-AP
           RomTable for 0x50006289 (Nordic VLSI ASA, 0x0006, r5)
             System Control Space for ARM Cortex-M4 r0p1 with FPU
             Data Watch Trace Unit
             Flash Patch and Breakpoint unit
             Instruction Trace Macrocell
             Trace Port Interface Unit
             Embedded Trace Macrocell
         Nordic Ctrl-AP
   Targets
     nRF52832
       ARM Cortex-M4 r0p1 with FPU
       Memory FLASH 'code' from 0x00000000 to 0x00080000 (512kiB), 4kiB pages
       Memory FLASH 'uicr' from 0x10001000 to 0x10002000 (4kiB), 4kiB pages
       Memory RAM 'ram' from 0x20000000 to 0x20010000 (64kiB)

Once roots are enumerated, a second pass extracts a list of targets
for discovered compoents. See below for explaination of targets.

In this second example, there is no automatic discovery of attached
components.  Path given on the command line gives explicit location of
an I2C memory. Then it is used to read first 16 bytes of memory::

  $ crobe memory -r "pro/i2c/eeprom(saddr=0x50,addr_bytes=2)" peek 0 0x10
  Bus: I2cEeprom
  0x0 42563100000000006299f9ff9fff9fff

Components
==========

Components are functionaly disjoint parts. Inside a SoC, components
may be referred as IPs. Crobe models a clean separation between
components with specific communication methods between them. For
instance, all of these are components:

* A JTAG TAP,
* A SWD Debug Port (DP),
* A SWD Application Port (AP),
* Coresight System Control Space IP,
* An I2C EEPROM,
* A SPI Flash,
* etc.

Targets
=======

Targets are a list of targets that can use different components in the
discovered tree.  This is mainly convenience for designating debugger
targets.

::

  $ crobe info enumerate -r pca/swd
   Roots
     PCA10040-2/SWD
       SW-DP v.1r2
         AHB-AP
           RomTable for 0x50006289 (Nordic VLSI ASA, 0x0006, r5)
             System Control Space for ARM Cortex-M4 r0p1 with FPU
             Data Watch Trace Unit
             Flash Patch and Breakpoint unit
             Instruction Trace Macrocell
             Trace Port Interface Unit
             Embedded Trace Macrocell
         Nordic Ctrl-AP
   Targets
     nRF52832
       ARM Cortex-M4 r0p1 with FPU
       Memory FLASH 'code' from 0x00000000 to 0x00080000 (512kiB), 4kiB pages
       Memory FLASH 'uicr' from 0x10001000 to 0x10002000 (4kiB), 4kiB pages
       Memory RAM 'ram' from 0x20000000 to 0x20010000 (64kiB)

In this example, nRF32832 target can be used for debugging, for
programming, for GPIO toggling, etc. All these operations of target
can be performed because crobe is able to take control of memory, CPU,
and other components. nRF52832 object in crobe actually refers to the
SCB, DWT, ITM, and the Ctrl-AP in order to implement all these.

Creating targets from discovered components is automatic through
various registries.

