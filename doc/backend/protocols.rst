=====================
 Supported protocols
=====================

Interfaces were presented in the concepts_ chapter. Here we'll pass
through some supported ones.

JTAG
====

JTAG stands for *Joint Test Action Group*, it is the name of the
working group which designed the *IEEE Standard Test Access Port and
Boundary-Scan Architecture* published as *IEEE 1149.1*.  The scope of
this work was to test and validate soldering of chips on an assembled
Printed Circuit Board.

Boundary scan test is supposed to be driven from an *Automated Test
Equipment* (ATE) and drive one or many *Test Access Ports* (TAP) of
chips on the board. TAPs expose a set of registers. In this register
set lies the *boundary-scan register* that directly controls I/O
buffers for the chip pins.  This allows to force output and probe
input signals for nets interconnecting JTAG-enabled chips, providing
continuity testing. JTAG document also describes using boundary scan
to apply test patterns to the internal logic of an IC, this is not
addressed by Crobe.

When developers take control of a JTAG chain through something else
than an ATE (which is supposed to be **Automated**), like a
PC-connected probe, one should designated probe as *JTAG ATE
Emulator*. With many people not knowing the meaning of "ATE", it
decayed to "JTAG Emulator". It means nothing, but this is the current
common name for a JTAG-based probe equipment.

As the protocol was designed for test, the specification does not
address non-test usages. These are outside the scope of the
standard. Nontheless, there is provision for vendor-specific
instructions. Of course, sideband access to all chips on the board is
precious, vendors reused the TAPs for other purpose, including
debug. Today, TAPs exist in Integrated Circuits, but do not always
provide proper boundary scan. Some TAPs only provide access to
internal capabilities of the chips. Most common capability is for
programmable chips debug.

JTAG wire protocol is implemented through a synchronous serial daisy
chain of TAPs running from TDI to TDO, clock is TCK. All TAPs have a
synchronized state driven through TMS pin. All TAPs at the same time
may be Resetting (in *Test/Logic Reset* state), Running test (in *Run
test/Idle* state), Shifting Instruction register (in *Shift-IR* state)
or Shifting Data register (in *Shift-DR* state). All other states are
transient and provide no semantic added value.

JTAG has support for auto-enumeration of chain, if implemented by TAPs
(this is optional in the spec): each TAP may shift-out its IDCODE
after reset. Most chips actually implement the necessary autodiscovery
features. IDCODEs are 32-bit identifiers that are supposed to be
unique for a given Die (but not necessarily package). Once chips are
enumerated, there can still be ambiguity on the actual split of the
Instruction Register chain. This requires out-of-band knowledge of
each actual TAP instruction register length.

Crobe models the ATE (the equipment that drives the JTAG wire protocol
pins), models the chain (the discovered chain of TAPs) and each TAP.
For any TAP IDCODE, a class can be registered to implement extended
features.

At the Chain level, Crobe does not allow to explicitly walk through
the state machine, it only exposes higher level operations like `Run`,
`Shift DR/IR`, `Reset`. At the TAP level, Crobe allows for shifting a
data register value in/out (both are optional) for a given
instruction. It's Crobe responsibility to shift the instruction in IR
if needed. This allows transparent multiplexing of JTAG chain between
multiple TAP drivers.

Crobe implements boundary scan features through generic support of
Boundary Scan operations, with no requirement for IC-specific code. It
relies on *Boundary Scan Definition Language* (BSDL) files that
manufacturers can provide for their chips.  Crobe builds a database of
BSDL definitions. There are dedicated commands for this usage. See
XXX.

Circa 2000, JTAG reunited to create *IEEE 1149.7*, an extension to
base protocol allowing fancy wiring variants.  There is limited
support for this in Crobe. The only subset of *IEEE 1149.7* that is
implemented is the method for switching TAPs to backward-compatible
4-wire variant at initialization.

SWD
===

SWD stands for *Single Wire Debug*, this is an ARM-developed,
ARM-specific debug protocol. *Single Wire* is marketing speech for
single **data** wire, as there is also a clock signal. So it uses two
wires:

* *SWCLK*, "Single Wire Clock", always driven by the probe (you may find
  errneous naming of *SWDCLK* sometimes),
* *SWDIO*, "Single Wire Data IO", a bi-directional IO between probe and
  target.

