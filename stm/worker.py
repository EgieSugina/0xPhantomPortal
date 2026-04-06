import os
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal

from .config import KIND_LOCAL, KIND_REMOTE, KIND_SOCKS


class TunnelWorker(QObject):
    status_changed = Signal(str, str)
    log_message = Signal(str, str)

    def __init__(self, tunnel: dict, password: str = ""):
        super().__init__()
        self.tunnel = tunnel
        self.tid = tunnel["id"]
        self.password = password
        self._running = False
        self._process = None
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self.status_changed.emit(self.tid, "disconnected")
        self.log_message.emit(self.tid, "⛔ Tunnel stopped by user.")

    def _connect_log_summary(self, t: dict, use_pw: bool) -> list[str]:
        name = t.get("name") or t.get("host", "?")
        user = (t.get("username") or "").strip()
        host = t.get("host", "?")
        ssh_port = int(t.get("ssh_port", 22))
        target = f"{user}@{host}" if user else host
        kind = t.get("kind", KIND_SOCKS)
        if t.get("identity_file"):
            auth = f"identity file: {t['identity_file']}"
        elif use_pw:
            auth = "password via sshpass (SSHPASS)"
        else:
            auth = "default (SSH agent / ~/.ssh keys / prompt)"

        lines = [
            f"🔌 Connecting — {name}  [{kind}]",
            f"   SSH target: {target}:{ssh_port}",
            f"   Auth: {auth}",
        ]
        if kind == KIND_SOCKS:
            lp = int(t.get("local_port", 1080))
            lines.insert(2, f"   Local SOCKS5: 127.0.0.1:{lp}  (-D dynamic forward)")
        elif kind == KIND_LOCAL:
            bind = (t.get("local_bind") or "127.0.0.1").strip() or "127.0.0.1"
            lp = int(t.get("local_port", 0))
            rh = (t.get("remote_host") or "127.0.0.1").strip() or "127.0.0.1"
            rp = int(t.get("remote_port", 0))
            lines.insert(2, f"   Local forward (-L): {bind}:{lp} → {rh}:{rp} (via server)")
        else:
            rb = (t.get("remote_bind") or "").strip()
            rp = int(t.get("remote_port", 0))
            lh = (t.get("local_host") or "127.0.0.1").strip() or "127.0.0.1"
            lp = int(t.get("local_port", 0))
            rspec = f"{rb}:{rp}" if rb else str(rp)
            lines.insert(2, f"   Remote forward (-R): server {rspec} → {lh}:{lp} (this machine)")
        return lines

    def _run(self):
        retry_delay = 2
        while self._running:
            self.status_changed.emit(self.tid, "connecting")
            t = self.tunnel
            use_pw = bool(self.password) and not t.get("identity_file")
            cmd = self._build_cmd(t, use_pw)

            for line in self._connect_log_summary(t, use_pw):
                self.log_message.emit(self.tid, line)
            self.log_message.emit(self.tid, f"   Shell: {' '.join(cmd)}")

            try:
                env = os.environ.copy()
                if use_pw:
                    env["SSHPASS"] = self.password
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                )
                self.status_changed.emit(self.tid, "connected")
                self.log_message.emit(self.tid, f"✅ SSH session up — PID {self._process.pid}")
                for line in self._process.stdout:
                    line = line.strip()
                    if line:
                        self.log_message.emit(self.tid, f"   {line}")
                    if not self._running:
                        break
                self._process.wait()
                rc = self._process.returncode
            except FileNotFoundError as e:
                missing = "sshpass" if "sshpass" in str(e) else "ssh"
                self.log_message.emit(
                    self.tid, f"❌ '{missing}' not found. Run: sudo apt install {missing}"
                )
                self._running = False
                self.status_changed.emit(self.tid, "disconnected")
                return
            except Exception as e:
                self.log_message.emit(self.tid, f"❌ Error: {e}")
                rc = -1

            if not self._running:
                break

            self.status_changed.emit(self.tid, "disconnected")
            self.log_message.emit(
                self.tid, f"⚠️  Disconnected (exit {rc}). Reconnecting in {retry_delay}s…"
            )
            for _ in range(retry_delay * 10):
                if not self._running:
                    break
                time.sleep(0.1)
            retry_delay = min(retry_delay * 2, 60)

    @staticmethod
    def _build_cmd(t: dict, use_password: bool) -> list:
        cmd = []
        if use_password:
            cmd += ["sshpass", "-e"]
        cmd += ["ssh"]
        kind = t.get("kind", KIND_SOCKS)
        if kind == KIND_SOCKS:
            cmd += ["-D", str(t["local_port"])]
        elif kind == KIND_LOCAL:
            bind = (t.get("local_bind") or "127.0.0.1").strip() or "127.0.0.1"
            cmd += ["-L", f"{bind}:{int(t['local_port'])}:{(t.get('remote_host') or '127.0.0.1').strip() or '127.0.0.1'}:{int(t['remote_port'])}"]
        else:
            rb = (t.get("remote_bind") or "").strip()
            rp = int(t["remote_port"])
            lh = (t.get("local_host") or "127.0.0.1").strip() or "127.0.0.1"
            lp = int(t["local_port"])
            spec = f"{rb}:{rp}:{lh}:{lp}" if rb else f"{rp}:{lh}:{lp}"
            cmd += ["-R", spec]
        cmd += ["-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3"]
        cmd += ["-o", "ExitOnForwardFailure=yes", "-o", "StrictHostKeyChecking=no"]
        cmd += ["-o", "BatchMode=no", "-N", "-T"]
        if t.get("ssh_port", 22) != 22:
            cmd += ["-p", str(t["ssh_port"])]
        if t.get("identity_file"):
            cmd += ["-i", t["identity_file"]]
        cmd += ["-v"]
        user = t.get("username", "")
        cmd.append(f"{user}@{t['host']}" if user else t["host"])
        return cmd
