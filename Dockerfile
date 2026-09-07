FROM ubuntu:26.04 AS image

ARG BUILD_MIRROR_MODE=ustc
RUN case "$BUILD_MIRROR_MODE" in ustc|upstream) ;; *) exit 1 ;; esac && \
    if [ "$BUILD_MIRROR_MODE" = ustc ]; then sed -Ei 's@(archive|security)\.ubuntu\.com/ubuntu/?@mirrors.ustc.edu.cn/ubuntu@g; s@ports\.ubuntu\.com/ubuntu-ports/?@mirrors.ustc.edu.cn/ubuntu-ports@g' /etc/apt/sources.list.d/ubuntu.sources; fi && \
    apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install --no-install-recommends parted udev dosfstools e2fsprogs debootstrap qemu-utils ca-certificates && \
    apt-get clean

WORKDIR /srv
CMD ["/bin/bash", "/srv/101strap"]

FROM image AS exporter
RUN apt-get update && \
    apt-get -y install --no-install-recommends virtualbox && \
    apt-get clean
