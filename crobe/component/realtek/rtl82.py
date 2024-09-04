from .. import ethernet_phy
from ...protocol import smi
from ...part_id import PartId
from ... import bitfield
import enum

def paged_address(reg, page):
    return (page << 3) | (reg & 7)

class RtlHighPagedPhy(ethernet_phy.Clause22EthernetPhy):
    DEFAULT_HIGH_PAGE = 0xa42

    def execute(self, ops):
        pending = []
        rsp = {}
        page = None

        for index, op in enumerate(ops):
            if isinstance(op, (smi.C22Read, smi.C22Write)) and op.addr > 0x20:
                next_page = op.addr >> 3
                if page != next_page:
                    pending.append(self.cmd_write(0x1f, next_page))
                    page = next_page

                addr = 0x10 | (op.addr & 0x7)
                rsp[index] = len(pending)

                if isinstance(op, smi.C22Read):
                    pending.append(self.cmd_read(addr))
                else:
                    pending.append(self.cmd_write(addr))


            else:
                if page is not None:
                    pending.append(self.cmd_write(0x1f, self.DEFAULT_HIGH_PAGE))
                    page = None
                pending.append(op)

        if page is not None:
            pending.append(self.cmd_write(0x1f, self.DEFAULT_HIGH_PAGE))
            page = None

        super(ethernet_phy.Clause22EthernetPhy, self).execute(pending)

        for index, pending_index in rsp.items():
            ops[index].data = pending[pending_index].data
