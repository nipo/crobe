from ..model import JtagSramFpga, SramFpga
from ...part_id import PartId
from ...protocol import jtag
import time
import enum

parts = {
    0x362c: "5EB013B",
    0x364f: "5ED065B",
}

@jtag.Chain.db.register(*[PartId(0, 0x6e, x) for x in parts.keys()])
class Agilex(jtag.Tap, JtagSramFpga):
    max_freq = 30e6
    irlen = 10

    class VoltageChannel(enum.IntEnum):
        External0 = 0
        External1 = 1
        Vcc = 2
        VccIoSdm = 3
        VccPt = 4
        VccRCore = 5
        VccHSdm = 6
        VccLSdm = 7
        VccAdc = 9

    CONFIG = jtag.Dr(None)
    BOUNDARY = jtag.Dr(None)

    EXTEST           = jtag.Instruction(0x00f, "BOUNDARY")
    SAMPLE           = jtag.Instruction(0x005, "BOUNDARY")
    IDCODE           = jtag.Instruction(0x006, "DEVICE_ID")
    USERCODE         = jtag.Instruction(0x007, "DEVICE_ID")
    CLAMP            = jtag.Instruction(0x00a, "BOUNDARY")
    HIGHZ            = jtag.Instruction(0x00b, "BOUNDARY")

    SDM_IO = jtag.Dr(34)
    SDM_CMD = jtag.Instruction(0x201, "SDM_IO")
    SDM_RSP = jtag.Instruction(0x202, "SDM_IO")
    SDM_WAKEUP = jtag.Instruction(0x281, None)

    CMF_DATA = jtag.Instruction(0x002, None)
    CMF_CONTROL_REG = jtag.Dr(37)
    CMF_CONTROL = jtag.Instruction(0x208, "CMF_CONTROL_REG")

    CHECK_STATUS_REG = jtag.Dr(492)
    CHECK_STATUS = jtag.Instruction(0x004, "CHECK_STATUS_REG")

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        JtagSramFpga.__init__(self)
        self.name = f"A{parts.get(idcode.part_no, hex(idcode.part_no))}"
        self.__sdm = None

    @property
    def sdm(self):
        if not self.__sdm:
            from .sdm_jtag import SdmJtag
            self.__sdm = SdmJtag(self)
            self.child_add(self.__sdm)
            self.__sdm.start()
        return self.__sdm

    def child_spawn(self, crit):
        if crit == "sdm":
            return self.sdm

    def is_configured(self):
        self.bla

    def sram_configure(self, program_data):
        self.logger.trace("Loading %d bytes to SRAM", len(program_data))
        raise NotImplementedError()

    def load(self, program):
        """Load bitstream via SDM + streaming"""
        if len(program) != 1:
            raise ValueError("Bitstream requires exactly one segment")

        self.sdm.config_request()

        blob = program[0].data
        self.logger.trace("Streaming %d bytes...", len(blob))
        self._cmf_load(blob)

        self.logger.trace("Checking CONF_DONE...")

        for retry in range(15-1, -1, -1):
            time.sleep(0.1)
            try:
                cs = self.sdm.config_status()
            except SdmError:
                if not retry:
                    raise
            if cs.conf_done:
                break

        self.logger.note("Configuration complete")
        self.execute([
            self.BYPASS.cmd(),
            self.cmd_run(16),
            ])

    def _cmf_load(self, bitstream):
        """Stream bitstream data to CMF_DATA IR
        """
        HEADER = bytes.fromhex("ffffffff002a7ea1")
        INITIAL_CHUNK = 4096
        MAX_CHUNK = 65536
        STATUS_RETRIES = 6000

        chunk_size = INITIAL_CHUNK
        stalled = True
        status_retries = STATUS_RETRIES
        reset = True

        with self.logger.progress("config", len(bitstream)) as pb:
            while True:
                done, error, progress, fifo_free = self._cmf_control(
                    request_data = stalled,
                    reset = reset,
                )

                reset = False

                if error:
                    raise RuntimeError("Program streaming error")

                pb.set(progress)

                if progress >= len(bitstream):
                    break

                status_retries -= 1
                if status_retries <= 0:
                    raise RuntimeError("Retry count exceeded")

                if done:
                    stalled = True
                    if chunk_size > INITIAL_CHUNK:
                        chunk_size //= 2
                    continue

                # ready for data
                if stalled:
                    stalled = False
                else:
                    chunk_size = min(chunk_size * 2, MAX_CHUNK)

                remaining = len(bitstream) - progress
                if remaining <= 0:
                    continue

                n = min(chunk_size, remaining)

                # Data is read from chip's progress position, not our
                # send position. On stall recovery, this re-sends data
                # the chip hasn't consumed yet.
                data_slice = bitstream[progress:progress + n]

                self.execute([
                    self.CMF_DATA.cmd(HEADER + data_slice, read_tdo=False),
                    self.cmd_run(16),
                    ])

                status_retries = STATUS_RETRIES

    def _cmf_control(self, request_data=False, reset=False):
        """Check config status via IR 0x208."""
        tdi_val = 0
        if request_data:
            tdi_val |= 1
        if reset:
            tdi_val |= 6

        result = self.CMF_CONTROL.shift(tdi_val, read_tdo=True)

        val = int(result)
        done = bool(val & 1)
        error = bool(val & 2)
        progress_words = (val >> 2) & 0x3FFFFFFF
        fifo_free = (val >> 32) & 0x1F
        return done, error, progress_words * 4, fifo_free
