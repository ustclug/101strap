# 101strap

## Introduction

This project aims to automate the generation of XUbuntu, which will be used as a example in [linux101]([欢迎 - Linux 101 (ustc.edu.cn)](https://101.lug.ustc.edu.cn/)).

## Build

```shell
sudo modprobe nbd
docker build -t local/101strap .
docker run -it --privileged --rm -v $(pwd):/srv:ro -v ~/tmp/101:/target -v /usr/lib/ovftool:/Ovftool -v /dev:/dev -e NBD=/dev/nbd0 local/101strap:latest
```

**Note:**

+ The generation order for this project is: **qcow2 -> vmdk/vdi -> ova**. All of the processes are **automated**, and all you need to do is to run the three commands mentioned. However, before that, you need to install the [ovftool](https://developer.vmware.com/web/tool/4.4.0/ovf). Please note that this project generates **XUbuntu 22.04**, and if you wish to generate other versions of XUbuntu, you need to modify some content in the scripts.

+ If there is any problems exporting to the ova file, you can also choose to manually export it using vmdk/vdi. You need to import the VMDK into VMware Workstation and configure it accordingly, import the VDI into VirtualBox and configure it accordingly, and then export each as an OVA.

+ If you only want to automate the process of generating a .qcow2 image, you can modify the last line of the Dockerfile to: 

  ```dockerfile
  CMD ["/bin/bash", "/srv/101strap_img"]
  ```

## Run

You can test the generated qcow2 file locally using the following command.

```shell
qemu-system-x86_64 -machine accel=kvm -m 1024m -hda ./root.qcow2 -bios /usr/share/ovmf/x64/OVMF.fd -netdev user,id=net101 -device e1000,netdev=net101
```
