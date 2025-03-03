# This file is part of the Arduino IoT Cloud Python client.
# Copyright (c) 2022 Arduino SA
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import binascii
from .ucloud import ArduinoCloudClient  # noqa
from .ucloud import ArduinoCloudObject
from .ucloud import ArduinoCloudObject as Task  # noqa
from .ucloud import timestamp


CADATA = binascii.unhexlify(
    b"308201d030820176a00302010202146fad9e2bf56fd5b69a3c0698e43003"
    b"0546f1075a300a06082a8648ce3d0403023045310b300906035504061302"
    b"555331173015060355040a130e41726475696e6f204c4c43205553310b30"
    b"09060355040b130249543110300e0603550403130741726475696e6f3020"
    b"170d3235303131303130353332325a180f32303535303130333130353332"
    b"325a3045310b300906035504061302555331173015060355040a130e4172"
    b"6475696e6f204c4c43205553310b3009060355040b130249543110300e06"
    b"03550403130741726475696e6f3059301306072a8648ce3d020106082a86"
    b"48ce3d03010703420004a1e1536c35521a330de82bac5b12c18f5037b33e"
    b"649ba0ee270235c78d5a1045d0caf552ec97f29aff81c6e279973fd339c6"
    b"d7a1cc6b618570f63bae621d71c8a3423040300f0603551d130101ff0405"
    b"30030101ff300e0603551d0f0101ff040403020106301d0603551d0e0416"
    b"041442652984d00488d1c603f409b378e33b1228e03e300a06082a8648ce"
    b"3d0403020348003045022100cfa4cb60ff5e8953abfdc554ff5d73c06a1f"
    b"7bf16835ee29d41973325ec6555002206f2d2f74dad966c839a515a412f6"
    b"81f2ee23d5925b5b11fbecd73fecc58667a7"
)


class Location(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"lat", "lon"}, **kwargs)


class Color(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"hue", "sat", "bri"}, **kwargs)


class ColoredLight(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "hue", "sat", "bri"}, **kwargs)


class DimmedLight(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        super().__init__(name, keys={"swi", "bri"}, **kwargs)


class Schedule(ArduinoCloudObject):
    def __init__(self, name, **kwargs):
        kwargs.update({("on_run", self.on_run)})
        self.on_active = kwargs.pop("on_active", None)
        # Uncomment to allow the schedule to change in runtime.
        # kwargs["on_write"] = kwargs.get("on_write", lambda aiot, value: None)
        self.active = False
        super().__init__(name, keys={"frm", "to", "len", "msk"}, **kwargs)

    def on_run(self, aiot, args=None):
        if self.initialized:
            ts = timestamp() + aiot.get("tz_offset", 0)
            if ts > self.frm and ts < (self.frm + self.len):
                if not self.active and self.on_active is not None:
                    self.on_active(aiot, self.value)
                self.active = True
            else:
                self.active = False


class Television(ArduinoCloudObject):
    PLAYBACK_FASTFORWARD = 0
    PLAYBACK_NEXT = 1
    PLAYBACK_PAUSE = 2
    PLAYBACK_PLAY = 3
    PLAYBACK_PREVIOUS = 4
    PLAYBACK_REWIND = 5
    PLAYBACK_STARTOVER = 6
    PLAYBACK_STOP = 7
    PLAYBACK_NONE = 255
    INPUT_AUX1 = 0
    INPUT_AUX2 = 1
    INPUT_AUX3 = 2
    INPUT_AUX4 = 3
    INPUT_AUX5 = 4
    INPUT_AUX6 = 5
    INPUT_AUX7 = 6
    INPUT_BLUERAY = 7
    INPUT_CABLE = 8
    INPUT_CD = 9
    INPUT_COAX1 = 10
    INPUT_COAX2 = 11
    INPUT_COMPOSITE1 = 12
    INPUT_DVD = 13
    INPUT_GAME = 14
    INPUT_HDRADIO = 15
    INPUT_HDMI1 = 16
    INPUT_HDMI2 = 17
    INPUT_HDMI3 = 18
    INPUT_HDMI4 = 19
    INPUT_HDMI5 = 20
    INPUT_HDMI6 = 21
    INPUT_HDMI7 = 22
    INPUT_HDMI8 = 23
    INPUT_HDMI9 = 24
    INPUT_HDMI10 = 25
    INPUT_HDMIARC = 26
    INPUT_INPUT1 = 27
    INPUT_INPUT2 = 28
    INPUT_INPUT3 = 29
    INPUT_INPUT4 = 30
    INPUT_INPUT5 = 31
    INPUT_INPUT6 = 32
    INPUT_INPUT7 = 33
    INPUT_INPUT8 = 34
    INPUT_INPUT9 = 35
    INPUT_INPUT10 = 36
    INPUT_IPOD = 37
    INPUT_LINE1 = 38
    INPUT_LINE2 = 39
    INPUT_LINE3 = 40
    INPUT_LINE4 = 41
    INPUT_LINE5 = 42
    INPUT_LINE6 = 43
    INPUT_LINE7 = 44
    INPUT_MEDIAPLAYER = 45
    INPUT_OPTICAL1 = 46
    INPUT_OPTICAL2 = 47
    INPUT_PHONO = 48
    INPUT_PLAYSTATION = 49
    INPUT_PLAYSTATION3 = 50
    INPUT_PLAYSTATION4 = 51
    INPUT_SATELLITE = 52
    INPUT_SMARTCAST = 53
    INPUT_TUNER = 54
    INPUT_TV = 55
    INPUT_USBDAC = 56
    INPUT_VIDEO1 = 57
    INPUT_VIDEO2 = 58
    INPUT_VIDEO3 = 59
    INPUT_XBOX = 60

    def __init__(self, name, **kwargs):
        super().__init__(
            name, keys={"swi", "vol", "mut", "pbc", "inp", "cha"}, **kwargs
        )


def async_wifi_connection(client=None, args=None, connecting=[False]):
    import time
    import network
    import logging

    try:
        from secrets import WIFI_SSID
        from secrets import WIFI_PASS
    except Exception:
        raise (
            Exception("Network is not configured. Set SSID and passwords in secrets.py")
        )

    wlan = network.WLAN(network.STA_IF)

    if wlan.isconnected():
        if connecting[0]:
            connecting[0] = False
            logging.info(f"WiFi connected {wlan.ifconfig()}")
            if client is not None:
                client.update_systime()
    elif connecting[0]:
        logging.info("WiFi is down. Trying to reconnect.")
    else:
        wlan.active(True)
        wlan.connect(WIFI_SSID, WIFI_PASS)
        connecting[0] = True
        logging.info("WiFi is down. Trying to reconnect.")

    # Running in sync mode, block until WiFi is connected.
    if client is None:
        while not wlan.isconnected():
            logging.info("Trying to connect to WiFi.")
            time.sleep(1.0)
        connecting[0] = False
        logging.info(f"WiFi Connected {wlan.ifconfig()}")
