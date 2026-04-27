"""Deterministic tool implementations for a Gazebo differential-drive robot.

The planner-facing API intentionally matches TurtleTools so the agent can swap
simulation backends without changing validation, safety, logging, or goals.
"""

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


def _angle_norm(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def _yaw_from_quaternion(q: Any) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


@dataclass
class GazeboState:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0


class GazeboTools:
    def __init__(
        self,
        node: Node,
        bounds_min: float,
        bounds_max: float,
        max_linear_speed: float,
        max_angular_speed: float,
        goal_tolerance: float,
        cmd_vel_topic: str = "/demo_bot/cmd_vel",
        odom_topic: str = "/demo_bot/odom",
    ):
        self.node = node
        self.state = GazeboState()
        self.bounds_min = bounds_min
        self.bounds_max = bounds_max
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed
        self.goal_tolerance = goal_tolerance
        self._has_odom = False

        self._cmd_pub = node.create_publisher(Twist, cmd_vel_topic, 10)
        self._odom_sub = node.create_subscription(Odometry, odom_topic, self._on_odom, 10)

    def _on_odom(self, msg: Odometry) -> None:
        pos = msg.pose.pose.position
        quat = msg.pose.pose.orientation
        twist = msg.twist.twist

        self.state.x = float(pos.x)
        self.state.y = float(pos.y)
        self.state.theta = float(_yaw_from_quaternion(quat))
        self.state.linear_velocity = float(twist.linear.x)
        self.state.angular_velocity = float(twist.angular.z)
        self._has_odom = True

    async def _wait_for_odom(self, timeout_s: float = 5.0) -> bool:
        start = time.monotonic()
        while not self._has_odom:
            if time.monotonic() - start > timeout_s:
                return False
            await asyncio.sleep(0.05)
        return True

    def _stop(self) -> None:
        self._cmd_pub.publish(Twist())

    async def say_pose(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not await self._wait_for_odom():
            return {"ok": False, "error": "No odometry received from Gazebo."}
        return {
            "ok": True,
            "pose": {"x": self.state.x, "y": self.state.y, "theta": self.state.theta},
        }

    async def set_pen(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "message": "Gazebo backend has no pen service; command accepted as a no-op.",
        }

    async def go_to(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not await self._wait_for_odom():
            return {"ok": False, "error": "No odometry received from Gazebo."}

        tx = float(args["x"])
        ty = float(args["y"])
        target_theta: Optional[float] = None
        if "theta" in args and args["theta"] is not None:
            target_theta = float(args["theta"])

        k_lin = 0.9
        k_ang = 2.8
        start = time.monotonic()
        timeout_s = 30.0

        while True:
            dx = tx - self.state.x
            dy = ty - self.state.y
            dist = math.hypot(dx, dy)
            if dist < self.goal_tolerance:
                break

            desired_heading = math.atan2(dy, dx)
            heading_error = _angle_norm(desired_heading - self.state.theta)

            cmd = Twist()
            cmd.angular.z = max(
                -self.max_angular_speed,
                min(self.max_angular_speed, k_ang * heading_error),
            )
            cmd.linear.x = max(0.0, min(self.max_linear_speed, k_lin * dist))
            if abs(heading_error) > 0.6:
                cmd.linear.x *= 0.2

            self._cmd_pub.publish(cmd)

            if time.monotonic() - start > timeout_s:
                self._stop()
                return {
                    "ok": False,
                    "error": "go_to timeout",
                    "final_pose": {
                        "x": self.state.x,
                        "y": self.state.y,
                        "theta": self.state.theta,
                    },
                }

            await asyncio.sleep(0.05)

        if target_theta is not None:
            await self._rotate_to(target_theta, timeout_s=8.0)

        self._stop()
        return {
            "ok": True,
            "final_pose": {"x": self.state.x, "y": self.state.y, "theta": self.state.theta},
        }

    async def draw_square(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not await self._wait_for_odom():
            return {"ok": False, "error": "No odometry received from Gazebo."}

        workspace_span = max(0.1, self.bounds_max - self.bounds_min)
        size = max(0.1, min(float(args["size"]), workspace_span / 2.0))
        for _ in range(4):
            if not await self._forward(size):
                return {"ok": False, "error": "draw_square forward segment timeout"}
            if not await self._rotate(math.pi / 2.0):
                return {"ok": False, "error": "draw_square rotation timeout"}
        return {"ok": True, "size": size}

    async def _forward(self, dist: float) -> bool:
        start_x = self.state.x
        start_y = self.state.y
        start = time.monotonic()

        while True:
            traveled = math.hypot(self.state.x - start_x, self.state.y - start_y)
            if traveled >= dist:
                break

            cmd = Twist()
            cmd.linear.x = min(self.max_linear_speed, 0.45)
            self._cmd_pub.publish(cmd)

            if time.monotonic() - start > max(8.0, dist / max(cmd.linear.x, 0.1) + 4.0):
                self._stop()
                return False

            await asyncio.sleep(0.05)

        self._stop()
        return True

    async def _rotate(self, angle: float) -> bool:
        return await self._rotate_to(_angle_norm(self.state.theta + angle), timeout_s=8.0)

    async def _rotate_to(self, target: float, timeout_s: float) -> bool:
        start = time.monotonic()
        while True:
            err = _angle_norm(target - self.state.theta)
            if abs(err) < 0.08:
                break

            cmd = Twist()
            cmd.angular.z = max(
                -self.max_angular_speed,
                min(self.max_angular_speed, 2.2 * err),
            )
            self._cmd_pub.publish(cmd)

            if time.monotonic() - start > timeout_s:
                self._stop()
                return False

            await asyncio.sleep(0.05)

        self._stop()
        return True
