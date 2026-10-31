<p align="center">
<a href="https://duckietown.com"><img src="./assets/images/dtlogo.png" alt="Duckietown Logo" width="50%"></a>
</p>

# Learning Experience (LX): Computer Vision

Find the most up-to-date instructions on [how to run LXs on the Duckietown manual](https://docs.duckietown.com/ente/duckietown-manual/60-learning-experiences/lx-setup-pid-control.html). 

**NOTE:** All commands below are intended to be executed from the root directory of this exercise (i.e., the directory containing this `README`).

## 1. Make sure your exercise is up-to-date

Update your exercise definition and instructions,

    git pull upstream ente

**NOTE:** to pull from upstream, you need to have completed the instructions in the [duckietown-lx repository README](https://github.com/duckietown/duckietown-lx/blob/mooc2022/README.md) to *fork* this repository.


## 2. Make sure your system is up-to-date

- 💻 Always make sure your Duckietown Shell is updated to the latest version. See [installation instructions](https://github.com/duckietown/duckietown-shell)

This exercise is meant to be run with the `ente` version of the shell commands. You can switch to that version with `dts profile switch ente`. 

- 💻 Update the shell commands: `dts update`

- 💻 Update your laptop/desktop: `dts desktop update`

- 🚙 Update your Duckiebot: `dts duckiebot update ROBOTNAME` (where `ROBOTNAME` is the name of your (real or virtual - more on this later) Duckiebot chosen during the initialization procedure.)

- 🚙 This exercise runs on **ROS 2** (Jazzy). Bring the ROS 2 stack up on your Duckiebot (real or virtual) once it is booted:

```
dts stack up -R ROBOTNAME ros2/duckiebot
dts stack up -R ROBOTNAME ros2-core/default
```

## 3. Work on the exercise


### Launch the code editor

Open the code editor by running the following command,

```
dts code editor
```

Wait for a URL to appear on the terminal, then click on it or copy-paste it in the address bar
of your browser to access the code editor. The first thing you will see in the code editor is
this same document, you can continue there.


### Walkthrough of notebooks

**NOTE**: You should be reading this from inside the code editor in your browser.

Inside the code editor, use the navigator sidebar on the left-hand side to navigate to the
`notebooks` directory and open the first notebook.

Follow the instructions on the notebook and work through the notebooks in sequence.


### Building your code

You can build your code with 

```
dts code build -R ROBOT_NAME
```

This will build a docker image with your code compiled inside - you should see your ROS 2 packages (`visual_lane_servoing`, `encoder_pose`, `lx_ros2_tools`) get built by `colcon` during the process. 


### Testing with Duckiematrix

In order to test your code in the Duckiematrix you will need a virtual robot. You can create one with the command:

```
dts duckiebot virtual create --type duckiebot --configuration DB21J [VBOT]
```

where `[VBOT]` is the hostname. It can be anything you like, with [some constraints](https://docs.duckietown.com/ente/duckietown-manual/10-setup/03-duckiebot/flashing-sd-card-duckiebot-initialization-complete.html). Make sure to remember your robot (host)name for later.

Then you can start your virtual robot with the command:

```
dts duckiebot virtual start [VIRTUAL_ROBOT_NAME]
```

You should see it with a status `Booting` and finally `Ready` if you look at `dts fleet discover`: 

```
     | Hardware |   Type    | Model |  Status  | Hostname 
---  | -------- | --------- | ----- | -------- | ---------
vbot |  virtual | duckiebot | DB21J |  Ready   | vbot.local
```

Virtual robots still boot with the ROS 1 stack; start the ROS 2 stack on it explicitly (once per boot):

```
dts stack up -R [VBOT] ros2/duckiebot
dts stack up -R [VBOT] ros2-core/default
```

Now that your virtual robot is ready you can start the Duckiematrix. From this exercise directory do:

```
dts code start_matrix
```

You should see the Unity-based Duckiematrix simulator start up. 


### 💻 Testing 


To test your code in the duckiematrix you can do:

```
dts code workbench -m -R [VBOT]
```

and to test your code on your real Duckiebot you can do:

```
dts code workbench -R [ROBOT_NAME]
```


The workbench runs the ROS 2 nodes of this exercise (`vls_node` and `encoder_pose_node`) in the namespace of your robot, connected to the robot's zenoh router. Leave it running and go back to the code editor (`dts code editor`): the last notebook ([04-Visual-Servoing](./notebooks/04-Visual-Servoing/visual_servoing.ipynb)) contains the control panel of the exercise, built with `ipywidgets`:

- `RosSession(ROBOT)` connects the notebook to your robot;
- `ActionButtons(ros, "vls_node", ["init", "calibrate", "start", "stop"])` drives the node (these are `std_srvs/Trigger` services);
- `ParamPanel` lets you change `v_0` (forward speed) and `omega_max` (steering scale) live;
- `ImageView` shows the camera and the left/right lane-marking masks your code produces;
- `TrajectoryPlot` draws the odometry estimated from the wheel encoders.

To drive the robot by hand (needed for the `calibrate` step), open a second terminal and run the keyboard control:

```
dts duckiebot keyboard_control [ROBOT_NAME]
```

### Debugging from the editor terminal

A terminal inside the code editor (`Terminal > New Terminal`) already has ROS 2 set up and, when the `VEHICLE_NAME` environment variable is set (or after the `RosSession(ROBOT)` cell has run), it is connected to the robot's zenoh router. Useful commands:

```
ros2 node list
ros2 topic list
ros2 topic echo /[ROBOT_NAME]/car_cmd_switch_node/cmd
ros2 param list /[ROBOT_NAME]/vls_node
ros2 param set /[ROBOT_NAME]/vls_node v_0 0.15
ros2 service call /[ROBOT_NAME]/vls_node/stop std_srvs/srv/Trigger
```

**Note**: right after connecting, the ROS graph takes a few seconds to sync through the zenoh router; if a list comes back empty use `ros2 topic list --no-daemon --spin-time 5` (same for `ros2 node list`).

### Troubleshooting

- *The node publishes car commands but the robot does not move*: the `kinematics_node` of your robot may still listen on the older topic `car_cmd` instead of `car_cmd_switch_node/cmd`. Check with `ros2 node info /[ROBOT_NAME]/kinematics_node` and, if so, relaunch the nodes with the topic remapped: `ros2 launch visual_lane_servoing visual_lane_servoing_node.launch.py veh:=[ROBOT_NAME] car_cmd_topic:=car_cmd` (the launcher of `dts code workbench` forwards the environment variable `CAR_CMD_TOPIC=car_cmd` the same way).

Now you can proceed to the [first notebook](./notebooks/01-Pinhole-Camera/pinhole_camera_matrix.ipynb).

