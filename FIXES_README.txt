FIXED FILES

Copy runvpn.sh, proxification.sh, tunnel.py, ssh.py, inject.py, and pidkill.py into the original project directory. Keep your existing settings.ini and credentials.

Then run:
  chmod +x runvpn.sh proxification.sh
  sudo ./runvpn.sh

Main corrections:
- clears stale logs and old screen/process/TUN state before each run
- uses separate screen session names
- waits for real SSH authentication instead of a fixed 10-second delay
- direct mode relays SSH without incorrectly injecting an HTTP CONNECT request into the SSH server
- does not kill every Python process
- prevents TUN routing loops and avoids flushing the entire firewall
- uses valid resolv.conf syntax
- restores routes and DNS when tun2socks exits
- reports real connection errors instead of always blaming settings.ini

Use only on a network and server you are authorized to use. A successful netcat connection means only that TCP connected; the run is successful only when the log says CONNECTED SUCCESSFULLY and port 1080 is listening.