Component connected to SWD lines on the target side is called a *Debug
Port* (DP). It is a bridge to multiple *Application Ports* (APs). APs
provide different kind of access to internals of chips, most common
one (defined by ARM) is Mem-AP, which bridges access to the CPU Core
debug bus (AHB or AXI subset). In turn, access to this debug bus
provides access to internal main bus of chip.  For more details, See
`ARM IHI0029 <https://developer.arm.com/docs/ihi0029/e>`_.

SWD instance of a DP is a SW-DP. ARM also defines a JTAG variant for a
DP, which is a JTAG-DP. When DP supports both JTAG and SWD, it is
named SWJ-DP. SWJ-DPs need some special initialization sequences to
select between JTAG and SWD variants, this is handled by Crobe
transparently.

In ARM Cortex line of CPUs, CPU control is done through memory-mapped
registers on the debug bus.  This is how SWD gives access to CPU and
internal chip programming.

In SWD and all downstream components, there are autodiscovery
features:

* SWD DP has an IDCODE that designates type of DP (not type of chip --
  a common mistake),

* DP can enumerate APs connected to it, they provide an Identification
  register (IDR) that designates the AP type and implementation,

* Memory AP (AHB-AP, AXI-AP) gives address to the root ROM Table, a
  tree of constant data structures in memory that describes the SoC
  debug components types and addresses. Root of the ROM Table tree is
  supposed to give the target SoC identifier.

Crobe implements the whole set of autodiscovery features. When IDCODE,
IDRs and ROM Tables are correctly implemented, crobe can tell the
target SoC type. There are some exception where integrators screwed
the implementation (bogus identifier format, default identifier value,
etc.), Crobe tries to work around the bugs.

SPI
===

SPI stands for *Serial Peripheral Interface*. It is a de-facto
standard in the industry and comes with some ambiguities. In
particular, word size, clock polarity and phase can differ among chips
claiming SPI support. Crobe only supports "mode 0" SPI, i.e. set
outputs on falling edge, register on rising of clock, with 8-bit
words. This is sufficient for interfacing with most SPI peripherals of
the market.

SPI communication uses clock (SCK), Master Output, Slave Input (MOSI)
and Master Input, Slave Output (MISO) lines. Multiple SPI peripherals
can share those three lines, then a dedicated selection signal must be
wired to each slave. Most of the time, it is called Chip Select (CS).

Crobe models the SPI master, and multiple Chip Select lines. When
using a SPI adapter, you may need to specify for Chip Select 0 as
direct child of SPI adapter.

SPI has no autodiscovery features, whatever the component connected to
a SPI line, you should explicitly specify its type.  Once type of
target is known, there may be some autodiscovery of actual
implementation. For instance, most modern SPI flashes offer for an
identification code, once Crobe is told to look for a SPI flash, it
will try to use either identification code, of SFDP tables, if
available.

I2C
===

I2C stands for Inter-Integrated-Circuit. It is a two-wire multidrop
interface that was developed and specified by Philips (now NXP). For
acutal specification, refer to `UM10204
<https://www.nxp.com/docs/en/user-guide/UM10204.pdf>`_.

I2C uses two open-drain (wired AND) wires. Its speed is mostly limited
by the total capacitance of the bus. Most common implementations are
in the 100 kHz to 400 kHz range. 1 MHz+ specification exists, but its
use is sporadic.

There are no proper autodiscovery features on I2C. Even scanning for
presence of slave on a given address is unspecified (while mostly
possible anyway).

10-bit addressing supoprt is mostly a hack above 7-bit addresses. It
is supported transparently.

SMBUS
=====

SMBUS stands for System-Management Bus. It is an Intel-developed
cousin of I2C. It is partially wire-protocol compatible, in a way some
devices claim for mixed I2C/SMBUS compatibility.  `Specification
<http://smbus.org/specs/SMBus_3_1_20180319.pdf>`_ is now maintained by
SMI forum.

SMBUS defines some added features:

* Minimal clock rate,
* Normalized *Network Layer* (i.e. frame and command format),
* Transmission integrity assessment (integrity byte appended to all
  transactions),
* Proper bus slave enumeration and dynamic address allocation known as
  *Address Resolution Protocol*.

Crobe supports SMBUS as a child of an I2C interface. Just summon
`smbus` on an I2C interface to get SMBUS capabilities.

Chipcon
=======

Chipcon (now Ti) had a lineup of 8051-based microcontrollers using a
custom debug protocol which looks like SPI (with some subtilities on
the data line when no data is clocked). Crobe supports this protocol
and is able to program CC24xx MCUs.

.. _`Concepts`: concepts.html
