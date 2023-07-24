# This file is part of the Python Arduino IoT Cloud.
# Any copyright is dedicated to the Public Domain.
# https://creativecommons.org/publicdomain/zero/1.0/
import logging
import os
import sys
import asyncio
from arduino_iot_cloud import ArduinoCloudClient
import argparse


def exception_handler(loop, context):
    pass


def on_value_changed(client, value):
    logging.info(f"The answer to life, the universe, and everything is {value}")
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handler)
    sys.exit(0)


if __name__ == "__main__":
    # Parse command line args.
    parser = argparse.ArgumentParser(description="arduino_iot_cloud.py")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debugging messages"
    )
    parser.add_argument(
        "-c", "--crypto-device", action="store_true", help="Use crypto device"
    )
    args = parser.parse_args()

    # Configure the logger.
    # All message equal or higher to the logger level are printed.
    # To see more debugging messages, pass --debug on the command line.
    logging.basicConfig(
        datefmt="%H:%M:%S",
        format="%(asctime)s.%(msecs)03d %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    # Create a client object to connect to the Arduino IoT cloud.
    # To use a secure element, set the token's "pin" and URI in "keyfile" and "certfile", and
    # the CA certificate (if any) in "ssl_params". Alternatively, a username and password can
    # be used to authenticate, for example:
    #   client = ArduinoCloudClient(device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY)
    if args.crypto_device:
        import arduino_iot_cloud.ussl as ssl
        client = ArduinoCloudClient(
            device_id=os.getenv("DEVICE_ID"),
            ssl_params={
                "pin": "1234",
                "keyfile": "pkcs11:token=arduino",
                "certfile": "pkcs11:token=arduino",
                "ca_certs": "ca-root.pem",
                "cert_reqs": ssl.CERT_REQUIRED,
                "engine_path": "/lib/x86_64-linux-gnu/engines-3/libpkcs11.so",
                "module_path": "/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
            },
        )
    else:
        client = ArduinoCloudClient(
            device_id=os.getenv("DEVICE_ID"),
            username=os.getenv("DEVICE_ID"),
            password=os.getenv("SECRET_KEY"),
        )

    # Register cloud objects.
    # Note: The following objects must be created first in the dashboard and linked to the device.
    # This cloud object is initialized with its last known value from the cloud. When this object is updated
    # from the dashboard, the on_switch_changed function is called with the client object and the new value.
    client.register("answer", value=None, on_write=on_value_changed)

    # Start the Arduino IoT cloud client.
    client.start()
