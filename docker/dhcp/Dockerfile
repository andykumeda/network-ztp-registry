FROM alpine:3.19

RUN apk add --no-cache dnsmasq iproute2

COPY dnsmasq.conf.tpl /etc/dnsmasq.conf.tpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 67/udp

ENTRYPOINT ["/entrypoint.sh"]
