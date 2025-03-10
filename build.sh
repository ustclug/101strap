sudo modprobe -r nbd
sudo modprobe nbd
sudo rm -rf ./build101
mkdir -p ./build101
docker build -t local/101strap .
docker run -it --privileged --rm -v $(pwd):/srv:ro -v $(pwd)/build101:/target -v /usr/lib/ovftool:/Ovftool:ro -v /dev:/dev -e NBD=/dev/nbd0 local/101strap:latest
