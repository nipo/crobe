"""Etherlink-style control plane: NUL-terminated ASCII control commands
and the parameter table the server advertises.

Mirrors the constants in Intel's ``intel_st_debug_if_constants.c`` plus
the welcome-message format from
``intel_st_debug_if_server.c::generate_server_welcome_message``.
"""

# Welcome / handshake messages
READY_MSG = b"READY\0"
NOT_READY_MSG = b"NOT_READY\0"
REJECT_MSG = b"SERVER_BUSY\0"

# Per-socket names embedded in the ``"<name> HANDLE=<int>"`` ack messages.
SOCK_CONTROL = "Control"
SOCK_MGMT = "Management"
SOCK_MGMT_RSP = "Management Response"
SOCK_H2T = "H2T"
SOCK_T2H = "T2H"

# Default buffer sizes advertised in the welcome message. Influence
# Quartus' batching but aren't load-bearing for correctness.
DEFAULT_H2T_BUFF_SZ = 0x4000
DEFAULT_MGMT_BUFF_SZ = 0x4000
DEFAULT_CTRL_BUFF_SZ = 0x1000

# Control command names
CMD_PING = "PING"
CMD_GET_PARAM = "GET_PARAM"
CMD_SET_PARAM = "SET_PARAM"
CMD_GET_DRIVER_PARAM = "GET_DRIVER_PARAM"
CMD_SET_DRIVER_PARAM = "SET_DRIVER_PARAM"
CMD_DISCONNECT = "DISCONNECT"

# Control responses
RSP_PING = b"PONG\0"
RSP_SET_PARAM_ACK = b"SET_PARAM_ACK\0"
RSP_SET_PARAM_FAIL = b"SET_PARAM_FAIL_ACK\0"
RSP_GET_PARAM_FAIL = b"GET_PARAM_FAILURE\0"
RSP_DISCONNECT = b"DISCONNECT_ACK\0"
RSP_UNRECOGNIZED = b"UNRECOGNIZED_COMMAND\0"

# Server parameter names recognised by GET_PARAM/SET_PARAM.
PARAM_MGMT_SUPPORT = "MGMT_SUPPORT"
PARAM_H2T_RX_BUFF_SZ = "H2T_RX_BUFF_SZ"
PARAM_MGMT_RX_BUFF_SZ = "MGMT_RX_BUFF_SZ"
PARAM_CTRL_RX_BUFF_SZ = "CTRL_RX_BUFF_SZ"
PARAM_T2H_NAGLE = "T2H_NAGLE"
PARAM_MGMT_RSP_NAGLE = "MGMT_RSP_NAGLE"
PARAM_SERVER_LOOPBACK = "SERVER_LOOPBACK"


def welcome_message(*, mgmt_support, h2t_rx_buff_sz,
                    mgmt_rx_buff_sz, ctrl_rx_buff_sz, handle):
    """Generate the NUL-terminated welcome banner sent on CTRL.

    Format (matches Intel's reference verbatim — Quartus parses exactly
    this string)::

        Welcome to INTEL_ST_HOST_EP_SERVER:
        MGMT_SUPPORT=<n> H2T_RX_BUFF_SZ=<n> MGMT_RX_BUFF_SZ=<n>
        CTRL_RX_BUFF_SZ=<n> HANDLE=<int>
    """
    text = (
        f"Welcome to INTEL_ST_HOST_EP_SERVER: "
        f"{PARAM_MGMT_SUPPORT}={mgmt_support} "
        f"{PARAM_H2T_RX_BUFF_SZ}={h2t_rx_buff_sz} "
        f"{PARAM_MGMT_RX_BUFF_SZ}={mgmt_rx_buff_sz} "
        f"{PARAM_CTRL_RX_BUFF_SZ}={ctrl_rx_buff_sz} "
        f"HANDLE={handle}"
    )
    return text.encode("ascii") + b"\0"


def expected_handle_message(sock_name, handle):
    """The string the client must send back on each socket to claim it."""
    return f"{sock_name} HANDLE={handle}".encode("ascii") + b"\0"


def parse_control_command(line):
    """Split a NUL-stripped control line into ``(verb, args)``."""
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]
