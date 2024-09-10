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
import binascii

pkcs11 = None

# Default engine and provider.
_ENGINE_PATH = "/usr/lib/engines-3/libpkcs11.so"
_MODULE_PATH = "/usr/lib/softhsm/libsofthsm2.so"

# Reference EC key for NXP's PlugNTrust
_EC_REF_KEY = binascii.unhexlify(
    b"3041020100301306072a8648ce3d020106082a8648ce3d03010704273025"
    b"0201010420100000000000000000000000000000000000ffffffffa5a6b5"
    b"b6a5a6b5b61000"
)


def wrap_socket(sock, ssl_params={}):
    keyfile = ssl_params.get("keyfile", None)
    certfile = ssl_params.get("certfile", None)
    cafile = ssl_params.get("cafile", None)
    cadata = ssl_params.get("cadata", None)
    ciphers = ssl_params.get("ciphers", None)
    verify = ssl_params.get("verify_mode", ssl.CERT_NONE)
    hostname = ssl_params.get("server_hostname", None)
    micropython = sys.implementation.name == "micropython"

    if keyfile is not None and "token" in keyfile and micropython:
        # Create a reference EC key for NXP EdgeLock device.
        objid = int(keyfile.split("=")[1], 16).to_bytes(4, "big")
        keyfile = _EC_REF_KEY[0:53] + objid + _EC_REF_KEY[57:]
        # Load the certificate from the secure element (when supported).
        # import cryptoki
        # with cryptoki.open() as token:
        #     cert = token.read(0x65, 412)

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
