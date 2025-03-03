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
    b"8230d0018230760103a0010202026f149eadf52bd56f9ab6063ce49803304605"
    b"07f1305a060a2a0848863dce030430023145300b060955030604021353551731"
    b"153003060455130a410e647269756f6e4c20434c55203153300b060955030b04"
    b"0213544910310e300306045513034107647269756f6e20300d17353231303031"
    b"303133353232185a320f3530303530313133353032335a3245300b3109300306"
    b"04551306550231533017061555030a040e13724175646e69206f4c4c20435355"
    b"0b31093003060455130b490231543010060e550303040713724175646e69306f"
    b"305906132a0748863dce01020806862ace48033d070142030400e1a16c535235"
    b"331ae80dac2b125b8fc137503eb39b64eea00227c7355a8d4510cad052f597ec"
    b"9af281ffe2c69779d33fc639a1d76bcc8561f670ae3b1d62c87142a340300f30"
    b"03061d550113ff0105040330010130ff060e55030f1d010104ff030401023006"
    b"061d55030e1d160414046542842904d0d18803c609f478b33be328123ee00a30"
    b"0806862ace48043d02034803300002450021a4cf60cb5eff5389fdab54c55dff"
    b"c0731f6af17b356829ee19d43273c65e505520022d6f742fd9dac866a539a415"
    b"f612f28123ee92d55b5bfb11d7ecec3f86c5a767"
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
