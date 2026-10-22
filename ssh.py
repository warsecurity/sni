#!/usr/bin/env python3
import configparser
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'settings.ini'
LOG = ROOT / 'logs.txt'
G='\033[32m'; GR='\033[37m'; R='\033[31m'

class SSHRunner:
    def log(self, message):
        with LOG.open('a') as f:
            f.write(f'[{time.strftime("%H:%M:%S")}] : {message}\n')
            f.flush()

    def run(self, proxy_kind):
        cfg = configparser.ConfigParser()
        try:
            with SETTINGS.open() as f:
                cfg.read_file(f)
            host = cfg.get('ssh', 'host').strip()
            port = cfg.getint('ssh', 'port')
            username = cfg.get('ssh', 'username').strip()
            password = cfg.get('ssh', 'password')
        except Exception as exc:
            self.log(f'{R}SSH ERROR reading settings.ini: {exc}{GR}')
            return 1

        if not all((host, username, password)):
            self.log(f'{R}SSH ERROR: host, username or password is empty{GR}')
            return 1

        if proxy_kind == '1':
            proxy_command = 'corkscrew 127.0.0.1 9092 %h %p'
        else:
            proxy_command = 'nc -X CONNECT -x 127.0.0.1:9092 %h %p'

        command = [
            'sshpass', '-e', 'ssh',
            '-vv', '-N', '-D', '127.0.0.1:1080',
            '-p', str(port),
            '-o', f'ProxyCommand={proxy_command}',
            '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=20',
            '-o', 'ServerAliveCountMax=3',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f'{username}@{host}',
        ]
        env = os.environ.copy()
        env['SSHPASS'] = password

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env,
                                       text=True, errors='replace', bufsize=1)
            announced = False
            for raw in process.stdout:
                line = raw.strip()
                if not line:
                    continue
                if ('Authenticated to ' in line or
                    'Authentication succeeded' in line):
                    if not announced:
                        self.log('Authentication Completed')
                        self.log(f'{G}CONNECTED SUCCESSFULLY{GR}')
                        announced = True
                elif any(token in line for token in (
                    'Permission denied', 'Connection refused', 'Connection closed',
                    'Connection timed out', 'Could not request local forwarding',
                    'kex_exchange_identification')):
                    self.log(f'{R}{line}{GR}')
                elif any(token in line for token in (
                    'kex: algorithm:', 'kex: host key algorithm:',
                    'Server host key:', 'Remote protocol version')):
                    self.log(line)
            return process.wait()
        except Exception as exc:
            self.log(f'{R}SSH ERROR: {type(exc).__name__}: {exc}{GR}')
            return 1

if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else '1'
    raise SystemExit(SSHRunner().run(kind))
