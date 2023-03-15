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

## Note

If you need to automate the process of generating an image, compressing it, and converting it to an OVA file, you can run the above command directly. 
If you only want to automate the process of generating a .img image, you can modify the last line of the Dockerfile to: 
```
CMD ["/bin/bash", "/srv/101strap_img"]. 
```
If you only want to compress and convert the .img image to an OVA file, which is usually needed during debugging, you can modify the last line of the Dockerfile to: 
```
CMD ["/bin/bash", "/srv/101strap_convert"].
```
