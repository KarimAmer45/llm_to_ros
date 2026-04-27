from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='llm_ros_agent',
            executable='agent_node',
            name='llm_ros_agent',
            output='screen',
            parameters=[{
                'planner': 'mock',   # mock or external
                'backend': 'turtlesim',
                'bounds_min': 0.5,
                'bounds_max': 10.5,
                'max_linear_speed': 2.0,
                'max_angular_speed': 2.5,
                'goal_tolerance': 0.15,
            }]
        )
    ])
