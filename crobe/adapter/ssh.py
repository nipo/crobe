from . import model
from ..protocol import smi
import os
import socket
import struct

__all__ = []

class SocketClosed(Exception):
    pass

@model.HwRoot.register
class Enumerator(model.ExplicitEnumerator):
    def __init__(self):
        model.Enumerator.__init__(self, "ssh")

    def child_spawn(self, name):
        return Adapter.from_target(name)
            
class Adapter(model.Adapter):
    @classmethod
    def from_target(cls, name):
        from urllib.parse import urlparse
        url = "ssh://" + name
        parsed = urlparse(url)
        
        return cls(host = parsed.hostname,
                   user = parsed.username,
                   password = parsed.password,
                   port = int(parsed.port or 22))

    supported_interfaces = []
    nickname = "ssh"

    def __init__(self, host, user, password, port):
        from paramiko.client import SSHClient
        
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        model.Adapter.__init__(self, f"ssh:{self.user}@{self.host}:{self.port}")

        self.client = SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(self._auto_accept_policy())
        self.client.connect(hostname = self.host,
                            port = self.port,
                            username = self.user,
                            password = self.password)

    def _auto_accept_policy(self):
        from paramiko.client import MissingHostKeyPolicy
        class Policy(MissingHostKeyPolicy):
            def missing_host_key(self, client, hostname, key):
                return
        return Policy
        
    @property
    def firmware_info(self):
        return "SSH %s:%d" % (self.host, self.port)

    def open(self, interface_name):
        if interface_name.lower() == "smi":
            return SmiInterface(self)

class SmiInterface(smi.Interface):
    def __init__(self, port, name = None):
        super().__init__(port, name)
        self.iface = "eth0"

    def option_set(self, opt):
        if opt.startswith("iface="):
            self.iface = opt[6:]

    def run_atomic(self, command):
        self.logger.protocol("Running %s", command)
        i, o, e = self.port.client.exec_command(command)
        i.close()
        stdout = o.read()
        stderr = e.read()
        self.logger.protocol("-> '%s' '%s'", stdout, stderr)
        return stdout, stderr
            
    def _execute(self, operation_list):
        for op in operation_list:
            if isinstance(op, smi.C22Read):
                o, e = self.run_atomic(f"phytool read {self.iface}/{op.phyad:#x}/{op.addr:#x}")
                if e:
                    raise smi.ProtocolError(e)
                op.data = int(o.strip(), 16)

            elif isinstance(op, smi.C22Write):
                o, e = self.run_atomic(f"phytool write {self.iface}/{op.phyad:#x}/{op.addr:#x} {op.data:#x}")
                if e:
                    raise smi.ProtocolError(e)
            
            else:
                raise NotImplementedError(op)
