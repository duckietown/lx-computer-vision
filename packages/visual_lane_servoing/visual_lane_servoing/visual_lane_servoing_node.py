#!/usr/bin/env python3
"""Visual lane servoing node (``vls_node``).

Performs a form of visual servoing based on image-space detections of the lane markings
(the student functions in ``include/visual_servoing_solution.py``).

Subscribers:
    camera_node/image/compressed (sensor_msgs/CompressedImage)
    camera_node/camera_info      (sensor_msgs/CameraInfo)
Publishers:
    car_cmd_switch_node/cmd          (duckietown_msgs/Twist2DStamped): the car command
    ~/debug/left_mask/compressed     (sensor_msgs/CompressedImage): left (yellow) lane marking mask
    ~/debug/right_mask/compressed    (sensor_msgs/CompressedImage): right (white) lane marking mask
Services (std_srvs/Trigger, driven by the notebook ``ActionButtons``):
    ~/init       put the robot in a lane, reset the calibration
    ~/calibrate  turn the robot in place (keyboard control) to record the maximum steering value
    ~/start      start the visual servoing
    ~/stop       stop the robot
Parameters (live, ``ros2 param set`` or the notebook ``ParamPanel``):
    v_0        forward velocity [m/s]
    omega_max  angular rate [rad/s] the normalized steering is scaled by (<= 0: kinematics calibration)
"""
import os
import time
from typing import Optional

import cv2
import numpy as np
import rclpy
import yaml
from dt_computer_vision.camera import CameraModel
from dt_computer_vision.camera.homography import Homography, HomographyToolkit
from dt_computer_vision.ground_projection import GroundProjector
from duckietown_msgs.msg import Twist2DStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, CompressedImage
from std_srvs.srv import Trigger

from lx_ros2_tools.image import bgr_to_compressed, compressed_to_bgr
from lx_ros2_tools.params import LiveParams

from visual_lane_servoing.include import visual_servoing_solution

ACTIONS = ("init", "calibrate", "start", "stop")


