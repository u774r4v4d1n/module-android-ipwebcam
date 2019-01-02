"""
This file is used by the Yombo core to create a device object for the specific zwave devices.
"""
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, CancelledError

from yombo.constants.features import FEATURE_DURATION
from yombo.constants.status_extra import STATUS_EXTRA_DURATION
from yombo.core.exceptions import YomboWarning
from yombo.core.log import get_logger
from yombo.lib.devices.camera import VideoCamera, Image
from yombo.utils.ffmpeg.sensor import SensorNoise, SensorMotion

from . import const

logger = get_logger("modules.android_ipwebcam.device")


class Android_IPWebCam(VideoCamera):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SUB_PLATFORM = const.PLATFORM_ANDROID_IP_WEBCAM
        self.status_data = None
        self.sensor_data = None
        self._timeout = 5
        self._available = True
        self._motion_sensor_device = None
        self._motion_sensor_ffmpeg = None
        self._noise_sensor_device = None
        self._noise_sensor_ffmpeg = None

        self._motion_enabled = None
        self._motion_sensitivity = None
        self._motion_reactivate_timeout = None
        self._motion_low_timeout = None
        self._motion_framerate = None
        self._noise_enabled = None
        self._noise_sensitivity = None
        self._noise_reactivate_timeout = None
        self._noise_low_timeout = None

        reactor.callLater(0.05, self._reload_)  # Dont' hold up the system, spawn a child.

    def _unload(self, **kwargs):
        """
        Closes the FFMPEG connections.

        :param kwargs:
        :return:
        """
        if self._motion_sensor_ffmpeg is not None:
            self._motion_sensor_ffmpeg.close()
        if self._noise_sensor_ffmpeg is not None:
            self._noise_sensor_ffmpeg.close()

    @inlineCallbacks
    def _reload_(self, **kwargs):
        """
        Called by _init_ or when the device has been edited.

        :param kwargs:
        :return:
        """

        yield self.device_variables()
        # print(f"android vars: {self.device_variables_cached}")
        try:
            self._protocol = self.device_variables_cached["protocol"]["values"][0]
        except KeyError:
            self._protocol = "http"
        self._host = self.device_variables_cached["host"]["values"][0]
        self._port = self.device_variables_cached["port"]["values"][0]
        username = self.device_variables_cached["username"]["values"][0]
        password = self.device_variables_cached["password"]["values"][0]
        if username and password:
            self._request_auth = (username, password)

        try:
            self._motion_enabled = self.device_variables_cached["motion_enabled"]["values"][0]
        except KeyError:
            self._motion_enabled = True
        if self._motion_enabled is None:
            self._motion_enabled = True
        try:
            self._motion_sensitivity = self.device_variables_cached["motion_sensitivity"]["values"][0]
        except KeyError:
            self._motion_sensitivity = 15
        try:
            self._motion_denoise = self.device_variables_cached["motion_denoise"]["values"][0]
        except KeyError:
            self._motion_denoise = 10
        try:
            self._motion_reactivate_timeout = self.device_variables_cached["motion_reactivate_timeout"]["values"][0]
        except KeyError:
            self._motion_reactivate_timeout = 10
        try:
            self._motion_low_timeout = self.device_variables_cached["motion_low_timeout"]["values"][0]
        except KeyError:
            self._motion_low_timeout = 10
        try:
            self._motion_framerate = self.device_variables_cached["motion_framerate"]["values"][0]
        except KeyError:
            self._motion_framerate = 8
        try:
            self._noise_enabled = self.device_variables_cached["noise_enabled"]["values"][0]
        except KeyError:
            self._noise_enabled = True
        if self._noise_enabled is None:
            self._noise_enabled = True
        try:
            self._noise_sensitivity = self.device_variables_cached["noise_sensitivity"]["values"][0]
        except KeyError:
            self._noise_sensitivity = -25
        try:
            self._noise_reactivate_timeout = self.device_variables_cached["noise_reactivate_timeout"]["values"][0]
        except KeyError:
            self._noise_reactivate_timeout = 30
        try:
            self._noise_low_timeout = self.device_variables_cached["noise_low_timeout"]["values"][0]
        except KeyError:
            self._noise_low_timeout = 30

        # print("11111111: before update")
        yield self.update()

        # print(f"11111111: self._motion_enabled: {self._motion_enabled}")

        if self._motion_enabled is True:
            # print("11111111: enabled")
            if self._motion_sensor_device is None:
                # print("11111111: no motion sensor device.")
                self._motion_sensor_device = yield self._Devices.create_child_device(
                    self,
                    label="Motion",
                    machine_label="motion",
                    device_type="motion_sensor",
                )
            self._motion_sensor_device.FEATURES[FEATURE_DURATION] = True
            self._motion_sensor_device.MACHINE_STATUS_EXTRA_FIELDS[STATUS_EXTRA_DURATION] = True
            self._motion_sensor_device.set_status(machine_status=0)

            if self._motion_sensor_ffmpeg is None:
                self._motion_sensor_ffmpeg = SensorMotion(self, self.motion_sensor_callback,
                                                          sensitivity=self._motion_sensitivity,
                                                          denoise=self._motion_denoise,
                                                          reactivate_timeout=self._motion_reactivate_timeout,
                                                          low_timeout=self._motion_low_timeout,
                                                          framerate=self._motion_framerate,
                                                          connected_callback=self.motion_sensor_connected,
                                                          closed_callback=self.motion_sensor_closed)
            else:
                self._motion_sensor_ffmpeg.close()
            yield self._motion_sensor_ffmpeg.open_sensor(self.video_url, source_type="video")

        if self._noise_enabled is True:
            if self._noise_sensor_device is None:
                self._noise_sensor_device = yield self._Devices.create_child_device(
                    self,
                    label="Noise",
                    machine_label="noise",
                    device_type="noise_sensor",
                )
            self._noise_sensor_device.FEATURES[FEATURE_DURATION] = True
            self._noise_sensor_device.MACHINE_STATUS_EXTRA_FIELDS[STATUS_EXTRA_DURATION] = True
            self._noise_sensor_device.set_status(machine_status=0)

            if self._noise_sensor_ffmpeg is None:
                self._noise_sensor_ffmpeg = SensorNoise(self, self.noise_sensor_callback, low_timeout=10,
                                                        connected_callback=self.noise_sensor_connected,
                                                        closed_callback=self.noise_sensor_closed)
            else:
                self._noise_sensor_ffmpeg.close()
            yield self._noise_sensor_ffmpeg.open_sensor(self.audio_url)

    def noise_sensor_connected(self, **kwargs):
        print(f"noise_sensor_connected.")

    def noise_sensor_closed(self, **kwargs):
        print(f"noise_sensor_closed.")

    def noise_sensor_callback(self, state, duration, trip_count):
        """
        Testing noise sensor
        :param noise_state:
        :param noise_duration:
        :return:
        """
        # print(f"noise_sensor_callback: state: {state}, duration: {duration} seconds, trip_count: {trip_count}")
        self._noise_sensor_device.set_status(machine_status=state,
                                              machine_status_extra={FEATURE_DURATION: duration})

    def motion_sensor_connected(self, **kwargs):
        # print(f"motion_sensor_connected.")
        pass

    def motion_sensor_closed(self, **kwargs):
        # print(f"motion_sensor_closed.")
        pass

    def motion_sensor_callback(self, state, duration, trip_count):
        """
        Testing noise sensor
        :param motion_start:
        :return:
        """
        # print(f"motion_sensor_callback: state: {state}, duration: {duration} seconds, trip_count: {trip_count}")
        self._motion_sensor_device.set_status(machine_status=state,
                                              machine_status_extra={FEATURE_DURATION: duration})

    @property
    def video_url(self):
        """ The video mjpeg url."""
        return f"{self.base_url}/video"

    @property
    def image_url(self):
        """ Single image (snapshot) url."""
        return f"{self.base_url}/shot.jpg"

    @property
    def audio_url(self):
        """ URL for the audio stream. """
        return f"{self.base_url}/audio.wav"

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
        image_results = yield self._Requests.request("get", self.image_url, self.request_auth)
        return Image(content_type=image_results["headers"]["content-type"][0], iamge=image_results["content"])

    @inlineCallbacks
    def _request(self, path, **kwargs):
        """
        Make a request to the android ip webcam.
        """
        url = f"{self.base_url}{path}"
        data = None
        if "auth" not in kwargs:
            kwargs["auth"] = self.request_auth

        try:
                image_results = yield self._Requests.request("get", url, **kwargs)
                response = image_results["response"]
                # if response.status == 200:
                data = image_results["content"]
        except (CancelledError, YomboWarning) as e:
            logger.error(f"Error communicating with IP Webcam: {e}")
            self._available = False
            return

        self._available = True
        if isinstance(data, str):
            return data.find("Ok") != -1
        else:
            return data

    @property
    def debug_data(self):
        """
        Provide additional debug data.

        :return:
        """
        debug_data = super().debug_data
        debug_data["android_ip_webcam"] = {
            'title': _("module::android_ip_webcam::ui::debug_header", "Android IP Webcam device details"),
            'description': _("module::android_ip_webcam::ui::debug_description", "Data as reported by the Android IP Webcam device."),
            'fields': [
                _("module::android_ip_webcam::ui::debug_column1", "Value name"),
                _("module::android_ip_webcam::ui::debug_column2", "Value data")
            ],
            'data': {
                _("module::android_ip_webcam::ui::debug::base_url", "Base URL"): self.base_url,
                _("module::android_ip_webcam::ui::debug::video_url", "Video URL"): self.video_url,
                _("module::android_ip_webcam::ui::debug::image_url", "Image URL"): self.image_url,
                _("module::android_ip_webcam::ui::debug::audio_url", "Audio URL"): self.audio_url,
                _("module::android_ip_webcam::ui::debug::last_image", "Last Image"): "not avail",
            }
        }
        return debug_data

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
