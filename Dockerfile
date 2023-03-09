FROM ubuntu:22.04

RUN sed -Ei 's/(archive|security)\.ubuntu\.com/mirrors.ustc.edu.cn/g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install --no-install-recommends parted udev dosfstools debootstrap arch-install-scripts && \
    apt-get clean

CMD ["/bin/bash", "/srv/101strap"]

