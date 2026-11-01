"""No external network access from the application process.

The model runs in a separate local Ollama server with cloud features disabled.
Model downloads are an explicit setup operation, never a document operation.
"""
import ipaddress
import socket

class LocalOnlyError(PermissionError):
    pass

def local_host(host):
    if host in ('localhost', b'localhost'):
        return True
    try:
        return ipaddress.ip_address(host.decode() if isinstance(host, bytes) else host).is_loopback
    except (ValueError, TypeError):
        return False

def install_network_guard():
    if getattr(socket, '_private_contracts_guard', False):
        return
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_lookup = socket.getaddrinfo
    real_sendto = socket.socket.sendto

    def check(address):
        if isinstance(address, tuple) and not local_host(address[0]):
            raise LocalOnlyError('External connections are disabled in Private Contracts.')

    def connect(self, address):
        check(address)
        return real_connect(self, address)

    def connect_ex(self, address):
        check(address)
        return real_connect_ex(self, address)

    def lookup(host, *args, **kwargs):
        if host is not None and not local_host(host):
            raise LocalOnlyError('External DNS lookups are disabled in Private Contracts.')
        return real_lookup(host, *args, **kwargs)

    def sendto(self, data, *args):
        if args:
            check(args[-1])
        return real_sendto(self, data, *args)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = lookup
    socket._private_contracts_guard = True
