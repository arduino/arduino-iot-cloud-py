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
    def __init__(self, name, **kwargs):
        self.on_read  = kwargs.pop("on_read", None)
        self.on_write = kwargs.pop("on_write", None)
        self.interval = kwargs.pop("interval", 1.0)
        self._runnable = kwargs.pop("runnable", False)
        value = kwargs.pop("value", None)
        if keys := kwargs.pop("keys", {}): # Create a complex object (with sub-records).
            mkrec = lambda k, v: AIOTObject(f"{name}:{k}", value=v, callback=self.senml_callback)
            value = {k : mkrec(k, v) for (k, v) in {k: kwargs.pop(k, None) for k in keys}.items()}
        self._updated = False
        self.on_write_scheduled = False
        self.timestamp = timestamp()
        self.dtype = type(value) # NOTE: must be set before calling super
        callback = kwargs.pop("callback", self.senml_callback)
        for key in kwargs:  # kwargs should be empty unless a wrong attr was used.
            raise TypeError(f"'{self.__class__.__name__}' got an unexpected keyword argument '{key}'")
        super().__init__(name, value=value, callback=callback)

    def __repr__(self):
        return f"{self.value}"

    def __contains__(self, key):
        return isinstance(self.value, dict) and key in self._value

    @property
    def updated(self):
        if isinstance(self.value, dict):
            return any(r._updated for r in self.value.values())
        return self._updated

    @updated.setter
    def updated(self, value):
        if isinstance(self.value, dict):
            for r in self.value.values():
                r._updated = value
        self._updated = value

    @property
    def initialized(self):
        if isinstance(self.value, dict):
            return all(r.initialized for r in self.value.values())
        return self.value is not None

    @property
    def runnable(self):
        return self.on_read is not None or self.on_write is not None or self._runnable

    @SenmlRecord.value.setter
    def value(self, value):
        if value is not None:
            if self.dtype is type(None):
                self.dtype = type(value)
            elif not isinstance(value, self.dtype):
                raise TypeError(f"task: {self.name} invalid data type. Expected {self.dtype} not {type(value)}")
            else:
                self._updated = True
            self.timestamp = timestamp()
            logging.debug(f"task: {self.name} %s: {value} ts: {self.timestamp}"
                    %("initialized" if self.value is None else "updated"))
        self._value = value

    def __getattr__(self, attr):
        if isinstance(super().__dict__.get("_value", None), dict) and attr in super().value:
            return super().value[attr].value
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{attr}'")

    def __setattr__(self, name, value):
        if isinstance(super().__dict__.get("_value", None), dict) and name in super().value:
            self.value[name].value = value
        else:
            super().__setattr__(name, value)

    def _build_rec_dict(self, naming_map, appendTo):
        if isinstance(self.value, dict):
            for r in self.value.values():
                if r.value is not None: # NOTE: should filter by updated when it's supported.
                    r._build_rec_dict(naming_map, appendTo)
        else:
            super()._build_rec_dict(naming_map, appendTo)

    def add_to_pack(self, pack):
        if isinstance(self.value, dict):
            for r in self.value.values():
                # NOTE: If record value is None it can still be added to the pack for initialization.
                pack.add(r) # NOTE: should filter by updated when it's supported.
        else:
            pack.add(self)
        self.updated = False

    def senml_callback(self, record, **kwargs):
        """
        This is called after the record is updated from the senml pack.
        Sets updated flag to False, to avoid sending the same value back,
        and schedules on_write callback on the next run.
        """
        self.updated = False
        self.on_write_scheduled = True

    async def run(self, aiot):
        while True:
            if (self.on_read is not None):
                self.value = self.on_read(aiot)
            if (self.on_write is not None and self.on_write_scheduled):
                self.on_write_scheduled = False
                self.on_write(aiot, self if isinstance(self.value, dict) else self.value)
            await asyncio.sleep(self.interval)

