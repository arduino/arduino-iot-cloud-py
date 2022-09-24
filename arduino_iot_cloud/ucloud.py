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

import time
from kpn_senml import SenmlPack
from kpn_senml import SenmlRecord
from arduino_iot_cloud.umqtt import MQTTClient

try:
    import logging
    import asyncio
    from asyncio import CancelledError
    from asyncio import InvalidStateError
except ImportError:
    import ulogging as logging
    import uasyncio as asyncio
    from arduino_iot_cloud import ntptime
    from uasyncio.core import CancelledError

    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass


def timestamp():
    return int(time.time())


class AIOTObject(SenmlRecord):
    def __init__(self, name, **kwargs):
        self.on_read = kwargs.pop("on_read", None)
        self.on_write = kwargs.pop("on_write", None)
        self.interval = kwargs.pop("interval", 1.0)
        self._runnable = kwargs.pop("runnable", False)
        value = kwargs.pop("value", None)
        if keys := kwargs.pop("keys", {}):
            value = {   # Create a complex object (with sub-records).
                k: AIOTObject(f"{name}:{k}", value=v, callback=self.senml_callback)
                for (k, v) in {k: kwargs.pop(k, None) for k in keys}.items()
            }
        self._updated = False
        self.on_write_scheduled = False
        self.timestamp = timestamp()
        callback = kwargs.pop("callback", self.senml_callback)
        for key in kwargs:  # kwargs should be empty by now, unless a wrong attr was used.
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
            if self.value is not None:
                if not isinstance(self.value, type(value)):
                    raise TypeError(
                        f"record: {self.name} invalid data type. Expected {type(self.value)} not {type(value)}"
                    )
                self._updated = True
            self.timestamp = timestamp()
            if (self.value is None):
                logging.info(f"Init: {self.name} value: {value} ts: {self.timestamp}")
            else:
                logging.debug(f"Update: {self.name} value: {value} ts: {self.timestamp}")
        self._value = value

    def __getattr__(self, attr):
        if isinstance(self.__dict__.get("_value", None), dict) and attr in self._value:
            return self._value[attr].value
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{attr}'")

    def __setattr__(self, attr, value):
        if isinstance(self.__dict__.get("_value", None), dict) and attr in self._value:
            self._value[attr].value = value
        else:
            super().__setattr__(attr, value)

    def _build_rec_dict(self, naming_map, appendTo):
        # This function builds a dict of records from a pack, which gets converted to CBOR and
        # pushed to the cloud on the next update.
        if isinstance(self.value, dict):
            for r in self.value.values():
                r._build_rec_dict(naming_map, appendTo)
        else:
            super()._build_rec_dict(naming_map, appendTo)

    def add_to_pack(self, pack, push=False):
        # This function adds records that will be pushed to (or updated from) the cloud, to the SenML pack.
        # NOTE: When pushing records to the cloud (push==True) only fully initialized records are added to
        # the pack. And when updating records from the cloud (push==False), partially initialized records
        # are allowed in the pack, so they can be initialized from the cloud.
        # NOTE: all initialized sub-records are added to the pack whether they changed their state since the
        # last update or not, because the cloud currently does not support partial objects updates.
        if isinstance(self._value, dict):
            if not push or self.initialized:
                for r in self._value.values():
                    pack.add(r)
        elif not push or self._value is not None:
            pack.add(self)
        self.updated = False

    def senml_callback(self, record, **kwargs):
        # This function gets called after a record is updated from the cloud (from_cbor).
        # The updated flag is cleared to avoid sending the same value again to the cloud,
        # and the on_write function flag is set to so it gets called on the next run.
        self.updated = False
        self.on_write_scheduled = True

    async def run(self, client):
        while True:
            if self.on_read is not None:
                self.value = self.on_read(client)
            if self.on_write is not None and self.on_write_scheduled:
                self.on_write_scheduled = False
                self.on_write(client, self if isinstance(self.value, dict) else self.value)
            await asyncio.sleep(self.interval)


