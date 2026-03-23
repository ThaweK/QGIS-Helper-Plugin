"""Download BDOT10k data packages from GUGiK opendata server."""

import os
import socket
import time
import zipfile
from urllib.request import urlopen, Request

from qgis.core import (
    QgsBlockingNetworkRequest,
    QgsNetworkAccessManager,
)
from qgis.PyQt.QtCore import QUrl, QObject, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest

from .teryt_registry import get_powiat_name

FORMAT_SUFFIXES = {
    "GML": "_GML.zip",
    "SHP": "_SHP.zip",
    "GPKG": "_GPKG.zip",
}

BASE_URL = "https://opendata.geoportal.gov.pl/bdot10k"


class DownloadResult:
    def __init__(self, teryt, name, success, path=None, error=None, size=0):
        self.teryt = teryt
        self.name = name
        self.success = success
        self.path = path
        self.error = error
        self.size = size


class Downloader(QObject):
    """Downloads BDOT10k ZIP packages."""

    progress_file = pyqtSignal(int, int)  # bytes_received, bytes_total
    progress_total = pyqtSignal(int, int, int, int)  # current, total, ok, fail
    status_changed = pyqtSignal(str)
    download_finished = pyqtSignal(list)  # list of DownloadResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def build_url(self, teryt, fmt="GML"):
        woj = teryt[:2]
        suffix = FORMAT_SUFFIXES.get(fmt, "_GML.zip")
        return f"{BASE_URL}/{woj}/{teryt}{suffix}"

    def download(self, teryt_list, dest_folder, fmt="GML", timeout=600,
                 extract=True):
        """Download packages for given TERYT codes.

        Args:
            teryt_list: list of 4-digit TERYT strings
            dest_folder: destination directory path
            fmt: "GML", "SHP", or "GPKG"
            timeout: timeout in seconds per file
            extract: whether to extract ZIPs after download
        """
        self._cancel = False
        results = []
        ok_count = 0
        fail_count = 0

        for i, teryt in enumerate(teryt_list):
            if self._cancel:
                break

            name = get_powiat_name(teryt) or teryt
            url = self.build_url(teryt, fmt)
            filename = f"{teryt}{FORMAT_SUFFIXES.get(fmt, '_GML.zip')}"
            filepath = os.path.join(dest_folder, filename)

            self.status_changed.emit(f"Pobieranie / Downloading {name} ({teryt})...")
            self.progress_total.emit(i, len(teryt_list), ok_count, fail_count)
            self.progress_file.emit(0, 0)

            result = self._download_file(url, filepath, teryt, name, timeout)

            if result.success and extract:
                try:
                    self.status_changed.emit(
                        f"Rozpakowywanie / Extracting {filename}..."
                    )
                    extract_dir = os.path.join(dest_folder, teryt)
                    os.makedirs(extract_dir, exist_ok=True)
                    with zipfile.ZipFile(filepath, 'r') as zf:
                        zf.extractall(extract_dir)
                    result.path = extract_dir
                except Exception as e:
                    result.success = False
                    result.error = f"Extraction failed: {e}"

            if result.success:
                ok_count += 1
            else:
                fail_count += 1

            results.append(result)
            self.progress_total.emit(
                i + 1, len(teryt_list), ok_count, fail_count
            )

        self.download_finished.emit(results)
        return results

    def _download_file(self, url, filepath, teryt, name, timeout):
        """Try downloading with QgsBlockingNetworkRequest, fallback to urllib."""
        try:
            return self._download_qgs(url, filepath, teryt, name, timeout)
        except Exception:
            pass

        try:
            return self._download_urllib(url, filepath, teryt, name, timeout)
        except Exception as e:
            return DownloadResult(teryt, name, False, error=str(e))

    def _download_qgs(self, url, filepath, teryt, name, timeout):
        """Download using QGIS network manager."""
        req = QNetworkRequest(QUrl(url))
        blocker = QgsBlockingNetworkRequest()
        blocker.setAuthCfg('')

        err = blocker.get(req, forceRefresh=True)

        if err != QgsBlockingNetworkRequest.NoError:
            raise Exception(blocker.errorMessage())

        reply = blocker.reply()
        data = reply.content()

        with open(filepath, 'wb') as f:
            f.write(bytes(data))

        size = len(data)
        self.progress_file.emit(size, size)
        return DownloadResult(teryt, name, True, path=filepath, size=size)

    def _download_urllib(self, url, filepath, teryt, name, timeout):
        """Fallback download using urllib."""
        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(timeout)
            req = Request(url, headers={'User-Agent': 'BDOT10k-Toolbox/1.0'})
            response = urlopen(req, timeout=timeout)

            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 65536

            with open(filepath, 'wb') as f:
                while True:
                    if self._cancel:
                        return DownloadResult(
                            teryt, name, False, error="Cancelled"
                        )
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress_file.emit(downloaded, total)

                    from qgis.PyQt.QtWidgets import QApplication
                    QApplication.processEvents()

            return DownloadResult(
                teryt, name, True, path=filepath, size=downloaded
            )
        finally:
            socket.setdefaulttimeout(old_timeout)
