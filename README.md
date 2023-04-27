# Arduino IoT Cloud Python client ☁️🐍☁️
This is a Python client for the Arduino IoT cloud, which runs on both CPython and MicroPython. The client supports basic and advanced authentication methods, and provides a user-friendly API that allows the user to connect to the cloud, and create and link local objects to cloud objects with a just a few lines of code.

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
DEVICE_ID  = b"" # Provided by Arduino cloud when creating a device.
SECRET_KEY = b"" # Provided by Arduino cloud when creating a device.
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
MicroPython currently does Not support secure elements. The username and password can be used, or the key and cert files must be stored in DER format on the filesystem. To test the client on MicroPython, first convert the key and certificate to DER, using the following commands, then copy the files to the internal storage.

#### Convert key and certificate to `.DER`
```bash
openssl ec -in key.pem -out key.der -outform DER
openssl x509 -in cert.pem -out cert.der -outform DER
```

#### Run the MicroPython example script
* Set `KEY_PATH`, `CERT_PATH`, to key and certificate DER paths respectively.
* run `examples/micropython.py`

## Useful links

* [micropython-senml library](https://github.com/micropython/micropython-lib/tree/master/micropython/senml)
* [micropython-cbor2 library](https://github.com/micropython/micropython-lib/tree/master/python-ecosys/cbor2)
* [m2crypto](https://github.com/m2crypto/m2crypto)
* [umqtt.simple](https://github.com/micropython/micropython-lib/tree/master/micropython/umqtt.simple)
* [openssl docs/man](https://www.openssl.org/docs/man1.0.2/man3/)
