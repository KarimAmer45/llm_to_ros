from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = Path(get_package_share_directory("llm_ros_agent"))
    gazebo_share = Path(get_package_share_directory("gazebo_ros"))

    world_path = str(pkg_share / "worlds" / "interview_arena.world")
    robot_description = (pkg_share / "urdf" / "llm_demo_bot.urdf").read_text(encoding="utf-8")
    use_sim_time = LaunchConfiguration("use_sim_time")

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(gazebo_share / "launch" / "gazebo.launch.py")),
        launch_arguments={"world": world_path}.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{"robot_description": robot_description, "use_sim_time": use_sim_time}],
    )

    spawn_robot = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        name="spawn_llm_demo_bot",
        output="screen",
        arguments=[
            "-topic",
            "robot_description",
            "-entity",
            "llm_demo_bot",
            "-x",
            "0.0",
            "-y",
            "0.0",
            "-z",
            "0.08",
        ],
    )

    agent = Node(
        package="llm_ros_agent",
        executable="agent_node",
        name="llm_ros_agent",
        output="screen",
        parameters=[
            {
                "planner": "mock",
                "backend": "gazebo",
                "bounds_min": -5.0,
                "bounds_max": 5.0,
                "max_linear_speed": 0.7,
                "max_angular_speed": 1.8,
                "goal_tolerance": 0.18,
                "cmd_vel_topic": "/demo_bot/cmd_vel",
                "odom_topic": "/demo_bot/odom",
                "use_sim_time": use_sim_time,
            }
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            gazebo,
            robot_state_publisher,
            TimerAction(period=2.0, actions=[spawn_robot]),
            TimerAction(period=4.0, actions=[agent]),
        ]
    )
