"""Main ROS2 node: LLM-toolcalling agent loop for ROS2 simulators.

Usage:
- Run turtlesim_node separately, or launch the bundled Gazebo demo
- Run: ros2 run llm_ros_agent agent_node --ros-args -p planner:=mock

Publish goals:
  ros2 topic pub /agent/goal std_msgs/msg/String "{data: 'Go to x=8 y=2 then draw a square size 2'}" -1

Interview talking points:
- Planner is swappable (mock vs real LLM)
- Validation + safety before execution
- Deterministic tool layer
- Logs to JSONL for evaluation
"""

import os
import json
import asyncio
from typing import Any, Dict

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .llm.mock import MockPlanner
from .safety import validate_tool_call, clamp_go_to_args
from .tools_turtlesim import TurtleTools
from .tool_registry import ToolRegistry
from .logging_utils import JsonlLogger

class AgentNode(Node):
    def __init__(self):
        super().__init__("llm_ros_agent")

        self.declare_parameter("planner", "mock")
        self.declare_parameter("backend", "turtlesim")
        self.declare_parameter("bounds_min", 0.5)
        self.declare_parameter("bounds_max", 10.5)
        self.declare_parameter("max_linear_speed", 2.0)
        self.declare_parameter("max_angular_speed", 2.5)
        self.declare_parameter("goal_tolerance", 0.15)
        self.declare_parameter("cmd_vel_topic", "")
        self.declare_parameter("pose_topic", "")
        self.declare_parameter("odom_topic", "")
        self.declare_parameter("set_pen_service", "")
        self.declare_parameter("log_path", os.path.join(os.path.expanduser("~"), "llm_ros_agent_log.jsonl"))

        self.planner_name = self.get_parameter("planner").get_parameter_value().string_value
        self.backend = str(self.get_parameter("backend").value).lower()
        self.bounds_min = float(self.get_parameter("bounds_min").value)
        self.bounds_max = float(self.get_parameter("bounds_max").value)
        self.max_linear_speed = float(self.get_parameter("max_linear_speed").value)
        self.max_angular_speed = float(self.get_parameter("max_angular_speed").value)
        self.goal_tolerance = float(self.get_parameter("goal_tolerance").value)
        self.logger_jsonl = JsonlLogger(str(self.get_parameter("log_path").value))

        # Planner (mock by default)
        self.planner = MockPlanner()

        # Tools
        self.tools = self._make_tools()
        self.tool_registry = ToolRegistry()
        for tool_name in ("go_to", "draw_square", "say_pose", "set_pen"):
            self.tool_registry.register(tool_name, getattr(self.tools, tool_name))

        self.sub = self.create_subscription(String, "/agent/goal", self.on_goal, 10)
        self.pub = self.create_publisher(String, "/agent/status", 10)

        self._busy = False

        self.get_logger().info("LLM-to-ROS agent started. Waiting for /agent/goal...")
        self.get_logger().info(
            f"Planner: {self.planner_name} | Backend: {self.backend} | "
            f"Log: {self.get_parameter('log_path').value}"
        )

    def _param_or_default(self, name: str, default: str) -> str:
        value = str(self.get_parameter(name).value)
        return value if value else default

    def _make_tools(self):
        if self.backend in ("turtle", "turtlesim"):
            return TurtleTools(
                node=self,
                bounds_min=self.bounds_min,
                bounds_max=self.bounds_max,
                max_linear_speed=self.max_linear_speed,
                max_angular_speed=self.max_angular_speed,
                goal_tolerance=self.goal_tolerance,
                cmd_vel_topic=self._param_or_default("cmd_vel_topic", "/turtle1/cmd_vel"),
                pose_topic=self._param_or_default("pose_topic", "/turtle1/pose"),
                set_pen_service=self._param_or_default("set_pen_service", "/turtle1/set_pen"),
            )

        if self.backend == "gazebo":
            from .tools_gazebo import GazeboTools

            return GazeboTools(
                node=self,
                bounds_min=self.bounds_min,
                bounds_max=self.bounds_max,
                max_linear_speed=self.max_linear_speed,
                max_angular_speed=self.max_angular_speed,
                goal_tolerance=self.goal_tolerance,
                cmd_vel_topic=self._param_or_default("cmd_vel_topic", "/demo_bot/cmd_vel"),
                odom_topic=self._param_or_default("odom_topic", "/demo_bot/odom"),
            )

        raise ValueError("Unsupported backend '{}'. Use 'turtlesim' or 'gazebo'.".format(self.backend))

    def on_goal(self, msg: String) -> None:
        if self._busy:
            self.get_logger().warn("Agent is busy; ignoring new goal.")
            return
        goal = msg.data.strip()
        self._busy = True
        asyncio.get_event_loop().create_task(self.run_goal(goal))

    async def run_goal(self, goal: str) -> None:
        self.get_logger().info(f"Goal: {goal}")
        self.logger_jsonl.log("goal_received", goal=goal)

        # Minimal state
        state: Dict[str, Any] = {"phase": None}

        # Very small multi-step capability: handle "then draw square" after go_to
        steps_remaining = 6
        try:
            while steps_remaining > 0:
                steps_remaining -= 1

                tool_call = self.planner.plan(goal, state)
                tool = tool_call.get("tool")
                args = tool_call.get("args", {})
                reason = tool_call.get("reason", "")

                self.logger_jsonl.log("plan", tool=tool, args=args, reason=reason, state=state)

                ok, errors = validate_tool_call(tool, args)
                if not ok:
                    self.get_logger().error(f"Invalid tool call: {errors}")
                    self.logger_jsonl.log("validation_error", errors=errors, tool=tool, args=args)
                    self.publish_status(f"Validation failed: {errors}")
                    break

                # Safety transforms
                if tool == "go_to":
                    args = clamp_go_to_args(args, self.bounds_min, self.bounds_max)

                # Execute
                self.get_logger().info(f"Executing tool={tool} args={args} reason={reason}")
                result = await self.execute_tool(tool, args)

                self.logger_jsonl.log("tool_result", tool=tool, args=args, result=result)
                self.publish_status(json.dumps({"tool": tool, "ok": result.get("ok", False), "result": result}))

                if not result.get("ok", False):
                    self.get_logger().warn(f"Tool failed: {result.get('error','unknown')}")
                    break

                # Update minimal state for compound commands
                if ("then" in goal.lower() or "and" in goal.lower()) and "square" in goal.lower() and tool == "go_to":
                    state["phase"] = "after_goto"
                else:
                    break

        finally:
            self._busy = False

    async def execute_tool(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.tool_registry.has(tool):
            return await self.tool_registry.get(tool)(args)
        return {"ok": False, "error": f"Unknown tool: {tool}"}

    def publish_status(self, text: str) -> None:
        self.pub.publish(String(data=text))

def main():
    rclpy.init()
    node = AgentNode()

    # Ensure asyncio event loop integrates with rclpy spinning
    loop = asyncio.get_event_loop()

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            loop.run_until_complete(asyncio.sleep(0))
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
