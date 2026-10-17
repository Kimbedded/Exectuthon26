#!/bin/sh
# Run on VENTUNO Q. Uses the installed Arduino core, Router and OpenOCD.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
device_dir=/home/arduino/idk-button
mkdir -p "$device_dir/IdkButton"
cp "$source_dir/IdkButton/IdkButton.ino" "$device_dir/IdkButton/IdkButton.ino"
cp "$source_dir/flash.cfg" "$device_dir/flash.cfg"
arduino-cli compile --fqbn arduino:zephyr:ventunoq --jobs 2 --build-path "$device_dir/build" "$device_dir/IdkButton"
arduino-router-cli '$/serial/close' /dev/ttySTM0
trap 'arduino-router-cli '\''$/serial/open'\'' /dev/ttySTM0' EXIT
/opt/openocd/bin/openocd -f "$device_dir/flash.cfg"
