#!/bin/bash

ci_install_micropython() {
	CACHE_DIR=${HOME}/cache/bin
	mkdir -p ${CACHE_DIR}

	sudo apt-get install gcc-arm-none-eabi libnewlib-arm-none-eabi

	git clone --depth=1 https://github.com/micropython/micropython.git

	cat > micropython/ports/unix/manifest.py <<-EOF
	include("\$(PORT_DIR)/variants/standard/manifest.py")
	require("bundle-networking")
	require("time")
	require("senml")
	require("logging")
	EOF

    echo "#undef MICROPY_PY_SELECT_SELECT" >> micropython/ports/unix/variants/mpconfigvariant_common.h
    echo "#undef MICROPY_PY_SELECT_POSIX_OPTIMISATIONS" >> micropython/ports/unix/variants/mpconfigvariant_common.h

	make -j12 -C micropython/mpy-cross/
	make -j12 -C micropython/ports/unix/ submodules
	make -j12 -C micropython/ports/unix/ FROZEN_MANIFEST=manifest.py CFLAGS_EXTRA="-DMICROPY_PY_SELECT=1"
	cp micropython/ports/unix/build-standard/micropython ${CACHE_DIR}
}

ci_configure_softhsm() {
	TOKEN_DIR=${HOME}/softhsm/tokens/
	TOKEN_URI="pkcs11:token=arduino"
	PROVIDER=/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so

	mkdir -p ${TOKEN_DIR}
	cat > ${TOKEN_DIR}/softhsm2.conf <<-EOF
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

    # Convert to DER for MicroPython.
    openssl ec -in key.pem -out key.der -outform DER
    openssl x509 -in cert.pem -out cert.der -outform DER
    openssl x509 -in ca-root.pem -out ca-root.der -outform DER
}
