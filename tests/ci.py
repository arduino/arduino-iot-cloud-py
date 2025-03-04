# This file is part of the Python Arduino IoT Cloud.
# Any copyright is dedicated to the Public Domain.
# https://creativecommons.org/publicdomain/zero/1.0/
import logging
import os
import time
import sys
import asyncio
from arduino_iot_cloud import ArduinoCloudClient
from arduino_iot_cloud import Task
from arduino_iot_cloud import CADATA # noqa
import argparse


def exception_handler(loop, context):
    pass


def on_value_changed(client, value):
    logging.info(f"The answer to life, the universe, and everything is {value}")
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handler)
    sys.exit(0)


def wdt_task(client, args, ts=[None]):
    if ts[0] is None:
        ts[0] = time.time()
    if time.time() - ts[0] > 20:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(exception_handler)
        logging.error("Timeout waiting for variable")
        sys.exit(1)


if __name__ == "__main__":
    # Parse command line args.
    parser = argparse.ArgumentParser(description="arduino_iot_cloud.py")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debugging messages"
    )
    parser.add_argument(
        "-b", "--basic-auth", action="store_true", help="Username and password auth",
    )
    parser.add_argument(
        "-c", "--crypto-device", action="store_true", help="Use soft-hsm/crypto device",
    )
    parser.add_argument(
        "-f", "--file-auth", action="store_true", help="Use key/cert files"
    )
    parser.add_argument(
        "-ca", "--ca-data", action="store_true", help="Use embedded CADATA"
    )
    parser.add_argument(
        "-s", "--sync", action="store_true", help="Run in synchronous mode"
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
    if args.basic_auth:
        client = ArduinoCloudClient(
            device_id=os.getenv("DEVICE_ID"),
            username=os.getenv("DEVICE_ID"),
            password=os.getenv("SECRET_KEY"),
            sync_mode=args.sync,
        )
    elif args.file_auth:
        import ssl
        fmt = "der" if sys.implementation.name == "micropython" else "pem"
        ca_key = "cadata" if args.ca_data else "cafile"
        ca_val = CADATA if args.ca_data else f"ca-root.{fmt}"
        client = ArduinoCloudClient(
            device_id=os.getenv("DEVICE_ID"),
            ssl_params={
                "keyfile": f"key.{fmt}",
                "certfile": f"cert.{fmt}",
                ca_key: ca_val,
                "cert_reqs": ssl.CERT_REQUIRED,
            },
            sync_mode=args.sync,
        )
    elif args.crypto_device:
        import ssl
        client = ArduinoCloudClient(
            device_id=os.getenv("DEVICE_ID"),
            ssl_params={
                "pin": "1234",
                "use_hsm": True,
                "keyfile": "pkcs11:token=arduino",
                "certfile": "pkcs11:token=arduino",
                "cafile": "ca-root.pem",
                "cert_reqs": ssl.CERT_REQUIRED,
                "engine_path": "/lib/x86_64-linux-gnu/engines-3/libpkcs11.so",
                "module_path": "/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
            },
            sync_mode=args.sync,
        )
    else:
        parser.print_help()
        sys.exit(1)

    # Register cloud objects.
    # When this object gets initialized from the cloud the test is complete.
    client.register("answer", value=None, on_write=on_value_changed)
    # This task will exist with failure after a timeout.
    client.register(Task("wdt_task", on_run=wdt_task, interval=1.0))

    # Start the Arduino IoT cloud client.
    client.start()
