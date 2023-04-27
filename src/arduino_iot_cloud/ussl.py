# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# SSL module with m2crypto backend for HSM support.

from M2Crypto import Engine, m2, SSL

CERT_NONE = SSL.verify_none
CERT_REQUIRED = SSL.verify_peer

_key = None
_cert = None

# Default engine and provider.
_ENGINE_PATH = "/usr/lib/engines-3/libpkcs11.so"
_MODULE_PATH = "/usr/lib/softhsm/libsofthsm2.so"


def init(pin, certfile, keyfile, engine_path, module_path):
    global _key, _cert
    Engine.load_dynamic_engine("pkcs11", engine_path)
    pkcs11 = Engine.Engine("pkcs11")
    pkcs11.ctrl_cmd_string("MODULE_PATH", module_path)
    pkcs11.ctrl_cmd_string("PIN", pin)
    pkcs11.init()
    _key = pkcs11.load_private_key(keyfile)
    _cert = pkcs11.load_certificate(certfile)


def wrap_socket(
    sock_in,
    pin=None,
    certfile=None,
    keyfile=None,
    ca_certs=None,
    cert_reqs=CERT_NONE,
    ciphers=None,
    engine_path=_ENGINE_PATH,
    module_path=_MODULE_PATH,
):
    if certfile is None or keyfile is None:
        # Fallback to Python's SSL
        import ssl
        return ssl.wrap_socket(sock_in)

    if _key is None or _cert is None:
        init(pin, certfile, keyfile, engine_path, module_path)

    # Create SSL context
    ctx = SSL.Context("tls")
    ctx.set_default_verify_paths()
    ctx.set_allow_unknown_ca(False)

    if ciphers is not None:
        ctx.set_cipher_list(ciphers)

    if ca_certs is not None and cert_reqs is not CERT_NONE:
        if ctx.load_verify_locations(ca_certs) != 1:
            raise Exception("Failed to load CA certs")
        ctx.set_verify(SSL.verify_peer, depth=9)

    # Set key/cert
    m2.ssl_ctx_use_x509(ctx.ctx, _cert.x509)
    m2.ssl_ctx_use_pkey_privkey(ctx.ctx, _key.pkey)
    SSL.Connection.postConnectionCheck = None
    return SSL.Connection(ctx, sock=sock_in)
