============
 GDB Server
============

Protocol Server
===============

GDB server protocol was designed for 7-bit serial lines. It comes with
frame management, error recovery and 8-bit sequence escapes. As
modernity came in, there are extensions to remove all this cruft when
transport is a reliable 8-bit capable stream like a TCP socket.  Crobe
handles all this in a generic protocol server framework.

Protocol Handler
================

On top of the protocol server is stacked a protocol handler. It can
handle command packets and generate responses. This is generic as well
and handles some of the debugger model (enumerating target type,
providing register definition to gdb), and execution model, but
everything may be overridden.

Target Handler
==============

At last, there is a target-specific handler that takes care of binding
GDB commands to target-specific actions. For now, only ARM Cortex
backend is implemented in Crobe.
