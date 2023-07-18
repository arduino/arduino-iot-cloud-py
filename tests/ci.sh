#!/bin/bash

ci_configure_softhsm() {
TOKEN_DIR=${HOME}/softhsm/tokens/
TOKEN_URI="pkcs11:token=arduino"
PROVIDER=/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so

mkdir -p ${TOKEN_DIR}
cat > ${TOKEN_DIR}/softhsm2.conf << EOF
directories.tokendir = ${TOKEN_DIR}
objectstore.backend = file

# ERROR, WARNING, INFO, DEBUG
log.level = ERROR

# If CKF_REMOVABLE_DEVICE flag should be set
slots.removable = false

# Enable and disable PKCS#11 mechanisms using slots.mechanisms.
slots.mechanisms = ALL

# If the library should reset the state on fork
library.reset_on_fork = false
EOF

export SOFTHSM2_CONF=${TOKEN_DIR}/softhsm2.conf

echo "$KEY_PEM" >> key.pem
echo "$CERT_PEM" >> cert.pem
echo "$CA_PEM" >> ca-root.pem

softhsm2-util --init-token --slot 0 --label "arduino" --pin 1234 --so-pin 1234
p11tool --provider=${PROVIDER} --login --set-pin=1234 --write ${TOKEN_URI} --load-privkey key.pem --label "mykey"
p11tool --provider=${PROVIDER} --login --set-pin=1234 --write ${TOKEN_URI} --load-certificate cert.pem --label "mycert"
}
