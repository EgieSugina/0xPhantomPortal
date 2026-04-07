import os
import posixpath
import socket
import stat
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import PARAMIKO_OK

if PARAMIKO_OK:
    import paramiko


def open_client_from_params(params):
    timeout = int(params.get("timeout", 8) or 8)
    if params.get("use_socks5"):
        sock = _open_socks5_socket(
            proxy_host=str(params.get("socks_host") or "127.0.0.1"),
            proxy_port=int(params.get("socks_port") or 1080),
            target_host=str(params["host"]),
            target_port=int(params["port"]),
            timeout=timeout,
        )
    else:
        sock = socket.create_connection((params["host"], params["port"]), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.banner_timeout = timeout
    transport.auth_timeout = timeout
    password = params.get("password") or None
    pkey = None
    if params.get("key_file"):
        pkey = paramiko.RSAKey.from_private_key_file(
            os.path.expanduser(params["key_file"]), password=password
        )
        password = None
    transport.connect(username=params["username"], password=password, pkey=pkey)
    return transport, paramiko.SFTPClient.from_transport(transport)


def _open_socks5_socket(
    proxy_host: str,
    proxy_port: int,
    target_host: str,
    target_port: int,
    timeout: int,
):
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    sock.settimeout(timeout)

    # Greeting: ver=5, nmethods=1, method=0(no-auth)
    sock.sendall(b"\x05\x01\x00")
    resp = _recv_exact(sock, 2)
    if resp[0] != 0x05:
        raise OSError("Invalid SOCKS5 proxy response.")
    if resp[1] == 0xFF:
        raise OSError("SOCKS5 proxy has no acceptable auth method (no-auth rejected).")
    if resp[1] != 0x00:
        raise OSError("SOCKS5 proxy requires auth. Only no-auth is supported.")

    host_bytes = target_host.encode("idna")
    if len(host_bytes) > 255:
        raise OSError("Target hostname too long for SOCKS5.")

    # CONNECT request: ver=5, cmd=1, rsv=0, atyp=3(domain), addr_len, addr, port
    req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + struct.pack(">H", int(target_port))
    sock.sendall(req)

    head = _recv_exact(sock, 4)
    if head[0] != 0x05:
        raise OSError("Invalid SOCKS5 connect reply.")
    if head[1] != 0x00:
        code = head[1]
        reasons = {
            0x01: "general SOCKS server failure",
            0x02: "connection not allowed by ruleset",
            0x03: "network unreachable",
            0x04: "host unreachable",
            0x05: "connection refused",
            0x06: "TTL expired",
            0x07: "command not supported",
            0x08: "address type not supported",
        }
        raise OSError(f"SOCKS5 connect failed ({code}): {reasons.get(code, 'unknown error')}")

    atyp = head[3]
    if atyp == 0x01:
        _recv_exact(sock, 4 + 2)  # ipv4 + port
    elif atyp == 0x03:
        ln = _recv_exact(sock, 1)[0]
        _recv_exact(sock, ln + 2)  # domain + port
    elif atyp == 0x04:
        _recv_exact(sock, 16 + 2)  # ipv6 + port
    else:
        raise OSError("SOCKS5 reply has unknown address type.")
    return sock


def _recv_exact(sock, size: int) -> bytes:
    out = b""
    while len(out) < size:
        chunk = sock.recv(size - len(out))
        if not chunk:
            raise OSError("SOCKS5 proxy closed connection unexpectedly.")
        out += chunk
    return out


def collect_upload_tasks(cwd: str, paths):
    dirs_to_create: set[str] = set()
    file_tasks: list[tuple[str, str]] = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            remote_root = posixpath.join(cwd, os.path.basename(p))
            dirs_to_create.add(remote_root)
            for root, dirs, files in os.walk(p):
                rel = os.path.relpath(root, p).replace("\\", "/")
                remote_base = remote_root if rel == "." else posixpath.join(remote_root, rel)
                dirs_to_create.add(remote_base)
                for d in dirs:
                    dirs_to_create.add(posixpath.join(remote_base, d))
                for f in files:
                    file_tasks.append((os.path.join(root, f), posixpath.join(remote_base, f)))
        elif os.path.isfile(p):
            file_tasks.append((p, posixpath.join(cwd, os.path.basename(p))))
    return dirs_to_create, file_tasks


def _upload_bucket_with_emit(params, tasks, emit):
    transport = None
    sftp = None
    try:
        transport, sftp = open_client_from_params(params)
        done = 0
        for local_path, remote_path in tasks:
            try:
                _put_with_progress(sftp, local_path, remote_path, emit)
                emit(("log", f"✅ Uploaded: {remote_path}"))
            except Exception as e:
                emit(("log", f"❌ Upload failed: {local_path} ({e})"))
                emit(("file_progress_done", remote_path, False, str(e)))
            done += 1
        return done
    finally:
        try:
            if sftp:
                sftp.close()
        except Exception:
            pass
        try:
            if transport:
                transport.close()
        except Exception:
            pass


def _put_with_progress(sftp, local_path: str, remote_path: str, emit):
    total_size = int(os.path.getsize(local_path) or 0)
    file_label = os.path.basename(local_path) or remote_path
    emit(("file_progress_init", remote_path, file_label))
    last_percent = -1

    def _callback(sent, total):
        nonlocal last_percent
        base = int(total or total_size or 0)
        if base <= 0:
            return
        pct = int((sent * 100) / base)
        if pct != last_percent:
            last_percent = pct
            emit(("file_progress", remote_path, int(sent), base))

    sftp.put(local_path, remote_path, callback=_callback)
    final_total = int(total_size or 1)
    emit(("file_progress", remote_path, final_total, final_total))
    emit(("file_progress_done", remote_path, True, "Done"))


def upload_files_parallel(params, file_tasks, workers, emit):
    total = len(file_tasks)
    if total == 0:
        return
    max_workers = min(max(int(workers), 1), 10, total)
    emit(("log", f"🚀 Uploading {total} file(s) with {max_workers} worker(s)"))
    emit(("progress_total", total, "Uploading files..."))
    if max_workers <= 1:
        transport = None
        sftp = None
        done = 0
        for local_path, remote_path in file_tasks:
            try:
                if sftp is None:
                    transport, sftp = open_client_from_params(params)
                _put_with_progress(sftp, local_path, remote_path, emit)
                emit(("log", f"✅ Uploaded: {remote_path}"))
            except Exception as e:
                emit(("log", f"❌ Upload failed: {local_path} ({e})"))
                emit(("file_progress_done", remote_path, False, str(e)))
            done += 1
            emit(("progress", done))
        try:
            if sftp:
                sftp.close()
        except Exception:
            pass
        try:
            if transport:
                transport.close()
        except Exception:
            pass
        return

    buckets = [[] for _ in range(max_workers)]
    for i, task in enumerate(file_tasks):
        buckets[i % max_workers].append(task)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_upload_bucket_with_emit, params, b, emit) for b in buckets if b]
        for fut in as_completed(futures):
            done += int(fut.result() or 0)
            emit(("progress", done))
            if done % 10 == 0 or done == total:
                emit(("log", f"📈 Upload progress: {done}/{total}"))


