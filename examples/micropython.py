# This file is part of the Python Arduino IoT Cloud.
# Any copyright is dedicated to the Public Domain.
# https://creativecommons.org/publicdomain/zero/1.0/
import time
import ussl
import network
import logging
from time import strftime
from arduino_iot_cloud import ArduinoCloudClient
from arduino_iot_cloud import Location
from arduino_iot_cloud import Schedule
from arduino_iot_cloud import ColoredLight
from arduino_iot_cloud import Task
from arduino_iot_cloud import CADATA
from random import uniform
from secrets import WIFI_SSID
from secrets import WIFI_PASS
from secrets import DEVICE_ID
from secrets import SECRET_KEY  # noqa

KEY_PATH = "key.der"
CERT_PATH = "cert.der"


def on_switch_changed(client, value):
    # This is a write callback for the switch that toggles the LED variable. The LED
    # variable can be accessed via the client object passed in the first argument.
    client["led"] = value


def on_clight_changed(client, clight):
    logging.info(f"ColoredLight changed. Swi: {clight.swi} Bri: {clight.bri} Sat: {clight.sat} Hue: {clight.hue}")


def user_task(client):
    # NOTE: this function should not block.
    # This is a user-defined task that updates the colored light. Note any registered
    # cloud object can be accessed using the client object passed to this function.
    # The composite ColoredLight object fields can be assigned to individually, using dot:
    client["clight"].hue = round(uniform(0, 100), 1)
    client["clight"].bri = round(uniform(0, 100), 1)


def wifi_connect():
    if not WIFI_SSID or not WIFI_PASS:
        raise (Exception("Network is not configured. Set SSID and passwords in secrets.py"))
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        logging.info("Trying to connect. Note this may take a while...")
        time.sleep_ms(500)
    logging.info(f"WiFi Connected {wlan.ifconfig()}")


if __name__ == "__main__":
    # Configure the logger.
    # All message equal or higher to the logger level are printed.
    # To see more debugging messages, set level=logging.DEBUG.
    logging.basicConfig(
        datefmt="%H:%M:%S",
        format="%(asctime)s.%(msecs)03d %(message)s",
        level=logging.INFO,
    )

    # NOTE: Add networking code here or in boot.py
    wifi_connect()

    # Create a client object to connect to the Arduino IoT cloud.
    # For MicroPython, the key and cert files must be stored in DER format on the filesystem.
    # Alternatively, a username and password can be used to authenticate:
    #   client = ArduinoCloudClient(device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY)
    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        ssl_params={
            "keyfile": KEY_PATH, "certfile": CERT_PATH, "cadata": CADATA, "cert_reqs": ussl.CERT_REQUIRED
        }
    )

    # Register cloud objects.
    # Note: The following objects must be created first in the dashboard and linked to the device.
    # This cloud object is initialized with its last known value from the cloud. When this object is updated
    # from the dashboard, the on_switch_changed function is called with the client object and the new value.
    client.register("sw1", value=None, on_write=on_switch_changed, interval=0.250)

    # This cloud object is updated manually in the switch's on_write_change callback.
    client.register("led", value=None)

    # This is a periodic cloud object that gets updated at fixed intervals (in this case 1 seconed) with the
    # value returned from its on_read function (a formatted string of the current time). Note this object's
    # initial value is None, it will be initialized by calling the on_read function.
    client.register("clk", value=None, on_read=lambda x: strftime("%H:%M:%S", time.localtime()), interval=1.0)

    # This is an example of a composite cloud object (a cloud object with multiple variables). In this case
    # a colored light with switch, hue, saturation and brightness attributes. Once initialized, the object's
    # attributes can be accessed using dot notation. For example: client["clight"].swi = False.
    client.register(ColoredLight("clight", swi=True, on_write=on_clight_changed))

    # This is another example of a composite cloud object, a map location with lat and long attributes.
    client.register(Location("treasureisland", lat=31.264694, lon=29.979987))

    # This object allows scheduling recurring events from the cloud UI. On activation of the event, if the
    # on_active callback is provided, it gets called with the client object and the schedule object value.
    # Note: The activation status of the object can also be polled using client["schedule"].active.
    client.register(Schedule("schedule", on_active=lambda client, value: logging.info(f"Schedule activated {value}!")))

    # The client can also schedule user code in a task and run it along with the other cloud objects.
    # To schedule a user function, use the Task object and pass the task name and function in "on_run"
    # to client.register().
    client.register(Task("user_task", on_run=user_task, interval=1.0))

    # Start the Arduino IoT cloud client.
    client.start()
