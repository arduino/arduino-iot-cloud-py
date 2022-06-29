# This file is part of the Python AIoT Cloud.
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

import time
from kpn_senml import SenmlPack
from kpn_senml import SenmlRecord
from aiotcloud.umqtt import MQTTClient
try:
    import logging
    import asyncio
    from asyncio import CancelledError
    from asyncio import InvalidStateError
except ImportError:
    import ulogging as logging
    import uasyncio as asyncio
    from uasyncio.core import CancelledError
    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass

def timestamp_s():
    return int((time.time() + 0.5))

def timestamp_ms():
    return int((time.time() + 0.5) * 1000)

def create_task(coro, name=None):
    if hasattr(asyncio.Task, "get_name"):
        return asyncio.create_task(coro, name=name)
    else:
        return asyncio.create_task(coro)

class AIOTProperty(SenmlRecord):
    def __init__(self, aiot, name, value, on_read=None, on_write=None, interval=None):
        self.aiot = aiot
        self.on_read = on_read
        self.on_write = on_write
        self.interval = interval
        self.updated = False
        self.call_on_write = False
        self.dtype = type(value)
        self.timestamp = timestamp_ms()
        super().__init__(name, value=value, callback=self.senml_callback)

    def __setattr__(self, key, value):
        if (key == "_value" and value is not None):
            if (self.dtype is type(None)):
                self.dtype = type(value)
            elif not isinstance(value, self.dtype):
                raise TypeError(f"Invalid data type, expected {self.dtype}")
            else:
                self.updated = True
            self.timestamp = timestamp_ms()
            logging.debug(f"task: {self.name} updated: {value} timestamp: {self.timestamp}")
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
    def __init__(self, device_id, ssl_params=None, server="mqtts-sa.iot.oniudra.cc", port=8883, keepalive=10):
        self.tasks = []
        self.records = {}
        self.thing_id = None
        self.keepalive = keepalive
        self.last_ping = timestamp_s()
        self.device_topic = b"/a/d/" + device_id + b"/e/i"
        self.senmlpack = SenmlPack("urn:uuid:"+device_id.decode("utf-8"), self.senml_callback)
        self.mqtt_client = MQTTClient(device_id, server, port, ssl_params, keepalive=keepalive, callback=self.mqtt_callback)
        # Note: this property is set by the cloud discovery protocol.
        self.register("thing_id", value=None, on_write=self.discovery_callback)

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
            self.tasks.append(create_task(record.run(), name=record.name))
            logging.debug(f"task: {name} created.")

    def senml_callback(self, record, **kwargs):
        logging.error(f"Unkown record: {record.name} value: {record.value}")

    def mqtt_callback(self, topic, message):
        logging.debug(f"mqtt topic: {topic[:16]}... message: {message[:16]}...")
        self.senmlpack.clear()
        for key, record in self.records.items():
            if record.on_write is not None:
                self.senmlpack.add(record)
        self.senmlpack.from_cbor(message)
        self.senmlpack.clear()

    def discovery_callback(self, aiot, thing_id):
        logging.info(f"Device configured via discovery protocol.")
        if not thing_id:
            raise(Exception("Device is not linked to a Thing ID."))
        self.thing_id  = bytes(thing_id, "utf-8")
        self.topic_in  = b"/a/t/" + self.thing_id + b"/e/i"
        self.topic_out = b"/a/t/" + self.thing_id + b"/e/o"
        logging.info(f"Subscribing to thing topic {self.topic_in}.")
        self.mqtt_client.subscribe(self.topic_in)

    async def mqtt_task(self, interval=0.100):
        while True:
            self.mqtt_client.check_msg()

            if self.thing_id is not None:
                for key, record in self.records.items():
                    if (record.updated):
                        record.updated = False
                        self.senmlpack.add(record)

                if len(self.senmlpack._data):
                    logging.debug("Pushing records to AIoT Cloud:")
                    if (self.debug):
                        for record in self.senmlpack:
                            logging.debug(f"  ==> record: {record.name} value: {record.value}")
                    self.mqtt_client.publish(self.topic_out, self.senmlpack.to_cbor(), qos=True)
                elif (self.keepalive and (timestamp_s() - self.last_ping) > self.keepalive):
                    self.mqtt_client.ping()
                    self.last_ping = timestamp_s()
                    logging.debug("No records to push, sent a ping request.")

                self.senmlpack.clear()

            await asyncio.sleep(interval)
 
    async def run(self, user_main=None, debug=False):
        self.debug = debug
        if (user_main is not None):
            # If user code is provided, append to tasks list.
            self.tasks.append(create_task(user_main, name="user code"))

        logging.info("Connecting to AIoT cloud...")
        if not self.mqtt_client.connect():
            logging.error("Failed to connect AIoT cloud.")
            return

        logging.info("Subscribing to device topic.")
        self.mqtt_client.subscribe(self.device_topic)

        self.tasks.append(create_task(self.mqtt_task(), name="mqtt"))

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
                    if hasattr(asyncio.Task, "get_name"):
                        logging.error(f"Removed task: {task.get_name()}. Raised exception: {task.exception()}.")
                    else:
                        logging.error(f"Removed task.")
                except (CancelledError, InvalidStateError) as e: pass
