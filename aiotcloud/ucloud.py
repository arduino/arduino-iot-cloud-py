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
import logging
from kpn_senml import SenmlPack
from kpn_senml import SenmlRecord
from aiotcloud.umqtt import MQTTClient
from asyncio import CancelledError

try:
    from asyncio import InvalidStateError
except ImportError:
    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass

def _timestamp():
    return int((time.time() + 0.5) * 1000)

class AIOTProperty(SenmlRecord):
    def __init__(self, aiot, name, value, on_read=None, on_write=None, interval=None):
        self.aiot = aiot
        self.on_read = on_read
        self.on_write = on_write
        self.interval = interval
        self.updated = False
        self.call_on_write = False
        self.dtype = type(value)
        self.timestamp = _timestamp()
        super().__init__(name, value=value, callback=self.senml_callback)

    def __setattr__(self, key, value):
        if (key == "value" and value is not None):
            if (self.dtype is type(None)):
                self.dtype = type(value)
            elif not isinstance(value, self.dtype):
                raise TypeError("Invalid data type, expected {}".format(self.dtype))
            else:
                self.updated = True
            self.timestamp = _timestamp()
            logging.debug("task: '{}' updated: '{}' timestamp: '{}'".format(self.name, value, self.timestamp))
        super().__setattr__(key, value)

    def senml_callback(self, record, **kwargs):
        # Updated from the cloud, the value shouldn't be sent back.
        self.updated = False
        self.call_on_write = True

    async def run(self):
        while True:
            if (self.on_read is not None):
                self.value = self.on_read(self.aiot)
            if (self.on_write is not None and self.call_on_write):
                self.call_on_write = False
                self.on_write(self.aiot, self.value)
            await asyncio.sleep(self.interval)

class AIOTCloud():
    def __init__(self, device_id, thing_id, ssl_params, server="mqtts-sa.iot.oniudra.cc", port=8883):
        self.records = {}
        self.topic_in  = b"/a/t/" + thing_id + b"/e/i"
        self.topic_out = b"/a/t/" + thing_id + b"/e/o"
        self.senmlpack = SenmlPack('', self.senml_callback)
        self.tasks = [asyncio.create_task(self.mqtt_task(), name="mqtt"), ]
        self.mqtt_client = MQTTClient(device_id, server, port, ssl_params, callback=self.mqtt_callback)

    def __getitem__(self, key):
        return self.records[key].value

    def __setitem__(self, key, value):
        self.records[key].value = value

    def register(self, name, value, interval=1.0, on_read=None, on_write=None):
        if (value is None and on_read is not None):
            value = on_read(self)
        record = AIOTProperty(self, name, value, on_read, on_write, interval)
        self.records[name] = record
        if (on_read is not None or on_write is not None):
            self.tasks.append(asyncio.create_task(record.run(), name=record.name))
            logging.debug("task: '{}' created.".format(name))

    def senml_callback(self, record, **kwargs):
        logging.info("Unkown record: {} value: {}".format(record.name, record.value))

    def mqtt_callback(self, topic, msg):
        logging.debug("mqtt topic: '{}' message: '{}'".format(topic, msg))
        for key, record in self.records.items():
            if record.on_write is not None:
                self.senmlpack.add(record)
        self.senmlpack.from_cbor(msg)
        self.senmlpack.clear()

    async def mqtt_task(self, interval=0.100):
        while True:
            push_updates = False
            self.mqtt_client.check_msg()

            for key, record in self.records.items():
                if (record.updated):
                    record.updated = False
                    push_updates = True
                    self.senmlpack.add(record)

            if (push_updates):
                logging.debug("Pushing records to AIoT Cloud:")
                if (self.debug):
                    for record in self.senmlpack:
                        logging.info("  ==> record name: {} value: {}".format(record.name, record.value))
                self.mqtt_client.publish(self.topic_out, self.senmlpack.to_cbor())

            self.senmlpack.clear()
            await asyncio.sleep(interval)
 
    async def run(self, user_main=None, debug=False):
        self.debug = debug

        if (user_main is not None):
            # If user code is provided, append to tasks list.
            self.tasks.append(asyncio.create_task(user_main, name="user code"))

        logging.info("Connecting to AIoT Cloud.")
        self.mqtt_client.connect()

        logging.info("Subscribing to thing topic.")
        self.mqtt_client.subscribe(self.topic_in)

        while True:
            try:
                await asyncio.gather(*self.tasks, return_exceptions=False)
                logging.info("All tasks finished!")
                break
            except Exception as e: pass

            for task in self.tasks:
                try:
                    if task.done():
                        self.tasks.remove(task)
                    logging.error("Removed task: '{}'. Raised exception: '{}'."
                            .format(task.get_name(), task.exception()))
                except (CancelledError, InvalidStateError) as e: pass
