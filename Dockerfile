FROM osrf/ros:melodic-desktop-full

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV MPLBACKEND=Agg

# Install system dependencies & configure debconf to auto-accept the license for ros-nao-meshes
RUN apt-get update && apt-get install -y debconf && \
    echo "ros-nao-meshes ros-nao-meshes/accepted-ros-nao-meshes boolean true" | debconf-set-selections && \
    apt-get install -y \
    git \
    unzip \
    scrot \
    curl \
    python-pip \
    python-setuptools \
    python-dev \
    ros-melodic-nao-meshes \
    ros-melodic-gazebo-ros-control \
    ros-melodic-gazebo-ros \
    ros-melodic-transmission-interface \
    ros-melodic-joint-limits-interface \
    ros-melodic-rqt-gui \
    ros-melodic-rqt-gui-py \
    mesa-utils \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    python-tk \
    && rm -rf /var/lib/apt/lists/*

# Set up the catkin workspace directory
WORKDIR /catkin_ws

# Copy the prepared catkin workspace from host
COPY gazebo9/catkin_ws/src ./src

# Install any missing dependencies using rosdep
RUN /bin/bash -c "source /opt/ros/melodic/setup.bash && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y || true"

# Compile the custom contactsensor plugin
WORKDIR /catkin_ws/src/gazebo_contactsensor_plugin
RUN /bin/bash -c "source /opt/ros/melodic/setup.bash && mkdir -p build && cd build && cmake .. && make"

# Build the Catkin workspace
WORKDIR /catkin_ws
RUN /bin/bash -c "source /opt/ros/melodic/setup.bash && catkin_make"

# Install legacy Python packages for explauto
# We pin packages to versions compatible with Python 2.7
# Install explauto from git source to avoid use_2to3 build issues
RUN pip install --upgrade "pip<21.0" "setuptools<45.0" && \
    pip install "numpy<1.17" "scipy<1.3" "matplotlib<3.0" "scikit-learn<0.21" "cma<3.0" && \
    pip install git+https://github.com/flowersteam/explauto.git

# Copy and run the patch script to apply thesis modifications to explauto
# (uses pip show to locate files, no import needed)
COPY patch_explauto.py /patch_explauto.py
# Copy the new Adaptive Linear Interest Model so the patch script can install it
COPY adaptive_linear_interest.py /adaptive_linear_interest.py
RUN python /patch_explauto.py

# Configure the shell to auto-source ROS environments on login
RUN echo "source /opt/ros/melodic/setup.bash" >> /root/.bashrc && \
    echo "source /catkin_ws/devel/setup.bash" >> /root/.bashrc

# Copy auxiliary launch and config files to /catkin_ws
COPY gazebo9/misc/launch-naoqi.sh ./launch-naoqi.sh
COPY gazebo9/misc/rqt_ez_publisher.yaml ./rqt_ez_publisher.yaml
RUN chmod +x ./launch-naoqi.sh

# Set working directory to the python experiment scripts folder
WORKDIR /catkin_ws/src/nao_explauto/python

CMD ["/bin/bash"]
