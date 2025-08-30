import os
from ftplib import FTP, all_errors


class FTPClient:
    """Simple FTP client for uploading files."""

    def __init__(self, host=None, user=None, password=None):
        self.host = host or os.getenv("FTP_HOST")
        self.user = user or os.getenv("FTP_USER")
        self.password = password or os.getenv("FTP_PASSWORD")
        if not self.host or not self.user or not self.password:
            raise ValueError("FTP credentials not set")
        self.ftp = None

    def connect(self):
        try:
            self.ftp = FTP(self.host, self.user, self.password, timeout=15)
        except all_errors as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"FTP connection failed: {exc}") from exc

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except all_errors:
                pass
            self.ftp = None

    def upload_file(self, local_path, remote_path=None):
        """Upload a single file to the FTP server."""
        if self.ftp is None:
            self.connect()
        remote_path = remote_path or os.path.basename(local_path)
        try:
            with open(local_path, "rb") as fh:
                self.ftp.storbinary(f"STOR {remote_path}", fh)
        except all_errors as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"FTP upload failed: {exc}") from exc

    def download_file(self, remote_path, local_path=None):
        """Download a single file from the FTP server."""
        if self.ftp is None:
            self.connect()
        local_path = local_path or os.path.basename(remote_path)
        try:
            with open(local_path, "wb") as fh:
                self.ftp.retrbinary(f"RETR {remote_path}", fh.write)
        except all_errors as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"FTP download failed: {exc}") from exc

    def upload_directory(self, directory, remote_dir="."):
        """Upload all files from ``directory`` to ``remote_dir``."""
        if self.ftp is None:
            self.connect()
        for entry in os.listdir(directory):
            path = os.path.join(directory, entry)
            if not os.path.isfile(path):
                continue
            dest = f"{remote_dir.rstrip('/')}/{entry}"
            self.upload_file(path, dest)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
