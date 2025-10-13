import warnings

# ftdi-based
try:
    from . import digilent
    from . import proby
    from . import lattice
    from . import smartfusion
    from . import icestick
    from . import dbg_hub
    from . import dbgsafe
    from . import dbg_fpga
    from . import sipeed
    from . import efinix
    from . import busblaster
    from . import dc590
    from . import trenz
except RuntimeError:
    warnings.warn("FTDI-based adapters unavailable")

try:
    import usb

    # usb-based
    try:
        from . import jlink
        from . import xilinx
        from . import kitprog
        from . import ch341
        from . import littlewire
        from . import cy_usb_serial
        from . import xds110
        from . import cmsis_dap
        from . import esp_usb_jtag
    except usb.core.NoBackendError:
        pass
except ModuleNotFoundError:
    warnings.warn("USB-based adapters unavailable")

from . import xvcd
from . import serial
from . import tcp
from . import udp
from . import ssh
    
