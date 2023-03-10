# 101strap

## Build

```
docker build -t local/101strap .
docker run -it --privileged --rm -v $(pwd):/srv:ro -v ~/tmp/101:/target -v /dev:/dev local/101strap:latest
```

## Run

```
qemu-system-x86_64 -machine accel=kvm -m 1024m -hda ./root.img -bios /usr/share/ovmf/x64/OVMF.fd -netdev user,id=net101 -device e1000,netdev=net101
```
