# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# SSL module with m2crypto backend for HSM support.

import ssl
import sys
import logging
try:
    from micropython import const
except (ImportError, AttributeError):
    def const(x):
        return x

pkcs11 = None
se_dev = None

# Default engine and provider.
_ENGINE_PATH = "/usr/lib/engines-3/libpkcs11.so"
_MODULE_PATH = "/usr/lib/softhsm/libsofthsm2.so"

# Reference EC key for the SE.
_EC_REF_KEY = const(
    b"\x30\x41\x02\x01\x00\x30\x13\x06\x07\x2A\x86\x48\xCE\x3D\x02\x01"
    b"\x06\x08\x2A\x86\x48\xCE\x3D\x03\x01\x07\x04\x27\x30\x25\x02\x01"
    b"\x01\x04\x20\xA5\xA6\xB5\xB6\xA5\xA6\xB5\xB6\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF"
    b"\xFF\xFF\xFF"
)


def log_level_enabled(level):
    return logging.getLogger().isEnabledFor(level)


def ecdsa_sign_callback(key, data):
    if log_level_enabled(logging.DEBUG):
        key_hex = "".join("%02X" % b for b in key)
        logging.debug(f"ecdsa_sign_callback key:{key_hex}")

    if key[0:8] != b"\xA5\xA6\xB5\xB6\xA5\xA6\xB5\xB6":
        if log_level_enabled(logging.DEBUG):
            logging.debug("ecdsa_sign_callback falling back to default sign")
        return None

    obj_id = int.from_bytes(key[-4:], "big")
    if log_level_enabled(logging.DEBUG):
        logging.debug(f"ecdsa_sign_callback oid: 0x{obj_id:02X}")

    # Sign data on SE using reference key object id.
    sig = se_dev.sign(obj_id, data)
    if log_level_enabled(logging.DEBUG):
        sig_hex = "".join("%02X" % b for b in sig)
        logging.debug(f"ecdsa_sign_callback sig: {sig_hex}")
    logging.info("Signed using secure element")
    return sig


def wrap_socket(sock, ssl_params={}):
    keyfile = ssl_params.get("keyfile", None)
    certfile = ssl_params.get("certfile", None)
    cafile = ssl_params.get("cafile", None)
    cadata = ssl_params.get("cadata", None)
    ciphers = ssl_params.get("ciphers", None)
    verify = ssl_params.get("verify_mode", ssl.CERT_NONE)
    hostname = ssl_params.get("server_hostname", None)

    se_key_token = keyfile is not None and "token" in keyfile
    se_crt_token = certfile is not None and "token" in certfile
    sys_micropython = sys.implementation.name == "micropython"

    if sys_micropython and (se_key_token or se_crt_token):
        import se05x

        # Create and initialize SE05x device.
        global se_dev
        if se_dev is None:
            se_dev = se05x.SE05X()

        if se_key_token:
            # Create a reference key for the secure element.
            obj_id = int(keyfile.split("=")[1], 16)
            keyfile = _EC_REF_KEY[0:-4] + obj_id.to_bytes(4, "big")

        if se_crt_token:
            # Load the certificate from the secure element.
            certfile = se_dev.read(0x65, 412)

    if keyfile is None or "token" not in keyfile:
        # Use MicroPython/CPython SSL to wrap socket.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if hasattr(ctx, "set_default_verify_paths"):
            ctx.set_default_verify_paths()
        if hasattr(ctx, "check_hostname") and verify != ssl.CERT_REQUIRED:
            ctx.check_hostname = False
        ctx.verify_mode = verify
        if keyfile is not None and certfile is not None:
            ctx.load_cert_chain(certfile, keyfile)
        if ciphers is not None:
            ctx.set_ciphers(ciphers)
        if cafile is not None or cadata is not None:
            ctx.load_verify_locations(cafile=cafile, cadata=cadata)
        if sys_micropython and se_key_token:
            # Set alternate ECDSA sign function.
            ctx._context.ecdsa_sign_callback = ecdsa_sign_callback
        return ctx.wrap_socket(sock, server_hostname=hostname)
    else:
        # Use M2Crypto to load key and cert from HSM.
        try:
            from M2Crypto import m2, SSL, Engine
        except (ImportError, AttributeError):
            logging.error("The m2crypto module is required to use HSM.")
            sys.exit(1)

        global pkcs11
        if pkcs11 is None:
            pkcs11 = Engine.load_dynamic_engine(
                "pkcs11", ssl_params.get("engine_path", _ENGINE_PATH)
            )
            pkcs11.ctrl_cmd_string(
                "MODULE_PATH", ssl_params.get("module_path", _MODULE_PATH)
            )
            if "pin" in ssl_params:
                pkcs11.ctrl_cmd_string("PIN", ssl_params["pin"])
            pkcs11.init()

        # Create and configure SSL context
        ctx = SSL.Context("tls")
        ctx.set_default_verify_paths()
        ctx.set_allow_unknown_ca(False)
        if verify == ssl.CERT_NONE:
            ctx.set_verify(SSL.verify_none, depth=9)
        else:
            ctx.set_verify(SSL.verify_peer | SSL.verify_fail_if_no_peer_cert, depth=9)
        if cafile is not None:
            if ctx.load_verify_locations(cafile) != 1:
                raise Exception("Failed to load CA certs")
        if ciphers is not None:
            ctx.set_cipher_list(ciphers)

        key = pkcs11.load_private_key(keyfile)
        m2.ssl_ctx_use_pkey_privkey(ctx.ctx, key.pkey)

        cert = pkcs11.load_certificate(certfile)
        m2.ssl_ctx_use_x509(ctx.ctx, cert.x509)

        sslobj = SSL.Connection(ctx, sock=sock)
        if verify == ssl.CERT_NONE:
            sslobj.clientPostConnectionCheck = None
        elif hostname is not None:
            sslobj.set1_host(hostname)
        return sslobj
