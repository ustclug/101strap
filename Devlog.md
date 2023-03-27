# XUbuntu22.04

## 方案一：mkosi

`mkosi` stands for _Make Operating System Image_, and is a tool for generating an OS tree or image that can be booted.

前置工作：[xuao1/mkosi: mkosi (github.com)](https://github.com/xuao1/mkosi)

目前存在的问题有：

- 启动后打不开终端：尝试安装 xterm 解决

  - 安装后，因为 xfec4 启动出了问题，所以又额外安装了 xinit 和 xserver-xorg，可以成功启动终端，但是不知道解决问题的是哪一个

- qemu 启动后 apt 出现错误.

​ 注：该错误在 systemd-nspawn 启动时没有，目前判断是缺少必要的网络包

## 方案二：采用现有镜像

使用现有 xubuntu22.04 镜像，手动安装。

VirtualBox 和 VMware 两个软件均支持自动导出 ova 文件

删除 snap

硬盘压缩：需要先做 0 填充，再进行硬盘压缩。VMware Workstation 支持直接压缩，VirtualBox 需要在其安装路径下使用 VBoxManage 进行压缩。

## 方案三：101strap

**最终采用**

### 概述

Docker 部署，生成基于 Ubuntu22.04 的镜像，使用脚本安装配置包含 Xfce4 在内的各种安装包。

简单来说，先生成一个 qcow2 格式的镜像文件，分别将其转化为 vmdk 和 vdi 硬盘文件，前者在 Vmware 中使用，后者在 VirtualBox 中。最后分别做一些基本配置，导出为两个平台分别可用的 OVA 文件。

对于本项目的使用：

我们致力于全部流程均为自动化实现，理论上只需要执行 README 中 Build 下的三条指令即可。但在那之前，你需要首先安装 [ovftool](https://developer.vmware.com/web/tool/4.4.0/ovf)，并将其放在 /usr/local.

注意到，本项目是自动化生成 XUbuntu22.04，所以如果之后希望复用本项目生成其他版本的 XUbuntu，你需要更改脚本中的部分内容，包括但不限于 “22.04” 字样。

接下来是关于开发流程的记录。

### 生成 qcow2

这一部分内容主要由 [taoky](https://github.com/taoky) 和 [RTXUX](https://github.com/RTXUX) 完成，全部内容均在 101strap_img 文件中。

该脚本创建和配置了 XUbuntu 22.04。主要功能概括如下：

1. 检查工作空间是否存在，用户是否为 root，设备是否为块设备。
2. 创建一个 5GB 的 qcow2 格式的磁盘镜像，并将其挂载到 NBD 设备。
3. 使用 parted 工具创建一个 GPT 分区表，并创建一个 256MB 的 EFI 分区和一个用于 Linux 系统的 ext4 分区。
4. 对 EFI 分区和 root 分区进行格式化。
5. 挂载 EFI 分区和 rootfs 分区。
6. 使用 debootstrap 安装 Ubuntu 22.04 的基本系统。
7. 挂载 proc、sys 和 dev 文件系统。
8. 修改 apt 源为中国科技大学镜像站点。
9. 安装基本的桌面应用程序、语言包和输入法。
10. 更新软件包。
11. 调整 XFCE 桌面环境的默认设置。
12. 配置用户、主机名和时区。
13. 生成语言环境。
14. 添加新用户并设置密码。
15. 设置 fstab 文件以挂载根文件系统和 EFI 分区。
16. 配置网络管理器来管理网络。
17. 安装内核、GRUB 引导加载器和其他必要的工具。
18. 配置 GRUB 引导加载器。
19. 清理不必要的软件包和缓存。
20. 对文件系统进行优化。

通过该脚本，可获得 root.qcow2

### 导出为 OVA 文件

这一部分内容主要由 [xuao1](https://github.com/xuao1) 完成。全部内容均在 101strap_disk.

该脚本主要用于将一个 QEMU QCOW2 格式的虚拟磁盘镜像文件（root.qcow2）转换为 VMware 和 VirtualBox 所支持的格式，并分别配置虚拟机，最后分别导出为 OVA 文件。

主要功能概括如下：

1.  将 root.qcow2 转换成 vmdk 和 vdi 文件，前者用于 VMware，后者用于 VirtualBox。
2.  为 VMware 创建一个.vmx 文件，定义虚拟机的各种配置信息，如内存、CPU、硬盘等。
3.  使用 ovftool 将 VMware 的虚拟机配置文件导出为 OVA 格式。
4.  为 VirtualBox 创建一个虚拟机，将前面转换好的 VDI 磁盘镜像关联到虚拟机，指定操作系统类型。
5.  配置 VirtualBox 虚拟机的其他设置，如内存、CPU、启动顺序、固件类型、USB 设置等。
6.  使用 VBoxManage 将 VirtualBox 虚拟机导出为 OVA 格式，便于分发和部署。

### 补充

关于 VirtualBox 全部配置信息，列在下面：

可以按照以下顺序来生成（默认已经创建好了 root.vdi）：

1. 安装 VBoxManage

2. 使用 VBoxManage 创建一个新的虚拟机，指定操作系统版本，并将 VDI 文件添加为虚拟硬盘

   ```shell
   VBoxManage createvm --name "My_VM" --ostype "Ubuntu_64" --register
   VBoxManage storagectl "My_VM" --name "SATA Controller" --add sata --controller IntelAHCI
   VBoxManage storageattach "My_VM" --storagectl "SATA Controller" --port 0 --device 0 --type hdd --medium /path/to/your/vmdk_file.vdi
   ```

3. 配置虚拟机：

   - 设置内存

     ```shell
     VBoxManage modifyvm "My_VM" --memory 1024
     ```

   - 设置 CPU 数量

     ```shell
     VBoxManage modifyvm "My_VM" --cpus 1
     ```

   - 更改虚拟机启动时的引导顺序（Boot Order）

     ```shell
     VBoxManage modifyvm "My_VM" --boot1 disk --boot2 none --boot3 none --boot4 none
     ```

   - 启用硬件时钟 UTC 时间模式

     ```shell
     VBoxManage modifyvm "My_VM" --rtcuseutc on
     ```

   - 启用 EFI：

     ```shell
     VBoxManage modifyvm "My_VM" --firmware efi
     ```

   - 配置虚拟机的 HID（Human Interface Device）：

     ```shell
     VBoxManage modifyvm "My_VM" --mouse usbtablet
     ```

   - 改显存为 32MB:

     ```shell
     VBoxManage modifyvm "My_VM" --vram 32
     ```

   - 启动网卡 1，启用网络连接，连接方式：NAT

     ```shell
     VBoxManage modifyvm "My_VM" --nic1 nat
     ```

   - 启用 USB 控制器，USB 2.0

     ```shell
     VBoxManage modifyvm "My_VM" --usb on
     VBoxManage modifyvm "My_VM" --usbehci on
     ```

   - 关闭 PAE（Physical Address Extension）：

     ```shell
     VBoxManage modifyvm "My_VM" --pae off
     ```

   - 启用长模式（Long Mode）

     ```shell
     VBoxManage modifyvm "My_VM" --longmode on
     ```

   - 启用 X2APIC 支持：

     ```shell
     VBoxManage modifyvm "My_VM" --x2apic on
     ```

   - 启用硬件虚拟化大页面（Hardware Virtualization Large Pages）支持：

     ```shell
     VBoxManage modifyvm "My_VM" --largepages on
     ```

4. 将虚拟机导出为 OVA 文件:

   ```shell
   VBoxManage export "My_VM" --output /path/to/output_file.ova
   ```
