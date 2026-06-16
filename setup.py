from setuptools import setup
import os
from glob import glob

package_name = 'llm_ros_agent'

setup(
    name=package_name,
    version='0.1.0',
    packages=[
        package_name,
        package_name + '.llm',
    ],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'urdf'), glob('urdf/*.urdf')),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*.world')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Karim Amer',
    maintainer_email='karimamer456@gmail.com',
    description='Interview-ready LLM-to-ROS2 tool-calling agent demo for turtlesim and Gazebo.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'agent_node = llm_ros_agent.agent_node:main',
        ],
    },
)
