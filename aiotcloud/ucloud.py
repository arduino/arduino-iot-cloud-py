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
    from aiotcloud import ntptime
    from uasyncio.core import CancelledError
    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass

def timestamp():
    return int(time.time())

class AIOTObject(SenmlRecord):
    def __init__(self, aiot, name, value, on_read=None, on_write=None, interval=None):
        self.aiot = aiot
        self.on_read = on_read
        self.on_write = on_write
        self.interval = interval
        self.updated = False
        self.on_write_scheduled = False
        self.dtype = type(value)
        self.timestamp = timestamp()
        super().__init__(name, value=value, callback=self.senml_callback)

    def __repr__(self):
        return f"{self.value}"

    def __contains__(self, key):
        return key in self.value

    def __getitem__(self, key):
        return self.value[key].value

    def __setitem__(self, key, value):
        if self._value is None:
            self._value = {}
        if key in self.value:
            self.value[key].value = value
        else:
            self.value[key] = AIOTObject(self.aiot, f"{self.name}:{key}", value)
        self.updated = True

    @SenmlRecord._parent.setter
    def _parent(self, value):
        self.__parent = value
        if isinstance(self.value, dict):
            for key, record in self.value.items():
                record._parent = value

    @SenmlRecord.value.setter
    def value(self, value):
        if (value is not None):
            if (self.dtype is type(None)):
                self.dtype = type(value)
                logging.debug(f"task: {self.name} initialized from the cloud.")
            elif not isinstance(value, self.dtype):
                raise TypeError(f"task: {self.name} invalid data type. Expected {self.dtype} not {type(value)}")
            else:
                self.updated = True
            self.timestamp = timestamp()
            logging.debug(f"task: {self.name} updated: {value} timestamp: {self.timestamp}")
        if isinstance(value, dict):
            for key, record in value.items():
                self[key] = record
        else:
            self._value = value

    def _build_rec_dict(self, naming_map, appendTo):
        if isinstance(self.value, dict):
            for key, record in self.value.items():
                record._build_rec_dict(naming_map, appendTo)
        else:
            super()._build_rec_dict(naming_map, appendTo)

    def senml_callback(self, record, **kwargs):
        """
        This is called after the record is updated from the senml pack.
        Sets updated flag to False, to avoid sending the same value back,
        and schedules on_write callback on the next run.
        """
        self.updated = False
        self.on_write_scheduled = True

    async def run(self):
        while True:
            if (self.on_read is not None):
                self.value = self.on_read(self.aiot)
            if (self.on_write is not None and self.on_write_scheduled):
                self.on_write_scheduled = False
                self.on_write(self.aiot, self.value if not isinstance(self.value, dict)
                        else {k: v.value for (k, v) in self.value.items()})
            await asyncio.sleep(self.interval)

