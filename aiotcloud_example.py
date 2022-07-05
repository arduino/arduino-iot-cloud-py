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
#
# This file is part of the Python Arduino IoT Cloud.

import time
from random import randint, choice
try:
    import logging
    import asyncio
except ImportError:
    import uasyncio as asyncio
    import ulogging as logging
from aiotcloud import AIOTCloud
if hasattr(time, "strftime"):
    from time import strftime
else:
    from ulogging.ustrftime import strftime

DEBUG_ENABLED = True

KEY_URI   = "pkcs11:token=arduino"
CERT_URI  = "pkcs11:token=arduino"
CA_PATH   = "ca-root.pem"
DEVICE_ID = b"25deeda1-3fda-4d06-9c3c-dd31be382cd2"

async def user_main(aiot):
    """
                    Add your code here.
    NOTE: To allow other tasks to run, this function must yield
    execution periodically by calling asyncio.sleep(seconds).
    """
    while True:
        aiot["user"] = choice(["=^.. ^=", "=^ ..^="])
        # The composite cloud object's fields can be assigned to individually:
        aiot["clight"]["hue"] = randint(0, 100)
        # Or with dictionary to set multiple fields.
        aiot["clight"] = {"bri" : randint(0, 100), "sat": randint(0, 100)}
        await asyncio.sleep(1.0)

def on_switch_changed(aiot, value):
    """
    This is a write callback for the switch, which toggles
    the LED variable. The LED variable can be accessed via
    the aiot cloud object passed in the first argument.
    """
    if value and not hasattr(on_switch_changed, "init"):
        on_switch_changed.init=True
        logging.info(f"Someone left the lights on!")
    aiot["led"] = value

async def main():
    aiot = AIOTCloud(device_id=DEVICE_ID, ssl_params = {"pin":"1234", "keyfile":KEY_URI, "certfile":CERT_URI, "ca_certs":CA_PATH})
    # This cloud object is initialized with its last known value from the cloud.
    aiot.register("sw1", value=None, on_write=on_switch_changed, interval=0.250)

    # This cloud object is initialized with its last known value from the cloud,
    # and gets manually updated from the switch's on_write_change callback.
    aiot.register("led", value=None)

    # This is a periodic cloud object that gets updated every 1 second.
    aiot.register("pot", value=None, on_read=lambda x:randint(0, 1024), interval=1.0)

    # This is a periodic cloud object that gets updated every 1 second,
    # with the formatted current time value.
    aiot.register("clk", value=None, on_read=lambda x:strftime("%H:%M:%S", time.localtime()), interval=1.0)

    # This variable is an example for a composite object (a colored light object in this case),
    # which is composed of multiple variables. This object is initialized, and can be assigned
    # to using dictionaries, or using indexing notation for individual fields.
    aiot.register("clight", value={"hue" : 22, "sat": 75, "bri": 10, "swi": True})

    # This variable is updated manually from user_main.
    aiot.register("user", value="")

    # Start the AIoT client.
    await aiot.run(user_main(aiot), debug=DEBUG_ENABLED)

if __name__ == "__main__":
    logging.basicConfig(
            datefmt="%H:%M:%S",
            format="%(asctime)s.%(msecs)03d %(message)s",
            level=logging.DEBUG if DEBUG_ENABLED else logging.INFO)
    asyncio.run(main())
