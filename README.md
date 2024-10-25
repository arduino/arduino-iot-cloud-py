# Arduino IoT Cloud Python client ☁️🐍☁️
This is a Python client for the Arduino IoT Cloud, which runs on both CPython and MicroPython. The client supports basic and advanced authentication methods, synchronous and asynchronous modes and provides a user-friendly API that allows users to connect to the cloud and create and link local objects to cloud objects with just a few lines of code.

## Minimal Example
The following basic example shows how to connect to the Arduino IoT cloud using basic username and password authentication, and control an LED from a dashboard's switch widget.
```python
from secrets import DEVICE_ID
from secrets import SECRET_KEY

# Switch callback, toggles the LED.
def on_switch_changed(client, value):
    # Note the client object passed to this function can be used to access
    # and modify any registered cloud object. The following line updates
    # the LED value.
    client["led"] = value

# 1. Create a client object, which is used to connect to the IoT cloud and link local
# objects to cloud objects. Note a username and password can be used for basic authentication
# on both CPython and MicroPython. For more advanced authentication methods, please see the examples.
client = ArduinoCloudClient(device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY)

# 2. Register cloud objects.
# Note: The following objects must be created first in the dashboard and linked to the device.
# When the switch is toggled from the dashboard, the on_switch_changed function is called with
# the client object and new value args.
client.register("sw1", value=None, on_write=on_switch_changed)

# The LED object is updated in the switch's on_write callback.
client.register("led", value=None)

# 3. Start the Arduino cloud client.
client.start()
```

Your `secrets.py` file should look like this:

```python
WIFI_SSID  = ""  # WiFi network SSID (for MicroPython)
WIFI_PASS  = ""  # WiFi network key  (for MicroPython)
DEVICE_ID  = "" # Provided by Arduino cloud when creating a device.
SECRET_KEY = "" # Provided by Arduino cloud when creating a device.
```

Note that by default, the client runs in asynchronous mode. In this mode, the client runs an asyncio loop that updates tasks and records, polls networking events, etc. The client also supports a synchronous mode, which requires periodic client polling. To run the client in synchronous mode, pass `sync_mode=True` when creating a client object and call `client.update()` periodically after connecting. For example:

```Python
# Run the client in synchronous mode.
client = ArduinoCloudClient(device_id=DEVICE_ID, ..., sync_mode=True)
....
client.register("led", value=None)
....
# In synchronous mode, this function returns immediately after connecting to the cloud.
client.start()

# Update the client periodically.
while True:
    client.update()
    time.sleep(0.100)
```

For more detailed examples and advanced API features, please see the [examples](https://github.com/arduino/arduino-iot-cloud-py/tree/main/examples).

## Testing on CPython/Linux
The client supports basic authentication using a username and password, and the more advanced key/cert pair stored on filesystem or in a crypto device. To test this functionality, the following steps can be used to emulate a crypto device (if one is not available) using SoftHSM on Linux.

#### Create softhsm token
Using the first available slot, in this case 0
```bash
softhsm2-util --init-token --slot 0 --label "arduino" --pin 1234 --so-pin 1234
```

#### Import the key and certificate using p11tool
```bash
p11tool --provider=/usr/lib/softhsm/libsofthsm2.so --login --set-pin=1234 --write "pkcs11:token=arduino" --load-privkey key.pem --label "Mykey"
p11tool --provider=/usr/lib/softhsm/libsofthsm2.so --login --set-pin=1234 --write "pkcs11:token=arduino" --load-certificate cert.pem --label "Mykey"
```

#### List objects
This should print the key and certificate
```bash
p11tool --provider=/usr/lib/softhsm/libsofthsm2.so --login --set-pin=1234 --list-all pkcs11:token=arduino

Object 0:
	URL: pkcs11:model=SoftHSM%20v2;manufacturer=SoftHSM%20project;serial=841b431f98150134;token=arduino;id=%67%A2%AD%13%53%B1%CE%4F%0E%CB%74%34%B8%C6%1C%F3%33%EA%67%31;object=mykey;type=private
	Type: Private key (EC/ECDSA)
	Label: mykey
	Flags: CKA_WRAP/UNWRAP; CKA_PRIVATE; CKA_SENSITIVE;
	ID: 67:a2:ad:13:53:b1:ce:4f:0e:cb:74:34:b8:c6:1c:f3:33:ea:67:31

Object 1:
	URL: pkcs11:model=SoftHSM%20v2;manufacturer=SoftHSM%20project;serial=841b431f98150134;token=arduino;id=%67%A2%AD%13%53%B1%CE%4F%0E%CB%74%34%B8%C6%1C%F3%33%EA%67%31;object=Mykey;type=cert
	Type: X.509 Certificate (EC/ECDSA-SECP256R1)
	Expires: Sat May 31 12:00:00 2053
	Label: Mykey
	ID: 67:a2:ad:13:53:b1:ce:4f:0e:cb:74:34:b8:c6:1c:f3:33:ea:67:31
```

#### Deleting Token:
When done with the token it can be deleted with the following command:
```bash
softhsm2-util --delete-token --token "arduino"
```

#### Run the example script
* Set `KEY_PATH`, `CERT_PATH` and `DEVICE_ID` in `examples/example.py`.
* Provide a CA certificate in a `ca-root.pem` file or set `CA_PATH` to `None` if it's not used.
* Override the default `pin` and provide `ENGINE_PATH` and `MODULE_PATH` in `ssl_params` if needed.
* Run the example:
```bash
python examples/example.py
```

## Testing on MicroPython
MicroPython supports both modes of authentication: basic mode, using a username and password, and mTLS with the key and certificate stored on the filesystem or a secure element (for provisioned boards). To use key and certificate files stored on the filesystem, they must first be converted to DER format. The following commands can be used to convert from PEM to DER:
```bash
openssl ec -in key.pem -out key.der -outform DER
openssl x509 -in cert.pem -out cert.der -outform DER
```

In this case `KEY_PATH`, `CERT_PATH`, can be set to the key and certificate DER paths, respectively:
```Python
KEY_PATH = "path/to/key.der"
CERT_PATH = "path/to/cert.der"
```

Alternatively, if the key and certificate are stored on the SE, their URIs can be specified in the following format:
```Python
KEY_PATH = "se05x:token=0x00000064"
CERT_PATH = "se05x:token=0x00000065"
```

With the key and certificate set, the example can be run with the following command `examples/micropython_advanced.py`

## Useful links

* [micropython-senml library](https://github.com/micropython/micropython-lib/tree/master/micropython/senml)
* [micropython-cbor2 library](https://github.com/micropython/micropython-lib/tree/master/python-ecosys/cbor2)
* [m2crypto](https://github.com/m2crypto/m2crypto)
* [umqtt.simple](https://github.com/micropython/micropython-lib/tree/master/micropython/umqtt.simple)
* [openssl docs/man](https://www.openssl.org/docs/man1.0.2/man3/)
