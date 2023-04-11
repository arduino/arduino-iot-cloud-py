# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from .ucloud import ArduinoCloudClient # noqa
from .ucloud import ArduinoCloudObject
from .ucloud import timestamp

try:
    import asyncio
    import binascii
except ImportError:
    import uasyncio as asyncio
    import ubinascii as binascii


CADATA = binascii.unhexlify(
    b"308201cf30820174a00302010202141f101deba7e125e727c1a391e3ec0d"
    b"174ded4a59300a06082a8648ce3d0403023045310b300906035504061302"
    b"555331173015060355040a130e41726475696e6f204c4c43205553310b30"
    b"09060355040b130249543110300e0603550403130741726475696e6f301e"
    b"170d3138303732343039343730305a170d3438303731363039343730305a"
    b"3045310b300906035504061302555331173015060355040a130e41726475"
    b"696e6f204c4c43205553310b3009060355040b130249543110300e060355"
    b"0403130741726475696e6f3059301306072a8648ce3d020106082a8648ce"
    b"3d030107034200046d776c5acf611c7d449851f25ee1024077b79cbd49a2"
    b"a38c4eab5e98ac82fc695b442277b44d2e8edf2a71c1396cd63914bdd96b"
    b"184b4becb3d5ee4289895522a3423040300e0603551d0f0101ff04040302"
    b"0106300f0603551d130101ff040530030101ff301d0603551d0e04160414"
    b"5b3e2a6b8ec9b01aa854e6369b8c09f9fce1b980300a06082a8648ce3d04"
    b"03020349003046022100bfd3dc236668b50adc3f0d0ec373e20ac7f760aa"
    b"100dd320bfe102969b6b05d8022100ead9d9da5acd12529709a8ed660fe1"
    b"8d6444ffe82217304ff2b89aafca8ecf"
)


class Location(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"lat", "lon"}, **kwargs)


class Color(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"hue", "sat", "bri"}, **kwargs)


class ColoredLight(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "hue", "sat", "bri"}, **kwargs)


class DimmedLight(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "bri"}, **kwargs)


class Schedule(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        kwargs.update({("runnable", True)})  # Force task creation.
        self.on_active = kwargs.pop("on_active", None)
        # Uncomment to allow the schedule to change in runtime.
        # kwargs["on_write"] = kwargs.get("on_write", lambda aiot, value: None)
        self.active = False
        super().__init__(name, keys={"frm", "to", "len", "msk"}, **kwargs)

    async def run(self, aiot):
        while True:
            if self.initialized:
                ts = timestamp() + aiot.get("tz_offset", 0)
                if ts > self.frm and ts < (self.frm + self.len):
                    if not self.active and self.on_active is not None:
                        self.on_active(aiot, self.value)
                    self.active = True
                else:
                    self.active = False
            await asyncio.sleep(self.interval)


class Task(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        kwargs.update({("runnable", True)})  # Force task creation.
        self.on_run = kwargs.pop("on_run", None)
        if not callable(self.on_run):
            raise TypeError("Expected a callable object")
        super().__init__(name, **kwargs)

    async def run(self, aiot):
        while True:
            self.on_run(aiot)
            await asyncio.sleep(self.interval)
