#!/bin/bash

# Ensure local directories for outputs and models exist on the host to avoid docker creating them as root
mkdir -p gazebo9/catkin_ws/src/nao_explauto/python/output
mkdir -p gazebo9/catkin_ws/src/nao_explauto/python/models

# Allow GUI / X11 connection on the host
echo "Enabling local X11 connections..."
xhost +local:root

# Build the Docker image
echo "Building the Docker image nao-gazebo-skin..."
docker build -t nao-gazebo-skin .

# Run the container with:
# - GUI forwarding: DISPLAY environment variable, X11 unix socket sharing
# - Hardware GPU acceleration: mount /dev/dri (Intel/AMD/generic) and pass NVIDIA environment variables if available
# - Network: net=host and ipc=host for optimal ROS communication and Gazebo speed
# - Volume mounts: link host output and models directories to persist experiment results
echo "Running the container..."
docker run -it --rm \
  --net=host \
  --ipc=host \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --device /dev/dri:/dev/dri \
  -v "$(pwd)/gazebo9/catkin_ws/src/nao_explauto/python/output:/catkin_ws/src/nao_explauto/python/output" \
  -v "$(pwd)/gazebo9/catkin_ws/src/nao_explauto/python/models:/catkin_ws/src/nao_explauto/python/models" \
  nao-gazebo-skin
