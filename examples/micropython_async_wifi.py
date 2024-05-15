# This file is part of the Python Arduino IoT Cloud.
# Any copyright is dedicated to the Public Domain.
# https://creativecommons.org/publicdomain/zero/1.0/

import time
import logging
from time import strftime
from machine import Pin

from secrets import DEVICE_ID
from secrets import SECRET_KEY

from arduino_iot_cloud import Task
from arduino_iot_cloud import ArduinoCloudClient
from arduino_iot_cloud import async_wifi_connection


def read_temperature(client):
    return 50.0


def read_humidity(client):
    return 100.0


def on_switch_changed(client, value):
    led = Pin("LED_BLUE", Pin.OUT)
    # Note the LED is usually inverted
    led.value(not value)
    # Update the value of the led cloud variable.
    client["led"] = value


if __name__ == "__main__":
    # Configure the logger.
    # All message equal or higher to the logger level are printed.
    # To see more debugging messages, set level=logging.DEBUG.
    logging.basicConfig(
        datefmt="%H:%M:%S",
        format="%(asctime)s.%(msecs)03d %(message)s",
        level=logging.INFO,
    )

    # Create a client object to connect to the Arduino IoT cloud.
    # The most basic authentication method uses a username and password. The username is the device
    # ID, and the password is the secret key obtained from the IoT cloud when provisioning a device.
    client = ArduinoCloudClient(
        device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY
    )

    # Register cloud objects.
    # Note: The following objects must be created first in the dashboard and linked to the device.
    # This cloud object is initialized with its last known value from the cloud. When this object is updated
    # from the dashboard, the on_switch_changed function is called with the client object and the new value.
    client.register("sw1", value=None, on_write=on_switch_changed, interval=0.250)

    # This cloud object is updated manually in the switch's on_write_change callback to update
    # the LED state in the cloud.
    client.register("led", value=None)

    # This is a periodic cloud object that gets updated at fixed intervals (in this case 1 seconed) with the
    # value returned from its on_read function (a formatted string of the current time). Note this object's
    # initial value is None, it will be initialized by calling the on_read function.
    client.register(
        "clk",
        value=None,
        on_read=lambda x: strftime("%H:%M:%S", time.localtime()),
        interval=1.0,
    )

    # Register some sensor readings.
    client.register("humidity", value=None, on_read=read_humidity, interval=1.0)
    client.register("temperature", value=None, on_read=read_temperature, interval=1.0)

    # This function is registered as a background task to reconnect to WiFi if it ever gets
    # disconnected. Note, it can also be used for the initial WiFi connection, in synchronous
    # mode, if it's called without any args (i.e, async_wifi_connection()) at the beginning of
    # this script.
    client.register(
        Task("wifi_connection", on_run=async_wifi_connection, interval=60.0)
    )

    # Start the Arduino IoT cloud client.
    client.start()
