#!/bin/sh
# Run as server administrator once. Grants only UIProof MCP + one loopback tunnel.
set -eu
command -v sudo >/dev/null
id forge-uiproof >/dev/null 2>&1 || useradd -m -s /bin/sh forge-uiproof
install -d -m 700 /opt/forge/runtime/uiproof-ssh
if [ ! -f /opt/forge/runtime/uiproof-ssh/id_ed25519 ]; then
  ssh-keygen -q -t ed25519 -N '' -f /opt/forge/runtime/uiproof-ssh/id_ed25519
fi
install -d -m 700 -o forge-uiproof -g forge-uiproof /home/forge-uiproof/.ssh
printf 'command="/usr/bin/sudo -n /opt/uiproof/bin/mcp",restrict,port-forwarding,permitlisten="127.0.0.1:49318" ' > /home/forge-uiproof/.ssh/authorized_keys
cat /opt/forge/runtime/uiproof-ssh/id_ed25519.pub >> /home/forge-uiproof/.ssh/authorized_keys
chown forge-uiproof:forge-uiproof /home/forge-uiproof/.ssh/authorized_keys
chmod 600 /home/forge-uiproof/.ssh/authorized_keys
printf 'forge-uiproof ALL=(root) NOPASSWD: /opt/uiproof/bin/mcp\n' > /etc/sudoers.d/forge-uiproof
chmod 440 /etc/sudoers.d/forge-uiproof
visudo -cf /etc/sudoers.d/forge-uiproof
cat > /opt/forge/runtime/uiproof-ssh/config <<'CONFIG'
Host yun2-uiproof
  HostName host.docker.internal
  HostKeyAlias yun2-loopback
  User forge-uiproof
  IdentityFile /home/forge/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking yes
  UserKnownHostsFile /home/forge/.ssh/known_hosts
CONFIG
printf 'yun2-loopback ' > /opt/forge/runtime/uiproof-ssh/known_hosts
cat /etc/ssh/ssh_host_ed25519_key.pub >> /opt/forge/runtime/uiproof-ssh/known_hosts
chmod 600 /opt/forge/runtime/uiproof-ssh/config /opt/forge/runtime/uiproof-ssh/known_hosts
chown -R 10001:10001 /opt/forge/runtime/uiproof-ssh
install -d -o 10001 -g 10001 -m 700 /opt/forge/data
