# This file is part of the Python Arduino IoT Cloud.
# Any copyright is dedicated to the Public Domain.
# https://creativecommons.org/publicdomain/zero/1.0/
import time
import logging
from time import strftime
from arduino_iot_cloud import ArduinoCloudClient
from arduino_iot_cloud import Location
from arduino_iot_cloud import Schedule
from arduino_iot_cloud import ColoredLight
from arduino_iot_cloud import Task
from random import uniform
import argparse
import ssl # noqa

from secrets import DEVICE_ID
from secrets import SECRET_KEY  # noqa

KEY_PATH = "pkcs11:token=arduino"
CERT_PATH = "pkcs11:token=arduino"
CA_PATH = "ca-root.pem"


def on_switch_changed(client, value):
    # This is a write callback for the switch that toggles the LED variable. The LED
    # variable can be accessed via the client object passed in the first argument.
    client["led"] = value


def on_clight_changed(client, clight):
    logging.info(f"ColoredLight changed. Swi: {clight.swi} Bri: {clight.bri} Sat: {clight.sat} Hue: {clight.hue}")


def user_task(client, args):
    # NOTE: this function should not block.
    # This is a user-defined task that updates the colored light. Note any registered
    # cloud object can be accessed using the client object passed to this function.
    # The composite ColoredLight object fields can be assigned to individually, using dot:
    client["clight"].hue = round(uniform(0, 100), 1)
    client["clight"].bri = round(uniform(0, 100), 1)


if __name__ == "__main__":
    # Parse command line args.
    parser = argparse.ArgumentParser(description="arduino_iot_cloud.py")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debugging messages")
    parser.add_argument("-s", "--sync", action="store_true", help="Run in synchronous mode")
    args = parser.parse_args()

    # Assume the host has an active Internet connection.

    # Configure the logger.
    # All message equal or higher to the logger level are printed.
    # To see more debugging messages, pass --debug on the command line.
    logging.basicConfig(
        datefmt="%H:%M:%S",
        format="%(asctime)s.%(msecs)03d %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    # Create a client object to connect to the Arduino IoT cloud.
    # The most basic authentication method uses a username and password. The username is the device
    # ID, and the password is the secret key obtained from the IoT cloud when provisioning a device.
    client = ArduinoCloudClient(device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY, sync_mode=args.sync)

    # Alternatively, the client supports key and certificate-based authentication. To use this
    # mode, set "keyfile" and "certfile", and specify the CA certificate (if any) in "ssl_params".
    # Secure elements, which can be used to store the key and certificate, are also supported.
    # To use secure elements, provide the key and certificate URIs (in provider:token format) and
    # set the token's PIN (if applicable). For example:
    # client = ArduinoCloudClient(
    #     device_id=DEVICE_ID,
    #     ssl_params={
    #         "pin": "1234", "keyfile": KEY_PATH, "certfile": CERT_PATH, "cafile": CA_PATH,
    #         "verify_mode": ssl.CERT_REQUIRED, "server_hostname" : "iot.arduino.cc"
    #     },
    #     sync_mode=args.sync,
    # )

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

    # Start the Arduino IoT cloud client. In synchronous mode, this function returns immediately
    # after connecting to the cloud.
    client.start()

    # In sync mode, start returns after connecting, and the client must be polled periodically.
    while True:
        client.update()
        time.sleep(0.100)
