# Crobe

Crobe is a generic hardware probe toolset.  It drives the usual serial
protocols (JTAG, SWD, I2C, SPI, SMBus, 1-wire, UART, ...) through
adapters, and builds on top of them to identify, inspect, program and
debug chips.

## Using crobe

Three frontends share the same object model:

* **CLI** — the `crobe` entry point is a Click command tree.
  `crobe info adapters` lists detected probe hardware,
  `crobe info enumerate -r <root>` walks a bus and shows what was
  found, `crobe chip -r <root> program image.elf` programs a target.
  See `crobe --help` for the full command set.
* **REPL** — `crobe repl` opens an interactive Python shell
  (ptpython) with the component `root` preloaded, for exploratory
  poking at hardware.
* **Scripts** — `crobe run script.py` (or `crobe run -m module`) runs
  a Python script with an initialized crobe context, for automated or
  repetitive jobs.

## Architecture

### Component tree

Everything in crobe is a `Component` (see `crobe.model`), organized as
a tree: enumerators at the root, then adapters, interfaces, buses, and
finally chips and their internal blocks.  Children are looked up or
spawned on demand, so a crobe session only instantiates what it
actually touches.  Tree nodes are addressed by slash-separated paths
where each element selects a child by index or name, optionally with
options in parentheses, e.g.  `ftdi/0/jtag(fmax=6M,reset)`.

Layers:

* `crobe.adapter` — drivers for probe hardware (FTDI, J-Link,
  CMSIS-DAP, USB Blaster, XVC, plain serial, ...) and the enumerators
  that detect them;
* `crobe.protocol` — adapter-independent wire protocol interfaces
  (JTAG, SWD, I2C, SPI, ...);
* `crobe.component` — chip and IP-block drivers, sorted by
  manufacturer or by industry standard;
* `crobe.target` — merges disparate components back into a common
  feature set (reset, erase, program).  A `Field` pass pattern-matches
  discovered components and attaches the matching targets.

### I/O batching

Protocol interfaces are transaction-batched: callers build lists of
`Operation` objects through factory methods and hand them to
`execute()` in one go.  The adapter driver translates a whole batch at
once, which keeps USB round-trips (the usual bottleneck) to a minimum.

### Autodiscovery

Adapters, buses and components are enumerated at runtime and exposed
as one uniform tree.

Autodiscovery is used as much as possible: each protocol in the node
tree can hold a database of potential children, registered by
protocol-specific ID.  When protocol allows so, IDs are looked up
automatically and components are automatically resolved.

### Extensibility

Crobe is pluggable through the `crobe_plugin` PEP 420 namespace
package: external packages can contribute enumerators, adapters,
components, targets and CLI commands without touching this tree.

## Documentation

This file is only an overview; the documentation tree lives in `doc/`.

## License

BSD, see `License`.
