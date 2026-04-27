"""Deterministic tool implementations for turtlesim (ROS2).

Implements a simple go-to controller using cmd_vel + pose feedback.
This is intentionally small but good enough for an interview demo.

Key idea to explain:
- LLM chooses *which tool*
- This module executes tools *deterministically* and returns structured results
"""

import math
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from turtlesim.msg import Pose
from turtlesim.srv import SetPen

def _angle_norm(a: float) -> float:
    while a > math.pi:
        a -= 2*math.pi
    while a < -math.pi:
        a += 2*math.pi
    return a

@dataclass
class TurtleState:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0

class TurtleTools:
    def __init__(self, node: Node,
                 bounds_min: float,
                 bounds_max: float,
                 max_linear_speed: float,
                 max_angular_speed: float,
                 goal_tolerance: float,
                 cmd_vel_topic: str = "/turtle1/cmd_vel",
                 pose_topic: str = "/turtle1/pose",
                 set_pen_service: str = "/turtle1/set_pen"):
        self.node = node
        self.state = TurtleState()
        self.bounds_min = bounds_min
        self.bounds_max = bounds_max
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed
        self.goal_tolerance = goal_tolerance

        self._cmd_pub = node.create_publisher(Twist, cmd_vel_topic, 10)
        self._pose_sub = node.create_subscription(Pose, pose_topic, self._on_pose, 10)
        self._pen_cli = node.create_client(SetPen, set_pen_service)

    def _on_pose(self, msg: Pose) -> None:
        self.state.x = float(msg.x)
        self.state.y = float(msg.y)
        self.state.theta = float(msg.theta)
        self.state.linear_velocity = float(msg.linear_velocity)
        self.state.angular_velocity = float(msg.angular_velocity)

    async def say_pose(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "pose": {"x": self.state.x, "y": self.state.y, "theta": self.state.theta}}

    async def set_pen(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Wait briefly for service (non-blocking)
        for _ in range(20):
            if self._pen_cli.service_is_ready():
                break
            await asyncio.sleep(0.1)

        if not self._pen_cli.service_is_ready():
            return {"ok": False, "error": "SetPen service not available."}

        req = SetPen.Request()
        req.r = int(args["r"]); req.g = int(args["g"]); req.b = int(args["b"])
        req.width = int(args["width"]); req.off = int(args["off"])

        fut = self._pen_cli.call_async(req)
        while not fut.done():
            await asyncio.sleep(0.05)
        return {"ok": True}

    async def go_to(self, args: Dict[str, Any]) -> Dict[str, Any]:
        tx = float(args["x"]); ty = float(args["y"])
        target_theta: Optional[float] = None
        if "theta" in args and args["theta"] is not None:
            target_theta = float(args["theta"])

        # Controller gains (simple, stable for turtlesim)
        k_lin = 1.2
        k_ang = 4.0

        start = self.node.get_clock().now().nanoseconds / 1e9
        timeout_s = 20.0

        while True:
            dx = tx - self.state.x
            dy = ty - self.state.y
            dist = math.hypot(dx, dy)

            # stop condition
            if dist < self.goal_tolerance:
                break

            desired_heading = math.atan2(dy, dx)
            heading_error = _angle_norm(desired_heading - self.state.theta)

            cmd = Twist()
            # angular first, then linear
            cmd.angular.z = max(-self.max_angular_speed, min(self.max_angular_speed, k_ang * heading_error))
            cmd.linear.x = max(0.0, min(self.max_linear_speed, k_lin * dist))
            if abs(heading_error) > 0.7:
                cmd.linear.x *= 0.25

            self._cmd_pub.publish(cmd)

            now = self.node.get_clock().now().nanoseconds / 1e9
            if now - start > timeout_s:
                self._cmd_pub.publish(Twist())
                return {"ok": False, "error": "go_to timeout", "final_pose": {"x": self.state.x, "y": self.state.y, "theta": self.state.theta}}

            await asyncio.sleep(0.05)

        # Optional final orientation
        if target_theta is not None:
            start2 = self.node.get_clock().now().nanoseconds / 1e9
            while True:
                err = _angle_norm(target_theta - self.state.theta)
                if abs(err) < 0.1:
                    break
                cmd = Twist()
                cmd.angular.z = max(-self.max_angular_speed, min(self.max_angular_speed, 3.0 * err))
                self._cmd_pub.publish(cmd)
                now2 = self.node.get_clock().now().nanoseconds / 1e9
                if now2 - start2 > 8.0:
                    break
                await asyncio.sleep(0.05)

        self._cmd_pub.publish(Twist())
        return {"ok": True, "final_pose": {"x": self.state.x, "y": self.state.y, "theta": self.state.theta}}

    async def draw_square(self, args: Dict[str, Any]) -> Dict[str, Any]:
        size = float(args["size"])
        # Draw by: go forward size, rotate 90 degrees, repeat 4 times
        for _ in range(4):
            await self._forward(size)
            await self._rotate(math.pi/2)
        return {"ok": True}

    async def _forward(self, dist: float) -> None:
        start_x, start_y = self.state.x, self.state.y
        start = self.node.get_clock().now().nanoseconds / 1e9
        while True:
            d = math.hypot(self.state.x - start_x, self.state.y - start_y)
            if d >= dist:
                break
            cmd = Twist()
            cmd.linear.x = min(self.max_linear_speed, 1.5)
            self._cmd_pub.publish(cmd)
            now = self.node.get_clock().now().nanoseconds / 1e9
            if now - start > 10.0:
                break
            await asyncio.sleep(0.05)
        self._cmd_pub.publish(Twist())

    async def _rotate(self, angle: float) -> None:
        target = _angle_norm(self.state.theta + angle)
        start = self.node.get_clock().now().nanoseconds / 1e9
        while True:
            err = _angle_norm(target - self.state.theta)
            if abs(err) < 0.08:
                break
            cmd = Twist()
            cmd.angular.z = max(-self.max_angular_speed, min(self.max_angular_speed, 3.0 * err))
            self._cmd_pub.publish(cmd)
            now = self.node.get_clock().now().nanoseconds / 1e9
            if now - start > 8.0:
                break
            await asyncio.sleep(0.05)
        self._cmd_pub.publish(Twist())
