# Python AIoT Cloud ☁️🐍☁️
AIoT cloud implementation for Python and MicroPython.

## Testing on Linux
If a crypto device is available, the following steps can be skipped, otherwise AIoT cloud can be tested on Linux using SoftHSM.

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

### Run the example script
* Set `KEY_URI`, `CERT_URI`, `DEVICE_ID`, `THING_ID` in `aiotcloud_example.py`.
* Provide a CA certificate in a `ca-root.pem` file or set `CA_PATH` to `None` if it's not used.
* Override the default `pin` and provide `ENGINE_PATH` and `MODULE_PATH` in `ssl_params` if needed.
* Clone this repository and run the following:
```bash
python aiotcloud_example.py
```

## Testing on MicroPython
The following changes to the example code are required, because MicroPython does Not support secure elements yet:

#### Convert key and certificate to `.DER`
```bash
openssl ec -in key.pem -out key.der -outform DER
openssl x509 -in cert.pem -out cert.der -outform DER
```

#### Load key and certificate from filesystem storage
```python
KEY_PATH  = "key.der"
CERT_PATH = "cert.der"
....

async def main():
    with open(KEY_PATH, "rb") as fin: key = fin.read()
    with open(CERT_PATH, "rb") as fin: cert = fin.read()
    aiot = AIOTCloud(device_id=DEVICE_ID, keepalive=10, ssl_params = {"key":key, "cert":cert})
    ....
```

## Useful links

* [ulogging](https://github.com/iabdalkader/micropython-ulogging)
* [senml-micropython](https://github.com/kpn-iot/senml-micropython-library)
* [m2crypto](https://github.com/m2crypto/m2crypto)
* [umqtt.simple](https://github.com/micropython/micropython-lib/tree/master/micropython/umqtt.simple)
* [openssl docs/man](https://www.openssl.org/docs/man1.0.2/man3/)