class AIOTClient():
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
        # Note: the following objects are initialized by the cloud.
        self.register("thing_id", value=None, on_write=self.discovery_callback)
        self.register("tz_offset", value=None)

    def __getitem__(self, key):
        if isinstance(self.records[key].value, dict):
            return self.records[key]
        return self.records[key].value

    def __setitem__(self, key, value):
        self.records[key].value = value

    def __contains__(self, key):
        return key in self.records

    def get(self, key, default=None):
        if key in self and self[key] is not None:
            return self[key]
        return default

    def update_systime(self):
        try:
            from aiotcloud import ntptime
            ntptime.settime()
            logging.info("RTC time set from NTP.")
        except ImportError:
            pass
        except Exception as e:
            logging.error(f"Failed to set RTC time from NTP: {e}.")

    def create_new_task(self, coro, *args, name=None):
        if hasattr(asyncio.Task, "get_name"):
            self.tasks.append(asyncio.create_task(coro(*args), name=name))
        else:
            self.tasks.append(asyncio.create_task(coro(*args)))
        logging.debug(f"task: {name} created.")

    def register(self, aiotobj, **kwargs):
        if isinstance(aiotobj, str):
            if kwargs.get("value", None) is None and kwargs.get("on_read", None) is not None:
                kwargs["value"] = kwargs.get("on_read")(self)
            aiotobj = AIOTObject(aiotobj, **kwargs)

        # Register the AIOTObject
        self.records[aiotobj.name] = aiotobj

        # Create a task for this object if it has any callbacks.
        if aiotobj.runnable:
            self.create_new_task(aiotobj.run, self, name=aiotobj.name)

        # Check if object needs to be initialized from the cloud.
        if not aiotobj.initialized and "r:m" not in self.records:
            self.register("r:m", value="getLastValues")

    def senml_generic_callback(self, record, **kwargs):
        """
        This callback catches all unknown/umatched records.
        """
        rname, sname = record.name.split(":") if ":" in record.name else [record.name, ""]
        if rname in self.records:
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
        logging.info(f"Subscribing to thing topic {self.topic_in}.")
        self.mqtt_client.subscribe(self.topic_in)

        if lastval_record := self.records.pop("r:m", None):
            shadow_in = b"/a/t/" + self.thing_id + b"/shadow/i"
            shadow_out= b"/a/t/" + self.thing_id + b"/shadow/o"
            lastval_record.add_to_pack(self.senmlpack)
            logging.info(f"Subscribing to shadow topic {shadow_in}.")
            self.mqtt_client.subscribe(shadow_in)
            self.mqtt_client.publish(shadow_out, self.senmlpack.to_cbor(), qos=True)

    def mqtt_callback(self, topic, message):
        logging.debug(f"mqtt topic: {topic[-8:]}... message: {message[:8]}...")
        self.senmlpack.clear()
        for record in self.records.values():
            if not record.initialized or (record.on_write is not None and b"shadow" not in topic):
                record.add_to_pack(self.senmlpack)
        self.senmlpack.from_cbor(message)
        self.senmlpack.clear()

    async def mqtt_task(self, interval=0.100):
        while True:
            self.mqtt_client.check_msg()
            if self.thing_id is not None:
                self.senmlpack.clear()
                for record in self.records.values():
                    if (record.updated):
                        record.add_to_pack(self.senmlpack)
                if len(self.senmlpack._data):
                    logging.debug("Pushing records to AIoT Cloud:")
                    if (self.debug):
                        for record in self.senmlpack:
                            logging.debug(f"  ==> record: {record.name} value: {str(record.value)[:48]}...")
                    self.mqtt_client.publish(self.topic_out, self.senmlpack.to_cbor(), qos=True)
                    self.last_ping = timestamp()
                elif (self.keepalive and (timestamp() - self.last_ping) > self.keepalive):
                    self.mqtt_client.ping()
                    self.last_ping = timestamp()
                    logging.debug("No records to push, sent a ping request.")
            await asyncio.sleep(interval)
 
    async def run(self, user_main=None, debug=False):
        self.debug = debug
        if (user_main is not None):
            # If user code is provided, append to tasks list.
            self.create_new_task(user_main, self, name="user code")

        logging.info("Connecting to AIoT cloud...")
        if not self.mqtt_client.connect():
            logging.error("Failed to connect AIoT cloud.")
            return

        logging.info("Subscribing to device topic.")
        self.mqtt_client.subscribe(self.device_topic)
        self.create_new_task(self.mqtt_task, name="mqtt")

        while True:
            try:
                await asyncio.gather(*self.tasks, return_exceptions=False)
                logging.info("All tasks finished!")
                break
            except Exception as e:
                pass #import traceback; traceback.print_exc()

            for task in self.tasks:
                try:
                    if task.done():
                        self.tasks.remove(task)
                    if hasattr(asyncio.Task, "get_name"):
                        logging.error(f"Removed task: {task.get_name()}. Raised exception: {task.exception()}.")
                    else:
                        logging.error(f"Removed task.")
                except (CancelledError, InvalidStateError) as e: pass
