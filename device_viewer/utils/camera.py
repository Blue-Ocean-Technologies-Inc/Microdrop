import json
from typing import List, Tuple

import numpy as np
import cv2
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QTransform

def qimage_to_cv_image(qimage: QImage) -> np.ndarray: # https://stackoverflow.com/questions/18406149/pyqt-pyside-how-do-i-convert-qimage-into-opencvs-mat-format
    '''  Converts a QImage into an opencv MAT format  '''
    incomingImage = qimage.convertToFormat(QImage.Format_RGBX8888)
    ptr = incomingImage.constBits()
    cv_im_in = np.array(ptr, copy=True).reshape(incomingImage.height(), incomingImage.width(), 4)
    cv_im_in = cv2.cvtColor(cv_im_in, cv2.COLOR_BGRA2RGB)
    return cv_im_in

def cv_image_to_qimage(cv_image: np.ndarray) -> QImage:
    ''' Converts an opencv MAT format image into a QImage '''
    # Convert BGR (OpenCV) to RGB
    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape

    # Create QImage and wrap in QVideoFrame
    return QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888).copy()  # Use copy to ensure data is not shared with OpenCV

def qtransform_serialize(transform: QTransform) -> str:
    return json.dumps([transform.m11(), transform.m12(), transform.m13(),
                        transform.m21(), transform.m22(), transform.m23(),
                        transform.m31(), transform.m32(), transform.m33()])

def qtransform_deserialize(data: str) -> QTransform:
    params = json.loads(data)
    return QTransform(params[0], params[1], params[2],
                      params[3], params[4], params[5],
                      params[6], params[7], params[8])

def qpointf_list_serialize(list_qpointf: List[QPointF]) -> List[Tuple[float, float]]:
    return json.dumps([el.toTuple() for el in list_qpointf])

def qpointf_list_deserialize(data: str) -> List[QPointF]:
    return [QPointF(*coord_tuple) for coord_tuple in json.loads(data)]