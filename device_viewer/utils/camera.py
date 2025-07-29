import numpy as np
import cv2
from PySide6.QtGui import QImage

def qimage_to_cv_image(qimage: QImage) -> np.ndarray: # https://stackoverflow.com/questions/18406149/pyqt-pyside-how-do-i-convert-qimage-into-opencvs-mat-format
    '''  Converts a QImage into an opencv MAT format  '''
    incomingImage = qimage.convertToFormat(QImage.Format_RGBX8888)
    ptr = incomingImage.constBits()
    cv_im_in = np.array(ptr, copy=True).reshape(incomingImage.height(), incomingImage.width(), 4)
    cv_im_in = cv2.cvtColor(cv_im_in, cv2.COLOR_BGRA2RGB)
    return cv_im_in