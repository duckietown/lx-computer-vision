import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    veh = LaunchConfiguration("veh")
    car_cmd_topic = LaunchConfiguration("car_cmd_topic")
    config = os.path.join(get_package_share_directory("visual_lane_servoing"), "config", "vls_node", "default.yaml")
    encoder_pose_launch = os.path.join(
        get_package_share_directory("encoder_pose"), "launch", "encoder_pose_node.launch.py"
    )
    return LaunchDescription([
        DeclareLaunchArgument("veh", default_value=EnvironmentVariable("VEHICLE_NAME"),
                              description="robot name (namespace of every topic)"),
        # The core stack's kinematics_node listens on `car_cmd_switch_node/cmd` (current `ente` source);
        # robot images built before 2026-10-20 listen on `car_cmd`: pass `car_cmd_topic:=car_cmd` for those.
        DeclareLaunchArgument("car_cmd_topic",
                              default_value=EnvironmentVariable("CAR_CMD_TOPIC", default_value="car_cmd_switch_node/cmd"),
                              description="topic (relative to the robot namespace) the kinematics node reads car commands from"),
        Node(
            package="visual_lane_servoing",
            executable="visual_lane_servoing_node",
            name="vls_node",
            namespace=veh,
            parameters=[config],
            remappings=[("car_cmd_switch_node/cmd", car_cmd_topic)],
            output="screen",
            emulate_tty=True,
        ),
        # we are also launching the encoder pose node just for visualization purposes (TrajectoryPlot)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(encoder_pose_launch),
            launch_arguments={"veh": veh}.items(),
        ),
    ])
