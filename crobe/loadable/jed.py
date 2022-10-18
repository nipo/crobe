from . import model

@model.Program.ext_db.register("jed")
@model.Program.format_db.register("jed")
class JedecImage(model.Program):
    def __init__(self, filename, offset = 0):
        super().__init__(filename)
        from ..jed import jed
        j = jed.Jed(filename)

        self.info["fuse_count"] = j.fuse_count
        self.info["pin_count"] = j.pin_count
        self.info["device_architecture"] = j.device_architecture
        self.info["device_pinout"] = j.device_pinout
        self.info["security"] = j.security
        self.info["notes"] = '\n'.join(j.notes)
        for n in j.notes:
            if n.lower().startswith("device name: "):
                self.info["device"] = n[13:]
            elif n.lower().startswith("device "):
                self.info["device"] = n[7:]
        self.append(model.Segment(0, bytes(j.fuses), filename))
