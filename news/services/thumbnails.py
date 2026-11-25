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

Nothing blocks the GUI thread: a fetch is asynchronous (QNetworkAccessManager)
and every picture is decoded to a QImage on a worker thread, only the QPixmap
made from it on the GUI thread. A file picture's size is known before then
(``known_size``, from its header alone), so a card can keep its room. Nothing
fails loudly: offline, or on any network or decoding problem, the card simply
has no image. Only https URLs are fetched, and redirects may not downgrade to
http.
"""

# Standard library imports.
from functools import partial
from threading import Thread
from urllib.parse import urlparse

# Enthought library imports.
from pyface.api import GUI
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
        self._sizes = {}

    def known_size(self, image):
        """The pixel size of the file picture ``image``, read from its header
        without decoding it; None for a URL or an unreadable file."""

        if len(urlparse(image).scheme) > 1:
            return None

        if image not in self._sizes:
            size = QtGui.QImageReader(image).size()
            self._sizes[image] = size if size.isValid() and not size.isEmpty() else None

        return self._sizes[image]

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
            self._waiting[image] = [callback]
            self._decode_in_background(image, image)

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

        if reply.error() == _NO_ERROR:
            self._decode_in_background(url, bytes(reply.readAll()))

        else:
            logger.info(f"Feed thumbnail {url} not fetched: {reply.errorString()}")
            self._done(url, None, self._waiting.pop(url, []))

        reply.deleteLater()

    def _decode_in_background(self, image, source):
        """Decode ``source``, a file path or fetched bytes, on a worker
        thread; ``image``'s callbacks get it on the GUI thread."""
        Thread(
            target=_decode_picture,
            args=(source, partial(GUI.invoke_later, self._decoded, image)),
            name=f"decode {image}",
            daemon=True,
        ).start()

    def _decoded(self, image, picture):
        """On the GUI thread: the QPixmap of the decoded ``picture``, to
        ``image``'s callbacks."""
        pixmap = None

        if picture.isNull():
            logger.info(f"Feed thumbnail {image} not shown: not a readable image")

        else:
            pixmap = QtGui.QPixmap.fromImage(picture)

        self._done(image, pixmap, self._waiting.pop(image, []))

    def _done(self, image, pixmap, callbacks):
        self._cache[image] = pixmap

        for callback in callbacks:
            callback(pixmap)


def _decode_picture(source, deliver):
    """On a worker thread: ``source`` (a file path, or bytes) decoded to a
    QImage, null if it is no image, passed to ``deliver``. A QImage, never a
    QPixmap: only the GUI thread may make those."""

    if isinstance(source, bytes):
        picture = QtGui.QImage.fromData(source)

    else:
        picture = QtGui.QImageReader(source).read()

    deliver(picture)


#: The session's loader, made on first use (it needs the QApplication).
_loader = None


def thumbnail_loader():
    """The session's ThumbnailLoader, shared so each image loads once."""
    global _loader

    if _loader is None:
        _loader = ThumbnailLoader(QtCore.QCoreApplication.instance())

    return _loader
