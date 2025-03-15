#!/bin/bash -ex

OVFTOOL_PATH=${OVFTOOL_PATH:-/usr/lib/ovftool}

sudo modprobe -r nbd
sudo modprobe nbd
sudo rm -rf ./build101
mkdir -p ./build101
sudo docker build -t local/101strap .
sudo docker run -it --privileged --rm -v "$(pwd):/srv:ro" -v "$(pwd)/build101:/target" -v "$OVFTOOL_PATH:/Ovftool:ro" -v /dev:/dev -e NBD=/dev/nbd0 local/101strap:latest
