# python-aiotcloud
AIoT cloud implementation in Python

## Testing with SoftHSM and p11tool:

### Create softhsm token (use first available slot, in this case 0)
```bash
softhsm2-util --init-token --slot 0 --label "arduino" --pin 1234 --so-pin 1234
```

### Import the key and certificate using p11tool:
```bash
p11tool --provider=/usr/lib/softhsm/libsofthsm2.so --login --set-pin=1234 --write "pkcs11:token=arduino" --load-privkey key.pem --label "Mykey"
p11tool --provider=/usr/lib/softhsm/libsofthsm2.so --login --set-pin=1234 --write "pkcs11:token=arduino" --load-certificate cert.pem --label "Mykey"
```

### List objects (should see the key and certificate):
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

### Run example:
```bash
python umqtt_example.py
```
Note: you need to override `ENGINE_PATH` and `MODULE_PATH` and provide `ca-root.pem` or set `CA_PATH` to `None`, in `umqtt_example.py`

### Delete Token:

```bash
softhsm2-util --delete-token --token "arduino"
```

### Useful links:

* [m2crypto](https://github.com/m2crypto/m2crypto)
* [umqtt.simple](https://github.com/micropython/micropython-lib/tree/master/micropython/umqtt.simple)
* [openssl docs/man](https://www.openssl.org/docs/man1.0.2/man3/)
