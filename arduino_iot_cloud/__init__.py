# This file is part of the Arduino IoT Cloud Python client.
#
# The MIT License (MIT)
#
# Copyright (c) 2022 Arduino SA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
from .ucloud import AIOTClient # noqa
from .ucloud import AIOTObject
from .ucloud import timestamp

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


class Location(AIOTObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"lat", "lon"}, **kwargs)


class Color(AIOTObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"hue", "sat", "bri"}, **kwargs)


class ColoredLight(AIOTObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "hue", "sat", "bri"}, **kwargs)


class DimmedLight(AIOTObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "bri"}, **kwargs)


class Schedule(AIOTObject):
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
