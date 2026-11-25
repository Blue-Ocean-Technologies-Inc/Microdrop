# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Feed thumbnails, from a file or fetched over https, once per session.

A fetch never blocks the GUI thread (QNetworkAccessManager is asynchronous)
and never fails loudly: offline, or on any network or decoding problem, the
card simply has no image. Only https URLs are fetched, and redirects may not
downgrade to http.
"""

# Standard library imports.
from urllib.parse import urlparse

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtNetwork

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Milliseconds a thumbnail fetch may take before it is abandoned.
FETCH_TIMEOUT_MS = 10_000

_NO_ERROR = QtNetwork.QNetworkReply.NetworkError.NoError


class ThumbnailLoader(QtCore.QObject):
    """Hands each requested image to its callbacks as a QPixmap, or None."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._network = None
        self._cache = {}
        self._waiting = {}

    def request(self, image, callback):
        """Call ``callback(pixmap or None)`` with ``image``: a file path, or
        an https URL, fetched in the background the first time."""

        if image in self._cache:
            callback(self._cache[image])

            return

        if image in self._waiting:
            self._waiting[image].append(callback)

            return

        scheme = urlparse(image).scheme.lower()

        if scheme == "https":
            self._waiting[image] = [callback]
            self._fetch(image)

        elif len(scheme) <= 1:
            # One letter is a Windows drive, not a scheme.
            self._done(image, self._read_file(image), [callback])

        else:
            logger.info(f"Feed thumbnail {image} not loaded: only https URLs are")
            self._done(image, None, [callback])

    def _fetch(self, url):
        if self._network is None:
            self._network = QtNetwork.QNetworkAccessManager(self)

        request = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        request.setTransferTimeout(FETCH_TIMEOUT_MS)
        request.setAttribute(
            QtNetwork.QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QtNetwork.QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )

        reply = self._network.get(request)
        reply.finished.connect(lambda: self._fetched(url, reply))

    def _fetched(self, url, reply):
        pixmap = None

        if reply.error() == _NO_ERROR:
            pixmap = self._decode(url, bytes(reply.readAll()))

        else:
            logger.info(f"Feed thumbnail {url} not fetched: {reply.errorString()}")

        reply.deleteLater()
        self._done(url, pixmap, self._waiting.pop(url, []))

    def _done(self, image, pixmap, callbacks):
        self._cache[image] = pixmap

        for callback in callbacks:
            callback(pixmap)

    @staticmethod
    def _read_file(path):
        pixmap = QtGui.QPixmap(path)

        if pixmap.isNull():
            logger.info(f"Feed thumbnail {path} not shown: no readable image there")

            return None

        return pixmap

    @staticmethod
    def _decode(url, data):
        pixmap = QtGui.QPixmap()

        if not pixmap.loadFromData(data):
            logger.info(f"Feed thumbnail {url} not shown: not an image")

            return None

        return pixmap


#: The session's loader, made on first use (it needs the QApplication).
_loader = None


def thumbnail_loader():
    """The session's ThumbnailLoader, shared so each image loads once."""
    global _loader

    if _loader is None:
        _loader = ThumbnailLoader(QtCore.QCoreApplication.instance())

    return _loader