class AIOTCloud():
    def __init__(self, device_id, ssl_params=None, server="mqtts-sa.iot.oniudra.cc", port=8883, keepalive=10):
        self.tasks = []
        self.records = {}
        self.thing_id = None
        self.keepalive = keepalive
        self.update_systime()
        self.last_ping = timestamp()
        self.device_topic = b"/a/d/" + device_id + b"/e/i"
        self.senmlpack = SenmlPack("urn:uuid:"+device_id.decode("utf-8"), self.senml_generic_callback)
        self.mqtt_client = MQTTClient(device_id, server, port, ssl_params, keepalive=keepalive, callback=self.mqtt_callback)
        # Note: this object is set by the cloud discovery protocol.
        self.register("thing_id", value=None, on_write=self.discovery_callback)

    def __getitem__(self, key):
        return self.records[key]

    def __setitem__(self, key, value):
        self.records[key].value = value

    def update_systime(self):
        try:
            from aiotcloud import ntptime
            ntptime.settime()
            logging.info("RTC time set from NTP.")
        except ImportError:
            pass
        except Exception as e:
            logging.error(f"Failed to set RTC time from NTP: {e}.")

    def create_new_task(self, coro, name=None):
        if hasattr(asyncio.Task, "get_name"):
            self.tasks.append(asyncio.create_task(coro, name=name))
        else:
            self.tasks.append(asyncio.create_task(coro))
        logging.debug(f"task: {name} created.")

    def register(self, name, value, interval=1.0, on_read=None, on_write=None):
        if value is None and on_read is not None:
            # Periodic task, and has an on_read function.
            value = on_read(self)
        elif value is None and "r:m" not in self.records:
            # This task initializes objects from the cloud.
            self.register("r:m", value="getLastValues")
        record = AIOTObject(self, name, value, on_read, on_write, interval)
        self.records[name] = record
        if (on_read is not None or on_write is not None):
            self.create_new_task(record.run(), name=record.name)

    def senml_generic_callback(self, record, **kwargs):
        """
        This callback catches all unknown/umatched records, and handles the initialization
        of composite types from the cloud. Cloud-initialized composite objects are handled
        in this callback because they have unknown sub-records.
        """
        name, subrec = record.name.split(":") if ":" in record.name else [record.name, ""]
        if rec := self.records.get(name, None):
            if rec.value is None or (subrec and subrec not in rec):
                rec[subrec] = None # This causes the right log message to be printed.
                rec[subrec] = record.value
                rec.updated = False
            else:
                logging.debug(f"Ignoring cloud initialization for record: {record.name}")
        else:
            logging.debug(f"Unkown record: {record.name} value: {record.value}")

    def discovery_callback(self, aiot, thing_id):
        logging.info(f"Device configured via discovery protocol.")
        if not thing_id:
            raise(Exception("Device is not linked to a Thing ID."))
        self.thing_id  = bytes(thing_id, "utf-8")
        self.topic_in  = b"/a/t/" + self.thing_id + b"/e/i"
        self.topic_out = b"/a/t/" + self.thing_id + b"/e/o"

        shadow_in = b"/a/t/" + self.thing_id + b"/shadow/i"
        shadow_out= b"/a/t/" + self.thing_id + b"/shadow/o"

        logging.info(f"Subscribing to thing topic {self.topic_in}.")
        self.mqtt_client.subscribe(self.topic_in)

        if lastval_record := self.records.pop("r:m", None):
            self.senmlpack.add(lastval_record)
            logging.info(f"Subscribing to shadow topic {shadow_in}.")
            self.mqtt_client.subscribe(shadow_in)
            self.mqtt_client.publish(shadow_out, self.senmlpack.to_cbor(), qos=True)

    def mqtt_callback(self, topic, message):
        logging.debug(f"mqtt topic: {topic[-8:]}... message: {message[:8]}...")
        self.senmlpack.clear()
        for key, record in self.records.items():
            if record.value is None or (record.on_write is not None and b"shadow" not in topic):
                if isinstance(record.value, dict):
                    self.senmlpack.add(record.value.values())
                else:
                    self.senmlpack.add(record)
        self.senmlpack.from_cbor(message)
        self.senmlpack.clear()

    async def mqtt_task(self, interval=0.100):
        while True:
            self.mqtt_client.check_msg()
            if self.thing_id is not None:
                self.senmlpack.clear()
                for key, record in self.records.items():
                    if (record.updated):
                        record.updated = False
                        self.senmlpack.add(record)
                if len(self.senmlpack._data):
                    logging.debug("Pushing records to AIoT Cloud:")
                    if (self.debug):
                        for record in self.senmlpack:
                            logging.debug(f"  ==> record: {record.name} value: {str(record.value)[:48]}...")
                    self.mqtt_client.publish(self.topic_out, self.senmlpack.to_cbor(), qos=True)
                elif (self.keepalive and (timestamp() - self.last_ping) > self.keepalive):
                    self.mqtt_client.ping()
                    self.last_ping = timestamp()
                    logging.debug("No records to push, sent a ping request.")
            await asyncio.sleep(interval)
 
    async def run(self, user_main=None, debug=False):
        self.debug = debug
        if (user_main is not None):
            # If user code is provided, append to tasks list.
            self.create_new_task(user_main, name="user code")

        logging.info("Connecting to AIoT cloud...")
        if not self.mqtt_client.connect():
            logging.error("Failed to connect AIoT cloud.")
            return

        logging.info("Subscribing to device topic.")
        self.mqtt_client.subscribe(self.device_topic)
        self.create_new_task(self.mqtt_task(), name="mqtt")

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