class AIOTClient:
    def __init__(
            self,
            device_id,
            username=None,
            password=None,
            ssl_params={},
            server="mqtts-sa.iot.oniudra.cc",
            port=8883,
            keepalive=10
    ):
        self.tasks = {}
        self.records = {}
        self.thing_id = None
        self.keepalive = keepalive
        self.update_systime()
        self.last_ping = timestamp()
        self.device_topic = b"/a/d/" + device_id + b"/e/i"
        self.senmlpack = SenmlPack("", self.senml_generic_callback)
        self.mqtt = MQTTClient(device_id, server, port, ssl_params, username, password, keepalive, self.mqtt_callback)
        # Note: the following internal objects are initialized by the cloud.
        for name in ["thing_id", "tz_offset", "tz_dst_until"]:
            self.register(name, value=None)

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
            ntptime.settime()
            logging.info("RTC time set from NTP.")
        except Exception as e:
            logging.error(f"Failed to set RTC time from NTP: {e}.")

    def create_task(self, name, coro, *args, **kwargs):
        self.tasks[name] = asyncio.create_task(coro(*args))
        logging.info(f"task: {name} created.")

    def create_topic(self, topic, inout):
        return bytes(f"/a/t/{self.thing_id}/{topic}/{inout}", "utf-8")

    def register(self, aiotobj, **kwargs):
        if isinstance(aiotobj, str):
            if kwargs.get("value", None) is None and kwargs.get("on_read", None) is not None:
                kwargs["value"] = kwargs.get("on_read")(self)
            aiotobj = AIOTObject(aiotobj, **kwargs)

        # Register the AIOTObject
        self.records[aiotobj.name] = aiotobj

        # Create a task for this object if it has any callbacks.
        if aiotobj.runnable:
            self.create_task(aiotobj.name, aiotobj.run, self)

        # Check if object needs to be initialized from the cloud.
        if not aiotobj.initialized and "r:m" not in self.records:
            self.register("r:m", value="getLastValues")

    def senml_generic_callback(self, record, **kwargs):
        # This callback catches all unknown/umatched sub/records that were not part of the pack.
        rname, sname = record.name.split(":") if ":" in record.name else [record.name, None]
        if rname in self.records:
            logging.info(f"Ignoring cloud initialization for record: {record.name}")
        else:
            logging.warning(f"Unkown record found: {record.name} value: {record.value}")

    def mqtt_callback(self, topic, message):
        logging.debug(f"mqtt topic: {topic[-8:]}... message: {message[:8]}...")
        self.senmlpack.clear()
        for record in self.records.values():
            if not record.initialized or (record.on_write is not None and b"shadow" not in topic):
                record.add_to_pack(self.senmlpack)
        self.senmlpack.from_cbor(message)
        self.senmlpack.clear()

    async def discovery_task(self, interval=0.100):
        while self.thing_id is None:
            self.mqtt.check_msg()
            if self.records.get("thing_id").value is not None:
                self.thing_id = self.records.pop("thing_id").value
                if not self.thing_id:  # Empty thing ID should not happen.
                    raise (Exception("Device is not linked to a Thing ID."))

                self.topic_out = self.create_topic("e", "o")
                self.mqtt.subscribe(self.create_topic("e", "i"))

                if lastval_record := self.records.pop("r:m", None):
                    lastval_record.add_to_pack(self.senmlpack)
                    self.mqtt.subscribe(self.create_topic("shadow", "i"))
                    self.mqtt.publish(self.create_topic("shadow", "o"), self.senmlpack.to_cbor(), qos=True)
                logging.info("Device configured via discovery protocol.")
            await asyncio.sleep(interval)

    async def mqtt_task(self, interval=0.100):
        while True:
            self.mqtt.check_msg()
            if self.thing_id is not None:
                self.senmlpack.clear()
                for record in self.records.values():
                    if record.updated:
                        record.add_to_pack(self.senmlpack, push=True)
                if len(self.senmlpack._data):
                    logging.debug("Pushing records to Arduino IoT cloud:")
                    for record in self.senmlpack._data:
                        logging.debug(f"  ==> record: {record.name} value: {str(record.value)[:48]}...")
                    self.mqtt.publish(self.topic_out, self.senmlpack.to_cbor(), qos=True)
                    self.last_ping = timestamp()
                elif self.keepalive and (timestamp() - self.last_ping) > self.keepalive:
                    self.mqtt.ping()
                    self.last_ping = timestamp()
                    logging.debug("No records to push, sent a ping request.")
            await asyncio.sleep(interval)

    async def run(self, user_main=None):
        logging.info("Connecting to Arduino IoT cloud...")
        if not self.mqtt.connect():
            logging.error("Failed to connect Arduino IoT cloud.")
            return

        self.mqtt.subscribe(self.device_topic)
        if user_main is not None:
            self.create_task("user_main", user_main, self)
        self.create_task("mqtt_task", self.mqtt_task)
        self.create_task("discovery", self.discovery_task)

        while True:
            try:
                await asyncio.gather(*self.tasks.values(), return_exceptions=False)
                logging.info("All tasks finished!")
                break
            except Exception as e:
                except_msg = str(e)
                pass  # import traceback; traceback.print_exc()

            for name in list(self.tasks):
                task = self.tasks[name]
                try:
                    if task.done():
                        self.tasks.pop(name)
                        self.records.pop(name, None)
                        logging.error(f"Removed task: {name}. Raised exception: {except_msg}.")
                except (CancelledError, InvalidStateError):
                    pass