def run_upload_job(params, cwd, paths, workers, emit):
    try:
        dirs_to_create, file_tasks = collect_upload_tasks(cwd, paths)
        emit(("log", f"📦 Prepared {len(file_tasks)} file task(s)"))
        transport = None
        sftp = None
        try:
            transport, sftp = open_client_from_params(params)
            for remote_dir in sorted(dirs_to_create, key=lambda p: p.count("/")):
                try:
                    sftp.mkdir(remote_dir)
                    emit(("log", f"📁 Created remote dir: {remote_dir}"))
                except Exception:
                    pass
        finally:
            try:
                if sftp:
                    sftp.close()
            except Exception:
                pass
            try:
                if transport:
                    transport.close()
            except Exception:
                pass
        if file_tasks:
            upload_files_parallel(params, file_tasks, workers, emit)
        emit(("done", True, "✔ Upload finished"))
    except Exception as e:
        emit(("error", f"Upload failed: {e}"))
        emit(("done", False, ""))


def remove_remote_dir(sftp, remote_dir: str):
    for a in sftp.listdir_attr(remote_dir):
        p = posixpath.join(remote_dir, a.filename)
        if stat.S_ISDIR(a.st_mode):
            remove_remote_dir(sftp, p)
        else:
            sftp.remove(p)
    sftp.rmdir(remote_dir)


def run_delete_job(params, delete_targets, emit):
    transport = None
    sftp = None
    try:
        emit(("progress_total", len(delete_targets), "Deleting selected items..."))
        transport, sftp = open_client_from_params(params)
        done = 0
        for remote_path, is_dir in delete_targets:
            if is_dir:
                remove_remote_dir(sftp, remote_path)
            else:
                sftp.remove(remote_path)
            done += 1
            emit(("log", f"🗑 Deleted: {remote_path}"))
            emit(("progress", done))
        emit(("done", True, "✔ Delete finished"))
    except Exception as e:
        emit(("error", f"Delete failed: {e}"))
        emit(("done", False, ""))
    finally:
        try:
            if sftp:
                sftp.close()
        except Exception:
            pass
        try:
            if transport:
                transport.close()
        except Exception:
            pass
