# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import time
import logging
import cbor2
from senml import SenmlPack
from senml import SenmlRecord
from arduino_iot_cloud.umqtt import MQTTClient
import asyncio
from asyncio import CancelledError
try:
    from asyncio import InvalidStateError
except (ImportError, AttributeError):
    # MicroPython doesn't have this exception
    class InvalidStateError(Exception):
        pass
try:
    from arduino_iot_cloud._version import __version__
except (ImportError, AttributeError):
    __version__ = "1.3.3"

# Server/port for basic auth.
_DEFAULT_SERVER = "iot.arduino.cc"

# Default port for cert based auth and basic auth.
_DEFAULT_PORT = (8883, 8884)


class DoneException(Exception):
    pass


def timestamp():
    return int(time.time())


def timestamp_ms():
    return time.time_ns() // 1000000


def log_level_enabled(level):
    return logging.getLogger().isEnabledFor(level)


class ArduinoCloudObject(SenmlRecord):
    def __init__(self, name, **kwargs):
        self.on_read = kwargs.pop("on_read", None)
        self.on_write = kwargs.pop("on_write", None)
        self.on_run = kwargs.pop("on_run", None)
        self.interval = kwargs.pop("interval", 1.0)
        self.backoff = kwargs.pop("backoff", None)
        self.args = kwargs.pop("args", None)
        value = kwargs.pop("value", None)
        if keys := kwargs.pop("keys", {}):
            value = {   # Create a complex object (with sub-records).
                k: ArduinoCloudObject(f"{name}:{k}", value=v, callback=self.senml_callback)
                for (k, v) in {k: kwargs.pop(k, None) for k in keys}.items()
            }
        self._updated = False
        self.on_write_scheduled = False
        self.timestamp = timestamp()
        self.last_poll = timestamp_ms()
        self.runnable = any((self.on_run, self.on_read, self.on_write))
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
            if log_level_enabled(logging.DEBUG):
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
            self.run_sync(client)
            await asyncio.sleep(self.interval)
            if self.backoff is not None:
                self.interval = min(self.interval * self.backoff, 5.0)

    def run_sync(self, client):
        if self.on_run is not None:
            self.on_run(client, self.args)
        if self.on_read is not None:
            self.value = self.on_read(client)
        if self.on_write is not None and self.on_write_scheduled:
            self.on_write_scheduled = False
            self.on_write(client, self if isinstance(self.value, dict) else self.value)


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
            ntp_timeout=3,
            sync_mode=False
    ):
        self.tasks = {}
        self.records = {}
        self.thing_id = None
        self.keepalive = keepalive
        self.last_ping = timestamp()
        self.senmlpack = SenmlPack("", self.senml_generic_callback)
        self.ntp_server = ntp_server
        self.ntp_timeout = ntp_timeout
        self.async_mode = not sync_mode
        self.connected = False

        # Convert args to bytes if they are passed as strings.
        if isinstance(device_id, str):
            device_id = bytes(device_id, "utf-8")
        if username is not None and isinstance(username, str):
            username = bytes(username, "utf-8")
        if password is not None and isinstance(password, str):
            password = bytes(password, "utf-8")

        self.device_topic = b"/a/d/" + device_id + b"/e/i"
        self.command_topic = b"/a/d/" + device_id + b"/c/up"

        # Update RTC from NTP server on MicroPython.
        self.update_systime()

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

    def update_systime(self, server=None, timeout=None):
        try:
            import ntptime
            ntptime.host = self.ntp_server if server is None else server
            ntptime.timeout = self.ntp_timeout if timeout is None else timeout
            ntptime.settime()
            logging.info("RTC time set from NTP.")
        except ImportError:
            pass    # No ntptime module.
        except Exception as e:
            if log_level_enabled(logging.ERROR):
                logging.error(f"Failed to set RTC time from NTP: {e}.")

    def create_task(self, name, coro, *args, **kwargs):
        if callable(coro):
            coro = coro(*args)
        try:
            asyncio.get_event_loop()
            self.tasks[name] = asyncio.create_task(coro)
            if log_level_enabled(logging.INFO):
                logging.info(f"task: {name} created.")
        except Exception:
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

        # Check if object needs to be initialized from the cloud.
        if not aiotobj.initialized and "r:m" not in self.records:
            self.register("r:m", value="getLastValues")

        # Create a task for this object if it has any callbacks.
        if self.async_mode and aiotobj.runnable:
            self.create_task(aiotobj.name, aiotobj.run, self)

    def senml_generic_callback(self, record, **kwargs):
        # This callback catches all unknown/umatched sub/records that were not part of the pack.
        rname, sname = record.name.split(":") if ":" in record.name else [record.name, None]
        if rname in self.records:
            if log_level_enabled(logging.INFO):
                logging.info(f"Ignoring cloud initialization for record: {record.name}")
        else:
            if log_level_enabled(logging.WARNING):
                logging.warning(f"Unkown record found: {record.name} value: {record.value}")

    def mqtt_callback(self, topic, message):
        if log_level_enabled(logging.DEBUG):
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

    def ts_expired(self, ts, last_ts_ms, interval_s):
        return last_ts_ms == 0 or (ts - last_ts_ms) > int(interval_s * 1000)

    def poll_records(self):
        ts = timestamp_ms()
        try:
            for record in self.records.values():
                if record.runnable and self.ts_expired(ts, record.last_poll, record.interval):
                    record.run_sync(self)
                    record.last_poll = ts
        except Exception as e:
            self.records.pop(record.name)
            if log_level_enabled(logging.ERROR):
                logging.error(f"task: {record.name} raised exception: {str(e)}.")

    def poll_connect(self, aiot=None, args=None):
        logging.info("Connecting to Arduino IoT cloud...")
        try:
            self.mqtt.connect()
        except Exception as e:
            if log_level_enabled(logging.WARNING):
                logging.warning(f"Connection failed {e}, retrying...")
            return

        if self.thing_id is None:
            self.mqtt.subscribe(self.device_topic, qos=1)
        else:
            self.mqtt.subscribe(self.create_topic("e", "i"))

        if self.async_mode:
            if self.thing_id is None:
                self.register("discovery", on_run=self.poll_discovery, interval=0.500)
            self.register("mqtt_task", on_run=self.poll_mqtt, interval=1.0)
            raise DoneException()
        self.connected = True

    def poll_discovery(self, aiot=None, args=None):
        self.mqtt.check_msg()
        if self.records.get("thing_id").value is not None:
            self.thing_id = self.records.pop("thing_id").value
            if not self.thing_id:  # Empty thing ID should not happen.
                raise Exception("Device is not linked to a Thing ID.")

            self.topic_out = self.create_topic("e", "o")
            self.mqtt.subscribe(self.create_topic("e", "i"))

            if lastval_record := self.records.pop("r:m", None):
                lastval_record.add_to_pack(self.senmlpack)
                self.mqtt.subscribe(self.create_topic("shadow", "i"), qos=1)
                self.mqtt.publish(self.create_topic("shadow", "o"), self.senmlpack.to_cbor(), qos=1)

            if hasattr(cbor2, "dumps"):
                # Push library version and mode.
                libv = "%s-%s" % (__version__, "async" if self.async_mode else "sync")
                # Note we have to add the tag manually because python-ecosys's cbor2 doesn't suppor CBORTags.
                self.mqtt.publish(self.command_topic, b"\xda\x00\x01\x07\x00" + cbor2.dumps([libv]), qos=1)
            logging.info("Device configured via discovery protocol.")
            if self.async_mode:
                raise DoneException()

    def poll_mqtt(self, aiot=None, args=None):
        self.mqtt.check_msg()
        if self.thing_id is not None:
            self.senmlpack.clear()
            for record in self.records.values():
                if record.updated:
                    record.add_to_pack(self.senmlpack, push=True)
            if len(self.senmlpack._data):
                logging.debug("Pushing records to Arduino IoT cloud:")
                if log_level_enabled(logging.DEBUG):
                    for record in self.senmlpack._data:
                        logging.debug(f"  ==> record: {record.name} value: {str(record.value)[:48]}...")
                self.mqtt.publish(self.topic_out, self.senmlpack.to_cbor(), qos=1)
                self.last_ping = timestamp()
            elif self.keepalive and (timestamp() - self.last_ping) > self.keepalive:
                self.mqtt.ping()
                self.last_ping = timestamp()
                logging.debug("No records to push, sent a ping request.")

    async def run(self, interval, backoff):
        # Creates tasks from coros here manually before calling
        # gather, so we can keep track of tasks in self.tasks dict.
        for name, coro in self.tasks.items():
            self.create_task(name, coro)

        # Create connection task.
        self.register("connection_task", on_run=self.poll_connect, interval=interval, backoff=backoff)

        while True:
            task_except = None
            try:
                await asyncio.gather(*self.tasks.values(), return_exceptions=False)
                break   # All tasks are done, not likely.
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                task_except = e
                pass    # import traceback; traceback.print_exc()

            for name in list(self.tasks):
                task = self.tasks[name]
                try:
                    if task.done():
                        self.tasks.pop(name)
                        self.records.pop(name, None)
                        if isinstance(task_except, DoneException) and log_level_enabled(logging.INFO):
                            logging.info(f"task: {name} complete.")
                        elif task_except is not None and log_level_enabled(logging.ERROR):
                            logging.error(f"task: {name} raised exception: {str(task_except)}.")
                        if name == "mqtt_task":
                            self.register(
                                "connection_task",
                                on_run=self.poll_connect,
                                interval=interval,
                                backoff=backoff
                            )
                        break   # Break after the first task is removed.
                except (CancelledError, InvalidStateError):
                    pass

    def start(self, interval=1.0, backoff=1.2):
        if self.async_mode:
            asyncio.run(self.run(interval, backoff))
            return

        last_conn_ms = 0
        last_disc_ms = 0

        while True:
            ts = timestamp_ms()
            if not self.connected and self.ts_expired(ts, last_conn_ms, interval):
                self.poll_connect()
                if last_conn_ms != 0:
                    interval = min(interval * backoff, 5.0)
                last_conn_ms = ts

            if self.connected and self.thing_id is None and self.ts_expired(ts, last_disc_ms, 0.250):
                self.poll_discovery()
                last_disc_ms = ts

            if self.connected and self.thing_id is not None:
                break
            self.poll_records()

    def update(self):
        if self.async_mode:
            raise RuntimeError("This function can't be called in asyncio mode.")

        if not self.connected:
            try:
                self.start()
            except Exception as e:
                raise e

        self.poll_records()

        try:
            self.poll_mqtt()
        except Exception as e:
            self.connected = False
            if log_level_enabled(logging.WARNING):
                logging.warning(f"Connection lost {e}")