class LaneServoingNode(Node):
    """
    Performs a form of visual servoing based on estimates of the image-space lane orientation
    """

    def __init__(self):
        super().__init__("vls_node")
        self.get_logger().info("Initializing...")
        # get the name of the robot
        self.veh = self.get_namespace().strip("/")

        # Parameters (defaults also in config/vls_node/default.yaml, loaded by the launch file)
        #  - v_0: forward velocity command
        #  - omega_max: the maximum omega used to scale the normalized steering command;
        #    <= 0 means "take it from the kinematics calibration file of the robot"
        self.params = LiveParams(self, {"v_0": 0.2, "omega_max": -1.0}, on_change=self._on_param)
        self.omega_max_calib = self.read_params_from_calibration_file().get("omega_max", 2.0)

        # The following are used for scaling
        self.steer_max = -1

        self.VLS_ACTION: Optional[str] = None
        self.VLS_STOPPED = True

        # Defining subscribers:
        self.sub_image = self.create_subscription(
            CompressedImage, "camera_node/image/compressed", self.cb_image, qos_profile_sensor_data
        )
        self.sub_camera_info = self.create_subscription(CameraInfo, "camera_node/camera_info", self.cb_info, 10)

        self.camera_model = None
        self.projector = None
        self.mapx = None
        self.mapy = None

        # services driven from the notebook panel (ActionButtons) or `ros2 service call`
        for action in ACTIONS:
            self.create_service(Trigger, f"~/{action}", lambda req, res, a=action: self.srv_action(a, req, res))

        # Command publisher
        self.pub_car_cmd = self.create_publisher(Twist2DStamped, "car_cmd_switch_node/cmd", 10)

        self.pub_lt_mask = self.create_publisher(CompressedImage, "~/debug/left_mask/compressed", 10)
        self.pub_rt_mask = self.create_publisher(CompressedImage, "~/debug/right_mask/compressed", 10)

        self.get_logger().info(
            f"Initialized! v_0 = {self.params.v_0}, omega_max = {self.omega_max} "
            f"(calibration: {self.omega_max_calib})"
        )

    @property
    def omega_max(self) -> float:
        return float(self.params.omega_max) if self.params.omega_max > 0 else float(self.omega_max_calib)

    def _on_param(self, name, value):
        self.get_logger().info(f"parameter {name} = {value}")

    def cb_info(self, msg: CameraInfo):
        if self.camera_model is not None:
            # we only need the first message
            return
        self.get_logger().info("Camera info message received.")
        H, W = msg.height, msg.width
        # create new camera info
        self.camera_model = CameraModel(
            width=W,
            height=H,
            K=np.reshape(msg.k, (3, 3)),
            D=np.reshape(msg.d, (5,)),
            P=np.reshape(msg.p, (3, 4)),
        )
        homography = self.load_extrinsics()
        if homography is not None:
            self.camera_model.H = homography
            self.projector = GroundProjector(self.camera_model)

        rect_camera_K, _ = cv2.getOptimalNewCameraMatrix(self.camera_model.K, self.camera_model.D, (W, H), alpha=0.0)
        self.mapx, self.mapy = cv2.initUndistortRectifyMap(
            self.camera_model.K, self.camera_model.D, None, rect_camera_K, (W, H), cv2.CV_32FC1
        )

    def srv_action(self, action: str, _req, res):
        """
        Call the right functions according to the button pressed in the notebook.
        """
        if action not in ACTIONS:
            res.success, res.message = False, f"Activity '{action}' not recognized"
            return res

        self.VLS_ACTION = action
        self.get_logger().info(f"ACTION: {self.VLS_ACTION}")

        if self.VLS_ACTION == "init":
            self.steer_max = -1
            self.VLS_STOPPED = True
            self.publish_command([0, 0])
            res.message = "Put the robot in a lane. Press [calibrate] when done."
            self.get_logger().info(res.message)

        elif self.VLS_ACTION == "calibrate":
            self.VLS_STOPPED = True
            res.message = (
                "Using your hands if you are working with a real robot, or the keyboard control if "
                "you are working with the simulator, turn the robot (in place) to the left "
                "then to the right by about 30deg on each side. Press [start] when done."
            )
            self.get_logger().info(res.message)

        elif self.VLS_ACTION == "start":
            if self.steer_max == -1:
                res.success, res.message = False, "Not calibrated! Press [calibrate] and turn the robot first."
                self.get_logger().error(res.message)
                return res
            res.message = f"Calibration value: {int(self.steer_max)}. Visual servoing started."
            self.get_logger().info(res.message)
            self.VLS_STOPPED = False
            # NOTE: this is needed to trigger the agent and get another image back
            self.publish_command([0, 0])

        elif self.VLS_ACTION == "stop":
            self.publish_command([0, 0])
            self.VLS_STOPPED = True
            res.message = "Stopped."

        res.success = True
        return res

    def cb_image(self, image_msg: CompressedImage):
        """
        Processes the incoming image messages.

        Performs the following steps for each incoming image:

        #. Rectifies the image with the camera intrinsics
        #. Runs the student's lane marking detector and publishes the masks
        #. Computes and publishes the steering command (when started)

        Args:
            image_msg (:obj:`sensor_msgs.msg.CompressedImage`): The received image message

        """

        # make sure we have a map to use
        if self.mapx is None or self.mapy is None:
            self.get_logger().info("Waiting for Camera Info", throttle_duration_sec=2.0)
            return

        dist_img = compressed_to_bgr(image_msg)
        image = cv2.remap(dist_img, self.mapx, self.mapy, cv2.INTER_NEAREST)

        shape = image.shape[0:2]

        steer_matrix_left_lm = visual_servoing_solution.get_steer_matrix_left_lane_markings(shape)
        steer_matrix_right_lm = visual_servoing_solution.get_steer_matrix_right_lane_markings(shape)

        # Call the user-defined function to get the masks for the left
        # and right lane markings
        (lt_mask, rt_mask) = visual_servoing_solution.detect_lane_markings(image, self.projector)

        # Publish these out for visualization (ImageView in the notebook)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        lt_mask_viz = cv2.addWeighted(gray, 0.1, lt_mask.astype(np.uint8), 0.8, 0)
        rt_mask_viz = cv2.addWeighted(gray, 0.1, rt_mask.astype(np.uint8), 0.8, 0)

        self.pub_lt_mask.publish(bgr_to_compressed(lt_mask_viz, header=image_msg.header))
        self.pub_rt_mask.publish(bgr_to_compressed(rt_mask_viz, header=image_msg.header))

        if self.VLS_ACTION == "calibrate":
            self.steer_max = max(
                self.steer_max,
                2
                * max(
                    float(np.sum(lt_mask * steer_matrix_left_lm)),
                    float(np.sum(rt_mask * steer_matrix_right_lm)),
                ),
            )

        if self.VLS_ACTION != "start" or self.VLS_STOPPED:
            return

        if self.steer_max == -1:
            self.get_logger().error("Not Calibrated!", throttle_duration_sec=2.0)
            return

        steer = float(np.sum(lt_mask * steer_matrix_left_lm)) + float(np.sum(rt_mask * steer_matrix_right_lm))

        # now rescale from 0 to 1
        steer_scaled = np.sign(steer) * rescale(min(np.abs(steer), self.steer_max), 0, self.steer_max)

        u = [float(self.params.v_0), steer_scaled * self.omega_max]
        self.publish_command(u)

        # logging to screen for debugging purposes
        self.get_logger().info(
            "    VISUAL SERVOING    "
            f"Steering: (Unnormalized) : {int(steer)} / {int(self.steer_max)},"
            f"  Steering (Normalized) : {np.round(steer_scaled, 1)}  "
            f"Command v : {np.round(u[0], 2)},  omega : {np.round(u[1], 2)}",
            throttle_duration_sec=1.0,
        )

    def publish_command(self, u):
        """Publishes a car command message.

        Args:
            u (:obj:`tuple(double, double)`): tuple containing [v, w] for the control action.
        """

        car_control_msg = Twist2DStamped()
        car_control_msg.header.stamp = self.get_clock().now().to_msg()

        car_control_msg.v = float(u[0])  # v
        car_control_msg.omega = float(u[1])  # omega

        self.pub_car_cmd.publish(car_control_msg)

    @staticmethod
    def trim(value, low, high):
        """
        Trims a value to be between some bounds.

        Args:
            value: the value to be trimmed
            low: the minimum bound
            high: the maximum bound

        Returns:
            the trimmed value
        """
        return max(min(value, high), low)

    def read_params_from_calibration_file(self) -> dict:
        """
        Reads the saved parameters from `/data/config/calibrations/kinematics/DUCKIEBOTNAME.yaml`
        or from `default.yaml`; returns an empty dict if neither exists.
        """
        cali_file_folder = "/data/config/calibrations/kinematics/"
        for fname in (cali_file_folder + self.veh + ".yaml", cali_file_folder + "default.yaml"):
            if os.path.isfile(fname):
                try:
                    with open(fname, "r") as in_file:
                        return yaml.safe_load(in_file) or {}
                except yaml.YAMLError as exc:
                    self.get_logger().error("YAML syntax error. File: %s. Exc: %s" % (fname, exc))
                    return {}
        self.get_logger().warning(
            "Kinematic calibration not found in %s! Using omega_max = 2.0 instead." % cali_file_folder
        )
        return {}

    def load_extrinsics(self) -> Optional[Homography]:
        """
        Loads the homography matrix from the extrinsic calibration file.

        Returns:
            :obj:`Homography`: the loaded homography matrix, or None if no calibration file is found
            (the horizon is then estimated without the ground projector).

        """
        # load extrinsic calibration
        cali_file_folder = "/data/config/calibrations/camera_extrinsic/"
        cali_file = cali_file_folder + self.veh + ".yaml"

        # Locate calibration yaml file or use the default otherwise
        if not os.path.isfile(cali_file):
            self.get_logger().warning(f"Can't find calibration file: {cali_file}\n Using default calibration instead.")
            cali_file = os.path.join(cali_file_folder, "default.yaml")

        if not os.path.isfile(cali_file):
            self.get_logger().error("Found no extrinsic calibration file ... running without ground projection")
            return None

        try:
            self.H: Homography = HomographyToolkit.load_from_disk(cali_file, return_date=False)  # type: ignore
            return self.H.reshape((3, 3))
        except Exception as e:
            self.get_logger().error(f"Error in parsing calibration file {cali_file}:\n{e}")
            return None

    def on_shutdown(self):
        self.get_logger().info("Stopping motors...")
        self.publish_command([0, 0])
        time.sleep(0.5)
        self.get_logger().info("Motors stopped.")


def rescale(a: float, L: float, U: float):
    if np.allclose(L, U):
        return 0.0
    return (a - L) / (U - L)


def main(args=None):
    rclpy.init(args=args)
    node = LaneServoingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.on_shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
