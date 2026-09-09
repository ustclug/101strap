FROM ubuntu:26.04@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b AS image

ARG CACHE_EPOCH=0
ARG BUILD_MIRROR_MODE=ustc
RUN test -n "$CACHE_EPOCH" && case "$BUILD_MIRROR_MODE" in ustc|upstream) ;; *) exit 1 ;; esac && \
    if [ "$BUILD_MIRROR_MODE" = ustc ]; then sed -Ei 's@(archive|security)\.ubuntu\.com/ubuntu/?@mirrors.ustc.edu.cn/ubuntu@g; s@ports\.ubuntu\.com/ubuntu-ports/?@mirrors.ustc.edu.cn/ubuntu-ports@g' /etc/apt/sources.list.d/ubuntu.sources; fi && \
    apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install --no-install-recommends parted udev dosfstools e2fsprogs debootstrap qemu-utils ca-certificates && \
    apt-get clean

WORKDIR /srv
CMD ["/bin/bash", "/srv/image/build.sh"]

FROM image AS open-vmdk-build
RUN apt-get update && \
    apt-get -y install --no-install-recommends build-essential curl zlib1g-dev && \
    apt-get clean

# Pin the upstream source revision and verify the downloaded archive.
RUN curl -fL https://codeload.github.com/vmware/open-vmdk/tar.gz/f0c7cec4e4eb43053aae48fa633de1f172335842 -o /tmp/open-vmdk.tar.gz && \
    echo '2b1a51e634b18c419a5a2599eff56ecb1066305645733f3575f716fe0f7e1965  /tmp/open-vmdk.tar.gz' | sha256sum -c - && \
    mkdir /tmp/open-vmdk && \
    tar -xzf /tmp/open-vmdk.tar.gz --strip-components=1 -C /tmp/open-vmdk && \
    make -C /tmp/open-vmdk/vmdk

FROM image AS exporter
COPY --from=open-vmdk-build /tmp/open-vmdk/build/vmdk/vmdk-convert /usr/local/bin/vmdk-convert
COPY --from=open-vmdk-build /tmp/open-vmdk/ova-compose/ova-compose.py /usr/local/bin/ova-compose
COPY --from=open-vmdk-build /tmp/open-vmdk/LICENSE /tmp/open-vmdk/NOTICE /usr/local/share/licenses/open-vmdk/
RUN apt-get update && \
    apt-get -y install --no-install-recommends virtualbox python3-yaml python3-lxml && \
    apt-get clean
