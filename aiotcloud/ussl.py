# The MIT License (MIT)
#
# Copyright (c) 2022 Arduino SA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ussl module with m2crypto backend for HSM support. 
from M2Crypto import Engine, m2, BIO, SSL

_key = None
_cert = None

# Default engine and provider.
ENGINE_PATH = "/usr/lib/engines-1.1/libpkcs11.so"
MODULE_PATH = "/usr/lib/softhsm/libsofthsm2.so"

def init(pin, certfile, keyfile, engine_path, module_path):
    global _key, _cert
    Engine.load_dynamic_engine("pkcs11", engine_path)
    pkcs11 = Engine.Engine("pkcs11")
    pkcs11.ctrl_cmd_string("MODULE_PATH", module_path)
    pkcs11.ctrl_cmd_string("PIN", pin)
    pkcs11.init()
    _key = pkcs11.load_private_key(keyfile)
    _cert = pkcs11.load_certificate(certfile)

def wrap_socket(sock_in, pin, certfile, keyfile, ca_certs=None, ciphers=None, engine_path=ENGINE_PATH, module_path=MODULE_PATH):
    if _key is None or _cert is None:
        init(pin, certfile, keyfile, engine_path, module_path)

    # Create SSL context
    ctx = SSL.Context('tls')
    ctx.set_default_verify_paths()
    ctx.set_allow_unknown_ca(False)

    if ciphers is not None:
        ctx.set_cipher_list(ciphers)

    if ca_certs is not None:
        if ctx.load_verify_locations(ca_certs) != 1:
            raise Exception('Failed to load CA certs')
        ctx.set_verify(SSL.verify_peer, depth=9)

    # Set key/cert
    m2.ssl_ctx_use_x509(ctx.ctx, _cert.x509)
    m2.ssl_ctx_use_pkey_privkey(ctx.ctx, _key.pkey)
    SSL.Connection.postConnectionCheck = None
    return SSL.Connection(ctx, sock=sock_in)
