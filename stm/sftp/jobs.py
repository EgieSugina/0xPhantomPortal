import os
import posixpath
import socket
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import PARAMIKO_OK

if PARAMIKO_OK:
    import paramiko


def open_client_from_params(params):
    timeout = int(params.get("timeout", 8) or 8)
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
