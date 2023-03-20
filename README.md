# 101strap

## Build

```shell
sudo modprobe nbd
docker build -t local/101strap .
docker run -it --privileged --rm -v $(pwd):/srv:ro -v ~/tmp/101:/target -v /usr/lib/ovftool:/Ovftool -v /dev:/dev -e NBD=/dev/nbd0 local/101strap:latest
```

**Note:**

+ If you need to automate the process of generating an image, compressing it, and converting it to an VMDK/VDI file, you can run the above commands directly. 

+ If you only want to automate the process of generating a .qcow2 image, you can modify the last line of the Dockerfile to: 

  ```dockerfile
  CMD ["/bin/bash", "/srv/101strap_img"]
  ```

## Run

```shell
qemu-system-x86_64 -machine accel=kvm -m 1024m -hda ./root.qcow2 -bios /usr/share/ovmf/x64/OVMF.fd -netdev user,id=net101 -device e1000,netdev=net101
```

## Export

Finally, you will need to manually import the VMDK into VMware Workstation and configure it accordingly, import the VDI into VirtualBox and configure it accordingly, and then export each as an OVA.
