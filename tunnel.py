#!/usr/bin/env python3
import configparser
import select
import socket
import ssl
import threading
import time
from pathlib import Path
from inject import injector

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "settings.ini"
LOG = ROOT / "logs.txt"
LOG_LOCK = threading.Lock()

G='\033[32m'; O='\033[33m'; GR='\033[37m'; R='\033[31m'

class Tun(injector):
    def __init__(self):
        self.localip = '127.0.0.1'
        self.LISTEN_PORT = 9092

    def conf(self):
        config = configparser.ConfigParser()
        with SETTINGS.open() as f:
            config.read_file(f)
        return config

    def log(self, message):
        now = time.strftime('%H:%M:%S')
        with LOG_LOCK, LOG.open('a') as f:
            f.write(f'[{now}] : {message}\n')
            f.flush()

    def proxy(self, config, fallback_host, fallback_port):
        host = config.get('config', 'proxyip', fallback='').strip()
        port = config.get('config', 'proxyport', fallback='').strip()
        if not host or not port:
            return fallback_host, int(fallback_port)
        return host, int(port)

    @staticmethod
    def parse_connect(request):
        first = request.splitlines()[0].split()
        if len(first) < 2 or first[0].upper() != 'CONNECT':
            raise ValueError('Expected an HTTP CONNECT request')
        target = first[1]
        host, port = target.rsplit(':', 1)
        return host.strip('[]'), int(port)

    def relay(self, client, remote):
        try:
            while True:
                readable, _, exceptional = select.select([client, remote], [], [client, remote], 30)
                if exceptional:
                    break
                if not readable:
                    continue
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (remote if source is client else client).sendall(data)
        finally:
            client.close()
            remote.close()

    def destination(self, client, address):
        remote = None
        try:
            self.log(f'{G}<#> Client {address[1]} received!{GR}')
            client.settimeout(15)
            request = client.recv(16384).decode('iso-8859-1', errors='replace')
            host, port = self.parse_connect(request)
            config = self.conf()
            mode = config.getint('mode', 'connection_mode')
            connect_host, connect_port = self.proxy(config, host, port)

            remote = socket.create_connection((connect_host, connect_port), timeout=20)
            self.log(f'{G}connected to {connect_host}:{connect_port}{GR}')

            if mode in (2, 3):
                sni = config.get('sni', 'server_name').strip()
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # Compatibility with the original project. Prefer certificate
                # verification when your TLS endpoint has a valid certificate.
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                remote = context.wrap_socket(remote, server_hostname=sni)

            if mode == 0:
                # True direct mode: do not send an HTTP payload to an SSH server.
                client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            elif mode == 2:
                client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            else:
                injector.connection(self, client, remote, str(host), str(port))

            client.settimeout(None)
            remote.settimeout(None)
            self.relay(client, remote)
        except Exception as exc:
            self.log(f'{R}Tunnel error: {type(exc).__name__}: {exc}{GR}')
            try:
                client.close()
            except Exception:
                pass
            if remote is not None:
                try:
                    remote.close()
                except Exception:
                    pass

    def create_connection(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.localip, self.LISTEN_PORT))
            sock.listen(128)
        except OSError as exc:
            self.log(f'{R}Cannot listen on {self.localip}:{self.LISTEN_PORT}: {exc}{GR}')
            sock.close()
            return 1

        self.log(f'Waiting for incoming connection to : {self.localip}:{self.LISTEN_PORT}')
        try:
            while True:
                client, address = sock.accept()
                threading.Thread(target=self.destination, args=(client, address), daemon=True).start()
        except KeyboardInterrupt:
            return 0
        finally:
            sock.close()

if __name__ == '__main__':
    raise SystemExit(Tun().create_connection() or 0)
