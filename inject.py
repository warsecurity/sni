#!/usr/bin/env python3
import configparser
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'settings.ini'
LOG = ROOT / 'logs.txt'

class injector:
    def conf(self):
        config = configparser.ConfigParser()
        with SETTINGS.open() as f:
            config.read_file(f)
        return config

    def getpayload(self, config):
        return config.get('config', 'payload')

    def conn_mode(self, config):
        return config.getint('mode', 'connection_mode')

    def auto_rep(self, config):
        return config.getboolean('config', 'auto_replace', fallback=True)

    def payloadformating(self, payload, host, port):
        port = str(port)
        replacements = {
            '[crlf]': '\r\n', '[crlf*2]': '\r\n\r\n', '[cr]': '\r', '[lf]': '\n',
            '[lfcr]': '\n\r', '[protocol]': 'HTTP/1.0', '[ua]': 'Dalvik/2.1.0',
            '[raw]': f'CONNECT {host}:{port} HTTP/1.0\r\n\r\n',
            '[real_raw]': f'CONNECT {host}:{port} HTTP/1.0\r\n\r\n',
            '[netData]': f'CONNECT {host}:{port} HTTP/1.0',
            '[realData]': f'CONNECT {host}:{port} HTTP/1.0',
            '[method]': 'CONNECT', '[ssh]': f'{host}:{port}',
            '[host_port]': f'{host}:{port}', '[host]': host, '[port]': port,
            '[auth]': '', 'mip': '127.0.0.1',
            '[split_delay]': '[delay_split]', '[split_instant]': '[instant_split]',
        }
        for old, new in replacements.items():
            payload = payload.replace(old, new)
        return payload

    @staticmethod
    def _send_parts(sock, payload):
        markers = {
            '[split]': 0.5,
            '[delay_split]': 1.5,
            '[instant_split]': 0.0,
        }
        for marker, delay in markers.items():
            if marker in payload:
                parts = payload.split(marker)
                for index, part in enumerate(parts):
                    if part:
                        sock.sendall(part.encode())
                    if index < len(parts) - 1:
                        time.sleep(delay)
                return

        if '[repeat_split]' in payload or '[x-split]' in payload:
            marker = '[repeat_split]' if '[repeat_split]' in payload else '[x-split]'
            parts = payload.split(marker, 1)
            if len(parts) == 2:
                sock.sendall(parts[0].encode())
                sock.sendall(parts[0].encode())
                sock.sendall(parts[1].encode())
                return

        if '[reverse_split]' in payload:
            parts = payload.split('[reverse_split]', 1)
            if len(parts) == 2:
                sock.sendall(parts[0].encode())
                sock.sendall(parts[1].encode())
                sock.sendall(parts[1].encode())
                return

        if '[split-x]' in payload:
            parts = payload.split('[split-x]', 1)
            if len(parts) == 2:
                sock.sendall(parts[0].encode())
                sock.sendall(parts[1].encode())
                time.sleep(0.5)
                sock.sendall(parts[1].encode())
                return

        sock.sendall(payload.encode())

    def connection(self, client, remote, host, port):
        config = self.conf()
        payload = self.payloadformating(self.getpayload(config), host, str(port))
        self._send_parts(remote, payload)

        if self.auto_rep(config):
            # Avoid hanging forever when the peer accepts TCP but returns no HTTP response.
            old_timeout = remote.gettimeout()
            remote.settimeout(15)
            try:
                response = remote.recv(4096)
                if not response:
                    raise ConnectionError('Remote endpoint closed after the payload')
                first_line = response.split(b'\n', 1)[0].strip()
                self.logs(f'Payload response: {first_line.decode("iso-8859-1", errors="replace")}')
            finally:
                remote.settimeout(old_timeout)

        client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')

    def logs(self, message):
        with LOG.open('a') as f:
            f.write(f'[{time.strftime("%H:%M:%S")}] : {message}\n')
