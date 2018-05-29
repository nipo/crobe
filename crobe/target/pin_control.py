import enum

class Mode:
    Disabled           = 0b00000
    Enabled_           = 0b00001
    ResistorUp_        = 0b00010
    ResistorDown_      = 0b00100
    DriveUp_           = 0b01000
    DriveDown_         = 0b10000
    Pushpull           = 0b11001
    Input              = 0b00001
    InputPull          = 0b00111
    InputPullup        = 0b00011
    InputPulldown      = 0b00101
    Opendrain          = 0b10001
    Opensource         = 0b01001
    OpendrainPullup    = 0b10011
    OpensourcePulldown = 0b01101

class Controller:
    def pin_get_many(self, pin_names = None):
        return dict((p, self.pin_get(p)) for p in pin_names)

    @property
    def pin_names(self):
        return []

    def pin_get(self, name):
        return None

    def pin_set(self, name, value):
        pass

    def pin_config(self, name, mode = Mode.Input):
        pass
