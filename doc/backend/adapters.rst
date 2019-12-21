=================
Suported adapters
=================

Adapters were presented in the concepts_ chapter. Here we'll define
some supported ones.

Some generic instructions if you are looking for a supported adapter
root path:

* Connect it to your machine,

* (Linux, USB) Ensure udev rules allow raw access to the device,

* List connected adapters::

    $ crobe info adapters

* Take the adapter name and interface name, compose a path reading
  `"adapter_name/interface_name"`. Try enumerating the targets::

    $ crobe info enumerate -r adapter_name/interface_name

  See what happens.

J-Link
======

J-Link adapters are supported directly by implementing commands
described in Segger's RM8001. They support JTAG, SWD and SPI.

All protocols are implemented using raw bitstream I/O.  Probe
offloading is unused as SEGGER wants to keep it for its own usage.

J-Link performance is decent.

Some J-Link adapters support setting power (`power=on/off` option
string). All J-Link adapters support setting frequency, maximal
frequency is dependent on the model.

J-Link enumerator retrieves probe nickname from its configuration
area and uses it as adapter name.

FTDI-based probes
=================

There is a generic implementation for MPSSE-based JTAG, SPI, SWD,
Chipcon, I2C bus protocols.  All that is needed to make them work is
to declare to crobe where I/Os other than the ones hardwired in FTDI
(TDI, TDO, TMS, TCK, SDA, SCL) are wired.

Relevant probe declarations are included for Lattice HW-USBN-2B and
Icestick, Digilent HS2/3 and SMT, Busblaster, Microsemi Smartfusion
devboard, and other custom boards.  Adding support for a new board is
trivial.

FTDI-based probe have great performance.

All FTDI-based adapters support setting frequency, maximal frequency
is dependent on the model (60 MHz or 12 MHz, see datasheets for
details).  Sideband I/Os (resets, power enables, ...) are dependent on
the hardware implementation.

CH341
=====

WCH CH341 chip is a chinese low-cost USB to serial adapter with
support for I2C and SPI.  It implements basic access to these bus.

CH341 performance is terrible. It should theoritically support
frequency setting, but faster speeds insert spurs on I2C lines,
therefore it is disabled in driver implementation.

KitProg
=======

KitProg is a custom SWD adapter from Cypress. They use it in some of
their devkits.  It has basic support for SWD.

KitProg performance is average.

XVCD
====

XVCD is Xilinx Virtual Cable. This is a Xilinx-desinged custom
protocol for transporting JTAG. This adapter is able to connect to a
foreign XVC server.  Of course, remote Crobe instance can be used as
server.

XVC performance depends on backend and network latency to server.

Server target is the child name. For instance, the following command
will enumerate JTAG chain on localhost server, port 1234::

  $ crobe info enumerate -r xvcd/127.0.0.1:1234/jtag

.. _`Concepts`: concepts.html
