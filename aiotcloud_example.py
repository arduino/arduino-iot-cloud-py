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

import time
import asyncio
import random
import logging
from aiotcloud import AIOTCloud

KEY_URI = "pkcs11:token=arduino"
CERT_URI = "pkcs11:token=arduino"
CA_PATH = "ca-root.pem"

DEVICE_ID = b"25deeda1-3fda-4d06-9c3c-dd31be382cd2"
THING_ID  = b"d2a51288-9cd3-43e3-b35b-08689cfe84f3"

async def user_main(aiot):
    '''
    Add your code here.
    NOTE: To allow other tasks to run, this function must yield
    execution periodically by calling asyncio.sleep(seconds).
    '''
    while True:
        aiot["user"] = random.choice(["=^.. ^=", "=^ ..^="])
        await asyncio.sleep(0.5)

def on_switch_changed(aiot, value):
    aiot["led"] = value

async def main():
    aiot = AIOTCloud(device_id=DEVICE_ID, thing_id=THING_ID, ssl_params = {
            "pin":"1234", "keyfile":KEY_URI, "certfile":CERT_URI, "ca_certs":CA_PATH})
    aiot.register("led", value=False)
    aiot.register("sw1", value=False, on_write=on_switch_changed, interval=0.250)
    aiot.register("pot", value=None, on_read=lambda x:random.randint(0, 1024), interval=1.0)
    aiot.register("clk", value=None, on_read=lambda x:time.strftime('%X'), interval=1.0)
    aiot.register("user", value="")
    await aiot.run(user_main(aiot))

if __name__ == '__main__':
    logging.basicConfig(
            level=logging.DEBUG,
            datefmt="%H:%M:%S",
            format="%(asctime)s.%(msecs)03d %(message)s")
    asyncio.run(main())
