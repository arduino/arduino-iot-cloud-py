# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import time
import logging
from senml import SenmlPack
from senml import SenmlRecord
from arduino_iot_cloud.umqtt import MQTTClient

try:
    import asyncio
    from asyncio import CancelledError
    from asyncio import InvalidStateError
except ImportError:
    import uasyncio as asyncio
    from uasyncio.core import CancelledError

    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass

# Server/port for basic auth.
_DEFAULT_SERVER = "iot.arduino.cc"

# Default port for cert based auth and basic auth.
_DEFAULT_PORT = (8883, 8884)


class DoneException(Exception):
    pass


def timestamp():
    return int(time.time())


class ArduinoCloudObject(SenmlRecord):
    def __init__(self, name, **kwargs):
        self.on_read = kwargs.pop("on_read", None)
        self.on_write = kwargs.pop("on_write", None)
        self.interval = kwargs.pop("interval", 1.0)
        self._runnable = kwargs.pop("runnable", False)
        value = kwargs.pop("value", None)
        if keys := kwargs.pop("keys", {}):
            value = {   # Create a complex object (with sub-records).
                k: ArduinoCloudObject(f"{name}:{k}", value=v, callback=self.senml_callback)
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
                # This is a workaround for the cloud float/int conversion bug.
                if isinstance(self.value, float) and isinstance(value, int):
                    value = float(value)
                if not isinstance(self.value, type(value)):
                    raise TypeError(
                        f"{self.name} set to invalid data type, expected: {type(self.value)} got: {type(value)}"
                    )
            self._updated = True
            self.timestamp = timestamp()
            logging.debug(
                f"%s: {self.name} value: {value} ts: {self.timestamp}"
                % ("Init" if self.value is None else "Update")
            )
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


class ArduinoCloudClient:
    def __init__(
            self,
            device_id,
            username=None,
            password=None,
            ssl_params={},
            server=None,
            port=None,
            keepalive=10,
            ntp_server="pool.ntp.org",
            ntp_timeout=3
    ):
        self.tasks = {}
        self.records = {}
        self.thing_id = None
        self.keepalive = keepalive
        self.last_ping = timestamp()
        self.device_topic = b"/a/d/" + device_id + b"/e/i"
        self.senmlpack = SenmlPack("", self.senml_generic_callback)
        self.started = False

        # Update RTC from NTP server on MicroPython.
        self.update_systime(ntp_server, ntp_timeout)

        # MicroPython does not support secure elements yet, and key/cert
        # must be loaded from DER files and passed as binary blobs.
        if "keyfile" in ssl_params and "der" in ssl_params["keyfile"]:
            with open(ssl_params.pop("keyfile"), "rb") as f:
                ssl_params["key"] = f.read()
        if "certfile" in ssl_params and "der" in ssl_params["certfile"]:
            with open(ssl_params.pop("certfile"), "rb") as f:
                ssl_params["cert"] = f.read()

        if "ca_certs" in ssl_params and "der" in ssl_params["ca_certs"]:
            with open(ssl_params.pop("ca_certs"), "rb") as f:
                ssl_params["cadata"] = f.read()

        # If no server/port were passed in args, set the default server/port
        # based on authentication type.
        if server is None:
            server = _DEFAULT_SERVER
        if port is None:
            port = _DEFAULT_PORT[0] if password is None else _DEFAULT_PORT[1]

        # Create MQTT client.
        self.mqtt = MQTTClient(
                device_id, server, port, ssl_params, username, password, keepalive, self.mqtt_callback
        )

        # Add internal objects initialized by the cloud.
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

    def update_systime(self, server, timeout):
        try:
            import ntptime
            ntptime.host = server
            ntptime.timeout = timeout
            ntptime.settime()
            logging.info("RTC time set from NTP.")
        except ImportError:
            pass    # No ntptime module.
        except Exception as e:
            logging.error(f"Failed to set RTC time from NTP: {e}.")

    def create_task(self, name, coro, *args, **kwargs):
        if callable(coro):
            coro = coro(*args)
        if self.started:
            self.tasks[name] = asyncio.create_task(coro)
            logging.info(f"task: {name} created.")
        else:
            # Defer task creation until there's a running event loop.
            self.tasks[name] = coro

    def create_topic(self, topic, inout):
        return bytes(f"/a/t/{self.thing_id}/{topic}/{inout}", "utf-8")

    def register(self, aiotobj, coro=None, **kwargs):
        if isinstance(aiotobj, str):
            if kwargs.get("value", None) is None and kwargs.get("on_read", None) is not None:
                kwargs["value"] = kwargs.get("on_read")(self)
            aiotobj = ArduinoCloudObject(aiotobj, **kwargs)

        # Register the ArduinoCloudObject
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
            # If the object is uninitialized, updates are always allowed even if it's a read-only
            # object. Otherwise, for initialized objects, updates are only allowed if the object
            # is writable (on_write function is set) and the value is received from the out topic.
            if not record.initialized or (record.on_write is not None and b"shadow" not in topic):
                record.add_to_pack(self.senmlpack)
        self.senmlpack.from_cbor(message)
        self.senmlpack.clear()

    async def discovery_task(self, interval=0.100):
        self.mqtt.subscribe(self.device_topic, qos=1)
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
                    self.mqtt.subscribe(self.create_topic("shadow", "i"), qos=1)
                    self.mqtt.publish(self.create_topic("shadow", "o"), self.senmlpack.to_cbor(), qos=1)
                logging.info("Device configured via discovery protocol.")
            await asyncio.sleep(interval)
        raise DoneException()

    async def conn_task(self, interval=1.0, backoff=1.2):
        logging.info("Connecting to Arduino IoT cloud...")
        while True:
            try:
                self.mqtt.connect()
                break
            except Exception as e:
                logging.warning(f"Connection failed {e}, retrying after {interval}s")
                await asyncio.sleep(interval)
                interval = min(interval * backoff, 4.0)

        if self.thing_id is None:
            self.create_task("discovery", self.discovery_task)
        else:
            self.mqtt.subscribe(self.create_topic("e", "i"))
        self.create_task("mqtt_task", self.mqtt_task)
        raise DoneException()

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
                    self.mqtt.publish(self.topic_out, self.senmlpack.to_cbor(), qos=1)
                    self.last_ping = timestamp()
                elif self.keepalive and (timestamp() - self.last_ping) > self.keepalive:
                    self.mqtt.ping()
                    self.last_ping = timestamp()
                    logging.debug("No records to push, sent a ping request.")
            await asyncio.sleep(interval)
        raise DoneException()

    async def run(self):
        self.started = True
        # Creates tasks from coros here manually before calling
        # gather, so we can keep track of tasks in self.tasks dict.
        for name, coro in self.tasks.items():
            self.create_task(name, coro)

        # Create connection task.
        self.create_task("conn_task", self.conn_task)

        while True:
            task_except = None
            try:
                await asyncio.gather(*self.tasks.values(), return_exceptions=False)
                break   # All tasks are done, not likely.
            except Exception as e:
                task_except = e
                pass    # import traceback; traceback.print_exc()

            for name in list(self.tasks):
                task = self.tasks[name]
                try:
                    if task.done():
                        self.tasks.pop(name)
                        self.records.pop(name, None)
                        if isinstance(task_except, DoneException):
                            logging.error(f"task: {name} complete.")
                        elif task_except is not None:
                            logging.error(f"task: {name} raised exception: {str(task_except)}.")
                        if name == "mqtt_task":
                            self.create_task("conn_task", self.conn_task)
                        break   # Break after the first task is removed.
                except (CancelledError, InvalidStateError):
                    pass

    def start(self):
        asyncio.run(self.run())
