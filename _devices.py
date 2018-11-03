"""
This file is used by the Yombo core to create a device object for the specific zwave devices.
"""
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, CancelledError

from yombo.core.exceptions import YomboWarning
from yombo.lib.devices.camera import MjpegCamera, Image

from yombo.core.log import get_logger

logger = get_logger("modules.android_ipwebcam.device")

from . import const


class Android_IPCam(MjpegCamera):

    def _init_(self, **kwargs):
        self.SUB_PLATFORM = const.PLATFORM_ANDROID_IP_WEBCAM
        self.status_data = None
        self.sensor_data = None
        self._timeout = 5
        self._available = True

    def _init_(self, **kwargs):
        """
        Called by the Yombo framework to setup the device.
        :param kwargs:
        :return:
        """
        reactor.callLater(1, self.reload)  # Dont' hold up the system, spawn a child.

    @inlineCallbacks
    def _reload_(self, **kwargs):
        """
        Called by _init_ or when the device has been edited.

        :param kwargs:
        :return:
        """
        self._host = self.device_variables_cached["host"]["values"][0]
        self._port = self.device_variables_cached["port"]["values"][0]
        self._auth = None

        username = self.device_variables_cached["username"]["values"][0]
        password = self.device_variables_cached["password"]["values"][0]
        if username and password:
            self._auth = (username, password)
        yield self.update()

    @property
    def base_url(self):
        """ Get the base URL for the android ip webcam endpoint."""
        return f"http://{self._host}:{self._port}"

    @property
    def video_url(self):
        """ The video mjpeg url."""
        return f"{self.base_url}/video"

    @property
    def image_url(self):
        """ Single image (snapshot) url."""
        return f"{self.base_url}/shot.jpg"

    @property
    def available(self):
        """ Returns True if the camera is available. """
        return self._available

    @inlineCallbacks
    def camera_image(self):
        """
        Fetches a single image from the camera, and returns an Image instance.

        :return:
        """
        image_results = yield self._Requests.request("get", self.image_url, self._auth)
        return Image(content_type=image_results["headers"]["content-type"][0], iamge=image_results["content"])

    @inlineCallbacks
    def _request(self, path, **kwargs):
        """
        Make a request to the android ip webcam.
        """
        url = f"{self.base_url}{path}"
        data = None
        if "auth" not in kwargs:
            kwargs["auth"] = self._auth

        try:
                image_results = yield self._Requests.request("get", url, **kwargs)
                response = image_results["response"]
                if response.status == 200:
                    data = image_results["content"]

        except CancelledError as e:
            logger.error(f"Error communicating with IP Webcam: {e}")
            self._available = False
            return

        self._available = True
        if isinstance(data, str):
            return data.find("Ok") != -1
        else:
            return data

    @inlineCallbacks
    def update(self):
        """
        Get the Android IP Webcam status and update sensor data.
        """
        status_data = yield self._request("/status.json", params={"show_avail": 1})

        if status_data:
            self.status_data = status_data

            sensor_data = yield self._request("/sensors.json")
            if sensor_data:
                self.sensor_data = sensor_data

    @property
    def current_connections(self):
        """
        Returns a dictionary of the current conenction counts.
        :return:
        """
        if self._available is True and \
                isinstance(self.status_data, dict) and "video_connections" in self.status_data and \
                "audio_connections" in self.status_data:
            return {
                "video_connections": self.status_data["video_connections"],
                "audio_connections": self.status_data["video_connections"],
            }
        return {
            "video_connections": 0,
            "audio_connections": 0,
        }

    @property
    def current_settings(self):
        """
        Returns a dictionary of the current active settings.
        """
        settings = {}
        if not self.status_data:
            return settings

        for (key, val) in self.status_data.get("curvals", {}).items():
            try:
                val = float(val)
            except ValueError:
                val = val

            if val == "on" or val == "off":
                val = (val == "on")

            settings[key] = val

        return settings

    @property
    def available_settings(self):
        """
        Related to current_settings, but shows all currentl available settings. Returns a dictionary with all possible
        settings.
        """
        available = {}
        if not self.status_data:
            return available

        for (key, val) in self.status_data.get("avail", {}).items():
            available[key] = []
            for subval in val:
                try:
                    subval = float(subval)
                except ValueError:
                    subval = subval

                if subval == "on" or subval == "off":
                    subval = (subval == "on")

                available[key].append(subval)

        return available

    @property
    def enabled_sensors(self):
        """
        Returns a list of the enabled sensors.
        """
        if self.sensor_data is None:
            return []
        return list(self.sensor_data.keys())

    @property
    def enabled_settings(self):
        """
        Return a list of available settings.
        """
        if self.status_data is None:
            return []
        return list(self.status_data.get("curvals", {}).keys())

    def export_sensor(self, sensor):
        """Return (value, unit) from a sensor node."""
        value = None
        unit = None
        try:
            container = self.sensor_data.get(sensor)
            unit = container.get("unit")
            data_point = container.get("data", [[0, [0.0]]])
            if data_point and data_point[0]:
                value = data_point[0][-1][0]
        except (ValueError, KeyError, AttributeError):
            pass
        return value, unit

    @inlineCallbacks
    def change_setting(self, key, val):
        """
        Change a camera setting.
        """
        if isinstance(val, bool):
            payload = "on" if val else "off"
        else:
            payload = val
        results = yield self._request(f"/settings/{key}", params={"set": payload})
        return results

    @inlineCallbacks
    def record(self, record=True, tag=None):
        """
        Enable/disable recording. Set record to True or False, otherwise, recording will be toggled.
        """
        params = {"force": 1}
        path = "/startvideo" if record else "/stopvideo"
        if record and tag is not None:
            params[tag] = tag;

        results = yield self._request(path, params=params)
        return results

    @inlineCallbacks
    def set_focus(self, activate=True):
        """
        Enable/disable camera focus. Calling without a variable, toggles it.
        """
        path = "/focus" if activate else "/nofocus"
        results = yield self._request(path)
        return results

    @inlineCallbacks
    def set_front_facing_camera(self, activate=True):
        """
        Enable/disable the front-facing camera. Calling without activate set will simply toggle it.
        """
        results = yield self.change_setting("ffc", activate)
        return results

    @inlineCallbacks
    def set_gps_active(self, activate=True):
        """
        Enable/disable GPS. Calling without activate set will simply toggle it.
        """
        results = yield self.change_setting("gps_active", activate)
        return results

    @inlineCallbacks
    def set_light(self, activate=True):
        """
        Enable/disable the light (aka torch). Calling without a variable, toggles it.
        Return a coroutine.
        """
        path = "/enabletorch" if activate else "/disabletorch"
        results = yield self._request(path)
        return results

    @inlineCallbacks
    def set_overlay(self, activate=True):
        """
        Enable/disable the video overlay. Calling without activate set will simply toggle it.
        """
        results = yield self.change_setting("overlay", activate)
        return results

    @inlineCallbacks
    def set_quality(self, quality=100):
        """
        Set the video quality on scale of 1 to 100. Typically want somewhere between 50 and 75.
        """
        results = yield self.change_setting("quality", quality)
        return results

    @inlineCallbacks
    def set_night_vision(self, activate=True):
        """
        Enable/disable night vision. Calling without activate set will simply toggle it.
        """
        results = yield self.change_setting("night_vision", activate)
        return results

    @inlineCallbacks
    def set_orientation(self, orientation="landscape"):
        """
        Set the video orientation, defaults to "landscape".
        """
        if orientation not in const.ALLOWED_ORIENTATIONS:
            logger.debug("%s is not a valid orientation", orientation)
            return False
        results = yield self.change_setting("orientation", orientation)
        return results

    @inlineCallbacks
    def set_scenemode(self, scenemode="auto"):
        """
        Set the video scene mode.
        """
        if scenemode not in self.available_settings["scenemode"]:
            raise YomboWarning(f"{scenemode} is not a valid scenemode")

        results = yield self.change_setting("scenemode", scenemode)
        return results

    @inlineCallbacks
    def set_zoom(self, zoom):
        """
        Set the zoom level, between 0 and 100.
        """
        if isinstance(zoom, int) is False or zoom < 0 or zoom > 100:
            raise YomboWarning("Set zoom must be an int between 0 and 100.")
        results = yield self._request(f"/settings/ptz", params={"zoom": zoom})
        return results
