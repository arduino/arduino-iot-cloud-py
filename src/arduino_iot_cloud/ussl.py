# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# SSL module with m2crypto backend for HSM support.

import sys
import ssl

pkcs11 = None

# Default engine and provider.
_ENGINE_PATH = "/usr/lib/engines-3/libpkcs11.so"
_MODULE_PATH = "/usr/lib/softhsm/libsofthsm2.so"


def wrap_socket(
    sock,
    ssl_params={},
):
    if any(k not in ssl_params for k in ("keyfile", "certfile", "pin")):
        # Use Micro/CPython's SSL
        if sys.implementation.name == "micropython":
            # Load key, cert and CA from DER files, and pass them as binary blobs.
            mpargs = {"keyfile": "key", "certfile": "cert", "ca_certs": "cadata"}
            for k, v in mpargs.items():
                if k in ssl_params and "der" in ssl_params[k]:
                    with open(ssl_params.pop(k), "rb") as f:
                        ssl_params[v] = f.read()
        return ssl.wrap_socket(sock, **ssl_params)

    # Use M2Crypto to load key and cert from HSM.
    from M2Crypto import m2, SSL, Engine

    global pkcs11
    if pkcs11 is None:
        pkcs11 = Engine.load_dynamic_engine(
            "pkcs11", ssl_params.get("engine_path", _ENGINE_PATH)
        )
        pkcs11.ctrl_cmd_string(
            "MODULE_PATH", ssl_params.get("module_path", _MODULE_PATH)
        )
        pkcs11.ctrl_cmd_string("PIN", ssl_params["pin"])
        pkcs11.init()

    # Create and configure SSL context
    ctx = SSL.Context("tls")
    ctx.set_default_verify_paths()
    ctx.set_allow_unknown_ca(False)

    ciphers = ssl_params.get("ciphers", None)
    if ciphers is not None:
        ctx.set_cipher_list(ciphers)

    ca_certs = ssl_params.get("ca_certs", None)
    if ca_certs is not None:
        if ctx.load_verify_locations(ca_certs) != 1:
            raise Exception("Failed to load CA certs")

    cert_reqs = ssl_params.get("cert_reqs", ssl.CERT_NONE)
    if cert_reqs == ssl.CERT_NONE:
        cert_reqs = SSL.verify_none
    else:
        cert_reqs = SSL.verify_peer
    ctx.set_verify(cert_reqs, depth=9)

    # Set key/cert
    key = pkcs11.load_private_key(ssl_params["keyfile"])
    m2.ssl_ctx_use_pkey_privkey(ctx.ctx, key.pkey)

    cert = pkcs11.load_certificate(ssl_params["certfile"])
    m2.ssl_ctx_use_x509(ctx.ctx, cert.x509)

    SSL.Connection.postConnectionCheck = None
    return SSL.Connection(ctx, sock=sock)
