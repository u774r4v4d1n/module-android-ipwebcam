"""
Brings images from Android IP Webcam into Yombo. This allows image capture and video streaming.

:copyright: 2018 Yombo
:license: YRPL
"""
from twisted.internet import reactor

from . import const

from yombo.core.module import YomboModule
from yombo.core.log import get_logger

logger = get_logger("modules.android_ipwebcam")


class Android_IP_WebCam(YomboModule):
    """
    Brings images from Android IP Webcam into Yombo. This allows image capture and video streaming.
    """
    def _init_(self, **kwargs):
        """
        Setups all Android IP Cameras
        """
        pass
