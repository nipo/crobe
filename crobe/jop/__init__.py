"""JTAG-over-Protocol (JoP) — Altera's TCP-framed JTAG bit-bang protocol.

Sub-modules:

* :mod:`.bytestream` — wire-level byte commands consumed by Altera's
  on-chip ``sld_hub_ctrl_core`` (the soft JTAG master that Quartus
  drives over the network).
* :mod:`.framing` — the Avalon-ST-over-TCP packet framing used between
  ``etherlink`` (or our equivalent) and Quartus' jtagd-side driver.
* :mod:`.listener` — TCP listener implementing the 5-socket etherlink
  handshake plus the per-session synchronous poll loop.

The on-chip JoP byte protocol is documented in plain SystemVerilog in
the ``sld_hub_ctrl_core`` IP; the wire framing comes from Intel's
BSD-licensed reference at
https://github.com/altera-fpga/remote-debug-for-intel-fpga.
"""
