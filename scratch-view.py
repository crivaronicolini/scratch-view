""" QtImageViewer.py: PyQt image viewer widget based on QGraphicsView with mouse zooming/panning and ROIs.

"""

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from pathlib import Path
import subprocess
import platform
import traceback


import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from PyQt6.QtCore import Qt, QRectF, QPoint, QPointF, pyqtSignal, QEvent, QSize, QProcess
from PyQt6.QtGui import QAction, QImage, QPixmap, QPainterPath, QMouseEvent, QPainter, QPen, QBrush, QColor
from PyQt6.QtWidgets import QToolBar, QMainWindow, QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QFileDialog, QSizePolicy, \
    QGraphicsItem, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsLineItem, QGraphicsPolygonItem, QLabel, QMessageBox

# numpy is optional: only needed if you want to display numpy 2d arrays as images.
try:
    import numpy as np
except ImportError:
    np = None

# qimage2ndarray is optional: useful for displaying numpy 2d arrays as images.
# !!! qimage2ndarray requires PyQt5.
#     Some custom code in the viewer appears to handle the conversion from numpy 2d arrays,
#     so qimage2ndarray probably is not needed anymore. I've left it here just in case.
try:
    import qimage2ndarray
except ImportError:
    qimage2ndarray = None

__author__ = "Marcel Goldschen-Ohm <marcel.goldschen@gmail.com>"
__version__ = '2.0.0'


def errorDialog(parent, title, message):
    print(message)
    QMessageBox.critical(parent, str(title), message)
    return


class MainWindow(QMainWindow):
    def __init__(self, ):
        QMainWindow.__init__(self)
        self.setWindowTitle("aber")
        self.viewer = QtImageViewer()
        self.plot = Plot()
        self.label = QLabel('hola')
        f = self.label.font()
        f.setPointSize(15)
        self.label.setFont(f)
        self.label.setFont(self.label.font())
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter |
                                Qt.AlignmentFlag.AlignVCenter)
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.viewer)
        layout.addWidget(self.plot)
        widget.setLayout(layout)

        self.setCentralWidget(widget)

        self._createActions()
        self._createMenuBar()
        self._createToolBars()

        # Status Bar
        self.status = self.statusBar()
        self.status.showMessage("Data loaded and plotted")

        self.p = None

        # TODO hacer configurable
        self.scale = 0.44  # px/um

        self.zeroEllipse = None

        self.show()

    def _createMenuBar(self):
        menuBar = self.menuBar()
        # File menu
        fileMenu = menuBar.addMenu("Archivo")
        fileMenu.addAction(self.newCSVAction)
        fileMenu.addAction(self.newIMGAction)
        fileMenu.addAction(self.newStitchAction)

    def _createToolBars(self):
        mainToolBar = QToolBar("Main", self)
        self.addToolBar(mainToolBar)
        mainToolBar.addAction(self.enableSetZeroAction)

    def _createActions(self):
        self.newIMGAction = QAction("Abrir imagen", self)
        self.newIMGAction.triggered.connect(self.viewer.open)

        self.newCSVAction = QAction("Abrir csv", self)
        self.newCSVAction.triggered.connect(self.plot.open)

        self.newStitchAction = QAction("Juntar imagenes", self)
        self.newStitchAction.triggered.connect(self.juntarImagenes)

        self.enableSetZeroAction = QAction("Elegir origen", self)
        self.enableSetZeroAction.setCheckable(True)
        self.enableSetZeroAction.toggled.connect(self.enableSetZero)

        self.viewer.mousePositionOnImageChanged.connect(self.printPos)
        self.viewer.setTitleAction.connect(self.setTitle)

    def enableSetZero(self, enable):
        if enable:
            self.viewer.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.viewer.middleMouseButtonReleased.connect(self.setZero)
        else:
            self.viewer.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewer.middleMouseButtonReleased.disconnect()

    def setZero(self, x, y):
        if self.zeroEllipse:
            self.viewer.scene.removeItem(self.zeroEllipse)
        try:
            r = 25
            self.zeroEllipse = self.viewer.scene.addEllipse(
                x-r, y-r, 2*r, 2*r, pen=0, brush=QColor("#FFD141"))
            self.zeroEllipsePos = QPointF(round(x-r), round(y-r))

            self.enableSetZeroAction.toggle()
        except Exception as e:
            # pass
            errorDialog(self, e, traceback.format_exc())
            print(e)

    def printPos(self, point):
        if self.zeroEllipse:
            try:
                x, y = self._mapToum(QPointF(point) - self.zeroEllipsePos)
                fIn = self.plot.getfIn(x)
                self.status.showMessage(f"x={x}, y={y}   F={fIn:.2f}N")
            except Exception as e:
                errorDialog(self, e, traceback.format_exc())
                print(e)
                # pass

    def _mapToum(self, point):
        x, y = point.x(), point.y()
        return round(self.scale * x), round(self.scale * y)

    def setTitle(self, title):
        self.label.setText(title)

    def _whichFiji(self):
        p = platform.system()
        if p == 'Linux':
            # return subprocess.run(["which", "fiji"])
            return "fiji"
        if p == 'Windows':
            # TODO
            return
        return

    def juntarImagenes(self):
        """Da para elegir una carpeta y corre una macro de Fiji sobre las imagenes de esa carpeta.
        Guarda el resultado con el nombre de la carpeta"""
        if not self.p:
            try:
                fiji = self._whichFiji()
                directory = QFileDialog.getExistingDirectory(
                    self, "Abrir carpeta de imagenes")
                directory = Path(directory).resolve()

                self.directory_juntadas = directory
                self.files_juntadas = sorted(Path.iterdir(directory))
                self.csv_juntadas = [
                    f for f in self.files_juntadas if f.name.endswith('csv')]
                imgs = [
                    f for f in self.files_juntadas if f.name.endswith('jpg')]

                if imgs[0].stem != '1':
                    # TODO convertir los archivos a 1 2 3...
                    pass

                x = len(imgs)
                y = 1
                overlap = 20

                # si está el csv de la medición uso eso como nombre de archivo
                if self.csv_juntadas:
                    self.outpath = ''.join(
                        [str(directory.parent / self.csv_juntadas[0].stem), '.jpg'])
                else:
                    self.outpath = ''.join(
                        [str(directory.parent / directory.name), '.jpg'])

                self.status.showMessage('Uniendo imagenes')
                self.p = QProcess()
                self.p.finished.connect(self.p_finished)

                print('hola')

                self.p.start(fiji, ["--headless", "--run", "stitch-macro.py",
                             f'{x=},{y=},{overlap=},directory="{str(directory)}",outpath="{self.outpath}"'])
            except Exception as e:
                errorDialog(self, e, traceback.format_exc())

    def p_finished(self):
        self.status.showMessage(f'Imagen guardada en {self.outpath}')
        self.viewer.open(self.outpath)
        if self.csv_juntadas:
            self.plot.open(self.csv_juntadas[0])
        self.p = None


class Plot(QWidget):

    doubleClickAction = pyqtSignal(str)

    def __init__(self, parent=None):
        super(Plot, self).__init__(parent)

        self.figure = plt.figure()
        self.figureCanvas = FigureCanvasQTAgg(self.figure)
        self.navigationToolbar = NavigationToolbar(self.figureCanvas, self)

        layout = QVBoxLayout()
        layout.addWidget(self.navigationToolbar)
        layout.addWidget(self.figureCanvas)
        self.setLayout(layout)

        self.ax = self.figure.add_subplot(111)

        self.figureCanvas.show()

    def open(self, filepath):
        """Open file picker to open csv """
        try:
            if not filepath:
                filepath, _ = QFileDialog.getOpenFileName(
                    self, "Abrir csv", "", "Spreadsheet files (*.csv *.tsv *.xlx)")
                filepath = Path(filepath).resolve()
            self.df = pd.read_csv(filepath)
            title = filepath.name
            self.ajustardf()
            self.plot(title)
        except Exception as e:
            errorDialog(self, e, traceback.format_exc())

    def ajustardf(self):
        df = self.df
        # TODO setear escala bien
        if df.x.mean() < -1:
            df.x = - df.x
        # saco el acercamiento y estabilizacion
        l = len(df.x[df.x == 0.]) - 1
        df = df.drop(df[:l].index).reset_index(drop=True)
        df['um'] = df.x/25.6
        df.fIn = df.fIn/1000
        df.fSet = df.fSet/1000
        self.df = df

    def plot(self, title):
        self.ax.cla()
        self.ax.plot(self.df.um, self.df.fIn, "b")
        self.ax.plot(self.df.um, self.df.fSet, "--", color="gray")
        self.ax.set_title(title)
        self.figureCanvas.draw_idle()
        self.figure.tight_layout()

    def getfIn(self, x):
        try:
            idx = np.searchsorted(self.df['um'], x, side='left')
            return self.df.fIn[idx]
        except ValueError:
            return 0


class QtImageViewer(QGraphicsView):
    """ PyQt image viewer widget based on QGraphicsView with mouse zooming/panning and ROIs.

    Image File:
    -----------
    Use the open("path/to/file") method to load an image file into the viewer.
    Calling open() without a file argument will popup a file selection dialog.

    Image:
    ------
    Use the setImage(im) method to set the image data in the viewer.
            - im can be a QImage, QPixmap, or NumPy 2D array (the later requires the package qimage2ndarray).
            For display in the QGraphicsView the image will be converted to a QPixmap.

    Some useful image format conversion utilities:
            qimage2ndarray: NumPy ndarray <==> QImage    (https://github.com/hmeine/qimage2ndarray)
            ImageQt: PIL Image <==> QImage  (https://github.com/python-pillow/Pillow/blob/master/PIL/ImageQt.py)

    Mouse:
    ------
    Mouse interactions for zooming and panning is fully customizable by simply setting the desired button interactions:
    e.g.,
            regionZoomButton = Qt.LeftButton  # Drag a zoom box.
            # Pop end of zoom stack (double click clears zoom stack).
            zoomOutButton = Qt.RightButton
            panButton = Qt.MiddleButton  # Drag to pan.
            # Set to None or 1 to disable mouse wheel zoom.
            wheelZoomFactor = 1.25

    To disable any interaction, just disable its button.
    e.g., to disable panning:
            panButton = None

    ROIs:
    -----
    Can also add ellipse, rectangle, line, and polygon ROIs to the image.
    ROIs should be derived from the provided EllipseROI, RectROI, LineROI, and PolygonROI classes.
    ROIs are selectable and optionally moveable with the mouse (see setROIsAreMovable).

    TODO: Add support for editing the displayed image contrast.
    TODO: Add support for drawing ROIs with the mouse.
    """

    # Mouse button signals emit image scene (x, y) coordinates.
    # !!! For image (row, column) matrix indexing, row = y and column = x.
    # !!! These signals will NOT be emitted if the event is handled by an interaction such as zoom or pan.
    # !!! If aspect ratio prevents image from filling viewport, emitted position may be outside image bounds.
    leftMouseButtonPressed = pyqtSignal(float, float)
    leftMouseButtonReleased = pyqtSignal(float, float)
    middleMouseButtonPressed = pyqtSignal(float, float)
    middleMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    leftMouseButtonDoubleClicked = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    # Emitted upon zooming/panning.
    viewChanged = pyqtSignal()

    # Emitted on mouse motion.
    # Emits mouse position over image in image pixel coordinates.
    # !!! setMouseTracking(True) if you want to use this at all times.
    mousePositionOnImageChanged = pyqtSignal(QPoint)

    # Emit index of selected ROI
    roiSelected = pyqtSignal(int)

    setTitleAction = pyqtSignal(str)

    def __init__(self):
        QGraphicsView.__init__(self)

        # Image is displayed as a QPixmap in a QGraphicsScene attached to this QGraphicsView.
        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Better quality pixmap scaling?
        # self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        # Displayed image pixmap in the QGraphicsScene.
        self._image = None

        # Image aspect ratio mode.
        #   Qt.IgnoreAspectRatio: Scale image to fit viewport.
        #   Qt.KeepAspectRatio: Scale image to fit inside viewport, preserving aspect ratio.
        #   Qt.KeepAspectRatioByExpanding: Scale image to fill the viewport, preserving aspect ratio.
        self.aspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio

        # Scroll bar behaviour.
        #   Qt.ScrollBarAlwaysOff: Never shows a scroll bar.
        #   Qt.ScrollBarAlwaysOn: Always shows a scroll bar.
        #   Qt.ScrollBarAsNeeded: Shows a scroll bar only when zoomed.
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Interactions (set buttons to None to disable interactions)
        # !!! Events handled by interactions will NOT emit *MouseButton* signals.
        #     Note: regionZoomButton will still emit a *MouseButtonReleased signal on a click (i.e. tiny box).
        self.regionZoomButton = Qt.MouseButton.LeftButton  # Drag a zoom box.
        # Pop end of zoom stack (double click clears zoom stack).
        self.zoomOutButton = Qt.MouseButton.RightButton
        self.panButton = Qt.MouseButton.MiddleButton  # Drag to pan.
        # Set to None or 1 to disable mouse wheel zoom.
        self.wheelZoomFactor = 1.25

        # Stack of QRectF zoom boxes in scene coordinates.
        # !!! If you update this manually, be sure to call updateViewer() to reflect any changes.
        self.zoomStack = []

        # Flags for active zooming/panning.
        self._isZooming = False
        self._isPanning = False

        # Store temporary position in screen pixels or scene units.
        self._pixelPosition = QPoint()
        self._scenePosition = QPointF()

        # Track mouse position. e.g., For displaying coordinates in a UI.
        self.setMouseTracking(True)

        # ROIs.
        self.ROIs = []

        # # For drawing ROIs.
        # self.drawROI = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(900, 600)

    def hasImage(self):
        """ Returns whether the scene contains an image pixmap.
        """
        return self._image is not None

    def clearImage(self):
        """ Removes the current image pixmap from the scene if it exists.
        """
        if self.hasImage():
            self.scene.removeItem(self._image)
            self._image = None

    def pixmap(self):
        """ Returns the scene's current image pixmap as a QPixmap, or else None if no image exists.
        :rtype: QPixmap | None
        """
        if self.hasImage():
            return self._image.pixmap()
        return None

    def image(self):
        """ Returns the scene's current image pixmap as a QImage, or else None if no image exists.
        :rtype: QImage | None
        """
        if self.hasImage():
            return self._image.pixmap().toImage()
        return None

    def setImage(self, image):
        """ Set the scene's current image pixmap to the input QImage or QPixmap.
        Raises a RuntimeError if the input image has type other than QImage or QPixmap.
        :type image: QImage | QPixmap
        """
        if type(image) is QPixmap:
            pixmap = image
        elif type(image) is QImage:
            pixmap = QPixmap.fromImage(image)
        elif (np is not None) and (type(image) is np.ndarray):
            if qimage2ndarray is not None:
                qimage = qimage2ndarray.array2qimage(image, True)
                pixmap = QPixmap.fromImage(qimage)
            else:
                image = image.astype(np.float32)
                image -= image.min()
                image /= image.max()
                image *= 255
                image[image > 255] = 255
                image[image < 0] = 0
                image = image.astype(np.uint8)
                height, width = image.shape
                bytes = image.tobytes()
                qimage = QImage(bytes, width, height,
                                QImage.Format.Format_Grayscale8)
                pixmap = QPixmap.fromImage(qimage)
        else:
            raise RuntimeError(
                "ImageViewer.setImage: Argument must be a QImage, QPixmap, or numpy.ndarray.")
        if self.hasImage():
            self._image.setPixmap(pixmap)
        else:
            self._image = self.scene.addPixmap(pixmap)

        # Better quality pixmap scaling?
        # !!! This will distort actual pixel data when zoomed way in.
        #     For scientific image analysis, you probably don't want this.
        # self._pixmap.setTransformationMode(Qt.SmoothTransformation)

        # Set scene size to image size.
        self.setSceneRect(QRectF(pixmap.rect()))
        self.updateViewer()

    def open(self, filepath=None):
        """ Load an image from file.
        Without any arguments, loadImageFromFile() will pop up a file dialog to choose the image file.
        With a fileName argument, loadImageFromFile(fileName) will attempt to load the specified image file directly.
        """
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Open image file.", "", "Image Files (*.png *.jpg *.bmp)")
            filepath = Path(filepath).resolve()
        if self.hasImage():
            self.clearImage()
        image = QImage(str(filepath))
        self.setImage(image)
        self.setTitle(filepath.name)

    def setTitle(self, title):
        self.setTitleAction.emit(title)

    def updateViewer(self):
        """ Show current zoom (if showing entire image, apply current aspect ratio mode).
        """
        if not self.hasImage():
            return
        if len(self.zoomStack):
            # Show zoomed rect.
            self.fitInView(self.zoomStack[-1], self.aspectRatioMode)
        else:
            # Show entire image.
            self.fitInView(self.sceneRect(), self.aspectRatioMode)

    def clearZoom(self):
        if len(self.zoomStack) > 0:
            self.zoomStack = []
            self.updateViewer()
            self.viewChanged.emit()

    def resizeEvent(self, event):
        """ Maintain current zoom on resize.
        """
        self.updateViewer()

    def mousePressEvent(self, event):
        """ Start mouse pan or zoom mode.
        """
        # Ignore dummy events. e.g., Faking pan with left button ScrollHandDrag.
        dummyModifiers = Qt.KeyboardModifier(Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
                                             | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
        if event.modifiers() == dummyModifiers:
            QGraphicsView.mousePressEvent(self, event)
            event.accept()
            return

        # # Draw ROI
        # if self.drawROI is not None:
        #     if self.drawROI == "Ellipse":
        #         # Click and drag to draw ellipse. +Shift for circle.
        #         pass
        #     elif self.drawROI == "Rect":
        #         # Click and drag to draw rectangle. +Shift for square.
        #         pass
        #     elif self.drawROI == "Line":
        #         # Click and drag to draw line.
        #         pass
        #     elif self.drawROI == "Polygon":
        #         # Click to add points to polygon. Double-click to close polygon.
        #         pass

        # Start dragging a region zoom box?
        if (self.regionZoomButton is not None) and (event.button() == self.regionZoomButton):
            self._pixelPosition = event.pos()  # store pixel position
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            QGraphicsView.mousePressEvent(self, event)
            event.accept()
            self._isZooming = True
            return

        if (self.zoomOutButton is not None) and (event.button() == self.zoomOutButton):
            if len(self.zoomStack):
                self.zoomStack.pop()
                self.updateViewer()
                self.viewChanged.emit()
            event.accept()
            return

        # Start dragging to pan?
        if (self.panButton is not None) and (event.button() == self.panButton):
            self._pixelPosition = event.pos()  # store pixel position
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            if self.panButton == Qt.MouseButton.LeftButton:
                QGraphicsView.mousePressEvent(self, event)
            else:
                # ScrollHandDrag ONLY works with LeftButton, so fake it.
                # Use a bunch of dummy modifiers to notify that event should NOT be handled as usual.
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                dummyModifiers = Qt.KeyboardModifier(Qt.KeyboardModifier.ShiftModifier
                                                     | Qt.KeyboardModifier.ControlModifier
                                                     | Qt.KeyboardModifier.AltModifier
                                                     | Qt.KeyboardModifier.MetaModifier)
                dummyEvent = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(event.pos()), Qt.MouseButton.LeftButton,
                                         event.buttons(), dummyModifiers)
                self.mousePressEvent(dummyEvent)
            sceneViewport = self.mapToScene(
                self.viewport().rect()).boundingRect().intersected(self.sceneRect())
            self._scenePosition = sceneViewport.topLeft()
            event.accept()
            self._isPanning = True
            return

        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            self.leftMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middleMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        elif event.button() == Qt.MouseButton.RightButton:
            self.rightMouseButtonPressed.emit(scenePos.x(), scenePos.y())

        QGraphicsView.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        """ Stop mouse pan or zoom mode (apply zoom if valid).
        """
        # Ignore dummy events. e.g., Faking pan with left button ScrollHandDrag.
        dummyModifiers = Qt.KeyboardModifier(Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
                                             | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
        if event.modifiers() == dummyModifiers:
            QGraphicsView.mouseReleaseEvent(self, event)
            event.accept()
            return

        # Finish dragging a region zoom box?
        if (self.regionZoomButton is not None) and (event.button() == self.regionZoomButton):
            QGraphicsView.mouseReleaseEvent(self, event)
            zoomRect = self.scene.selectionArea().boundingRect().intersected(self.sceneRect())
            # Clear current selection area (i.e. rubberband rect).
            self.scene.setSelectionArea(QPainterPath())
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            # If zoom box is 3x3 screen pixels or smaller, do not zoom and proceed to process as a click release.
            zoomPixelWidth = abs(event.pos().x() - self._pixelPosition.x())
            zoomPixelHeight = abs(event.pos().y() - self._pixelPosition.y())
            if zoomPixelWidth > 3 and zoomPixelHeight > 3:
                if zoomRect.isValid() and (zoomRect != self.sceneRect()):
                    self.zoomStack.append(zoomRect)
                    self.updateViewer()
                    self.viewChanged.emit()
                    event.accept()
                    self._isZooming = False
                    return

        # Finish panning?
        if (self.panButton is not None) and (event.button() == self.panButton):
            if self.panButton == Qt.MouseButton.LeftButton:
                QGraphicsView.mouseReleaseEvent(self, event)
            else:
                # ScrollHandDrag ONLY works with LeftButton, so fake it.
                # Use a bunch of dummy modifiers to notify that event should NOT be handled as usual.
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                dummyModifiers = Qt.KeyboardModifier(Qt.KeyboardModifier.ShiftModifier
                                                     | Qt.KeyboardModifier.ControlModifier
                                                     | Qt.KeyboardModifier.AltModifier
                                                     | Qt.KeyboardModifier.MetaModifier)
                dummyEvent = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(event.pos()),
                                         Qt.MouseButton.LeftButton, event.buttons(), dummyModifiers)
                self.mouseReleaseEvent(dummyEvent)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            if len(self.zoomStack) > 0:
                sceneViewport = self.mapToScene(
                    self.viewport().rect()).boundingRect().intersected(self.sceneRect())
                delta = sceneViewport.topLeft() - self._scenePosition
                self.zoomStack[-1].translate(delta)
                self.zoomStack[-1] = self.zoomStack[-1].intersected(
                    self.sceneRect())
                self.viewChanged.emit()
            event.accept()
            self._isPanning = False
            return

        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            self.leftMouseButtonReleased.emit(scenePos.x(), scenePos.y())
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middleMouseButtonReleased.emit(scenePos.x(), scenePos.y())
        elif event.button() == Qt.MouseButton.RightButton:
            self.rightMouseButtonReleased.emit(scenePos.x(), scenePos.y())

        QGraphicsView.mouseReleaseEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        """ Show entire image.
        """
        # Zoom out on double click?
        if (self.zoomOutButton is not None) and (event.button() == self.zoomOutButton):
            self.clearZoom()
            event.accept()
            return

        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            self.leftMouseButtonDoubleClicked.emit(scenePos.x(), scenePos.y())
        elif event.button() == Qt.MouseButton.RightButton:
            self.rightMouseButtonDoubleClicked.emit(scenePos.x(), scenePos.y())

        QGraphicsView.mouseDoubleClickEvent(self, event)

    def wheelEvent(self, event):
        if self.wheelZoomFactor is not None:
            if self.wheelZoomFactor == 1:
                return
            if event.angleDelta().y() > 0:
                # zoom in
                if len(self.zoomStack) == 0:
                    self.zoomStack.append(self.sceneRect())
                elif len(self.zoomStack) > 1:
                    del self.zoomStack[:-1]
                zoomRect = self.zoomStack[-1]
                center = zoomRect.center()
                zoomRect.setWidth(zoomRect.width() / self.wheelZoomFactor)
                zoomRect.setHeight(zoomRect.height() / self.wheelZoomFactor)
                zoomRect.moveCenter(center)
                self.zoomStack[-1] = zoomRect.intersected(self.sceneRect())
                self.updateViewer()
                self.viewChanged.emit()
            else:
                # zoom out
                if len(self.zoomStack) == 0:
                    # Already fully zoomed out.
                    return
                if len(self.zoomStack) > 1:
                    del self.zoomStack[:-1]
                zoomRect = self.zoomStack[-1]
                center = zoomRect.center()
                zoomRect.setWidth(zoomRect.width() * self.wheelZoomFactor)
                zoomRect.setHeight(zoomRect.height() * self.wheelZoomFactor)
                zoomRect.moveCenter(center)
                self.zoomStack[-1] = zoomRect.intersected(self.sceneRect())
                if self.zoomStack[-1] == self.sceneRect():
                    self.zoomStack = []
                self.updateViewer()
                self.viewChanged.emit()
            event.accept()
            return

        QGraphicsView.wheelEvent(self, event)

    def mouseMoveEvent(self, event):
        # Emit updated view during panning.
        if self._isPanning:
            QGraphicsView.mouseMoveEvent(self, event)
            if len(self.zoomStack) > 0:
                sceneViewport = self.mapToScene(
                    self.viewport().rect()).boundingRect().intersected(self.sceneRect())
                delta = sceneViewport.topLeft() - self._scenePosition
                self._scenePosition = sceneViewport.topLeft()
                self.zoomStack[-1].translate(delta)
                self.zoomStack[-1] = self.zoomStack[-1].intersected(
                    self.sceneRect())
                self.updateViewer()
                self.viewChanged.emit()

        scenePos = self.mapToScene(event.pos())
        if self.sceneRect().contains(scenePos):
            # Pixel index offset from pixel center.
            x = int(round(scenePos.x() - 0.5))
            y = int(round(scenePos.y() - 0.5))
            self.imagePos = QPoint(x, y)
        else:
            # Invalid pixel position.
            self.imagePos = QPoint(-1, -1)
        self.mousePositionOnImageChanged.emit(self.imagePos)

        QGraphicsView.mouseMoveEvent(self, event)

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def addROIs(self, rois):
        for roi in rois:
            self.scene.addItem(roi)
            self.ROIs.append(roi)

    def deleteROIs(self, rois):
        for roi in rois:
            self.scene.removeItem(roi)
            self.ROIs.remove(roi)
            del roi

    def clearROIs(self):
        for roi in self.ROIs:
            self.scene.removeItem(roi)
        del self.ROIs[:]

    def roiClicked(self, roi):
        for i in range(len(self.ROIs)):
            if roi is self.ROIs[i]:
                self.roiSelected.emit(i)
                break

    def setROIsAreMovable(self, tf):
        if tf:
            for roi in self.ROIs:
                roi.setFlags(
                    roi.flags() | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        else:
            for roi in self.ROIs:
                roi.setFlags(roi.flags() & ~
                             QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def addSpots(self, xy, radius):
        for xy_ in xy:
            x, y = xy_
            spot = EllipseROI(self)
            spot.setRect(x - radius, y - radius, 2 * radius, 2 * radius)
            self.scene.addItem(spot)
            self.ROIs.append(spot)


class EllipseROI(QGraphicsEllipseItem):

    def __init__(self, viewer):
        QGraphicsItem.__init__(self)
        self._viewer = viewer
        pen = QPen(Qt.yellow)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setFlags(self.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        QGraphicsItem.mousePressEvent(self, event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._viewer.roiClicked(self)


class RectROI(QGraphicsRectItem):

    def __init__(self, viewer):
        QGraphicsItem.__init__(self)
        self._viewer = viewer
        pen = QPen(Qt.GlobalColor.yellow)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setFlags(self.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        QGraphicsItem.mousePressEvent(self, event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._viewer.roiClicked(self)


class LineROI(QGraphicsLineItem):

    def __init__(self, viewer):
        QGraphicsItem.__init__(self)
        self._viewer = viewer
        pen = QPen(Qt.GlobalColor.yellow)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setFlags(self.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        QGraphicsItem.mousePressEvent(self, event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._viewer.roiClicked(self)


class PolygonROI(QGraphicsPolygonItem):

    def __init__(self, viewer):
        QGraphicsItem.__init__(self)
        self._viewer = viewer
        pen = QPen(Qt.GlobalColor.yellow)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setFlags(self.GraphicsItemFlag.ItemIsSelectable)

    def mousePressEvent(self, event):
        QGraphicsItem.mousePressEvent(self, event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._viewer.roiClicked(self)


if __name__ == '__main__':
    import sys
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        from PyQt5.QtWidgets import QApplication

    def handleLeftClick(x, y):
        row = int(y)
        column = int(x)
        print("Clicked on image pixel (row="+str(row)+", column="+str(column)+")")

    def handleViewChange():
        print("viewChanged")

    def my_exception_hook(exctype, value, traceback):
        # Print the error and traceback
        print(exctype, value, traceback)
        # Call the normal Exception hook after
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook

    # Set the exception hook to our wrapping function
    sys.excepthook = my_exception_hook

    # Create the QApplication.
    app = QApplication(sys.argv)
    #
    # Create an image viewer widget.
    mainwindow = MainWindow()
    viewer = mainwindow.viewer

    # Set viewer's aspect ratio mode.
    # !!! ONLY applies to full image view.
    # !!! Aspect ratio always ignored when zoomed.
    #   Qt.AspectRatioMode.IgnoreAspectRatio: Fit to viewport.
    #   Qt.AspectRatioMode.KeepAspectRatio: Fit in viewport using aspect ratio.
    #   Qt.AspectRatioMode.KeepAspectRatioByExpanding: Fill viewport using aspect ratio.
    viewer.aspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio

    # Set the viewer's scroll bar behaviour.
    #   Qt.ScrollBarPolicy.ScrollBarAlwaysOff: Never show scroll bar.
    #   Qt.ScrollBarPolicy.ScrollBarAlwaysOn: Always show scroll bar.
    #   Qt.ScrollBarPolicy.ScrollBarAsNeeded: Show scroll bar only when zoomed.
    viewer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    viewer.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    # Allow zooming by draggin a zoom box with the left mouse button.
    # !!! This will still emit a leftMouseButtonReleased signal if no dragging occured,
    #     so you can still handle left mouse button clicks in this way.
    #     If you absolutely need to handle a left click upon press, then
    #     either disable region zooming or set it to the middle or right button.
    viewer.regionZoomButton = None  # set to None to disable

    # Pop end of zoom stack (double click clears zoom stack).
    viewer.zoomOutButton = Qt.MouseButton.RightButton  # set to None to disable

    # Mouse wheel zooming.
    viewer.wheelZoomFactor = 1.25  # Set to None or 1 to disable

    # Allow panning with the middle mouse button.
    viewer.panButton = Qt.MouseButton.LeftButton  # set to None to disable

    # Load an image file to be displayed (will popup a file dialog).
    img = "/home/marco/documents/fac/tesis2/ensayos2/CrCrN/M1402C/scratch/5-60.jpg"
    csv = "/home/marco/documents/fac/tesis2/ensayos2/CrCrN/M1402C/scratch/M1402_5-60_1.csv"
    viewer.open(Path(img))
    mainwindow.plot.open(Path(csv))

    # Handle left mouse clicks with your own custom slot
    # handleLeftClick(x, y). (x, y) are image coordinates.
    # For (row, col) matrix indexing, row=y and col=x.
    # QtImageViewer also provides similar signals for
    # left/right mouse button press, release and doubleclick.
    # Here I bind the slot to leftMouseButtonReleased only because
    # the leftMouseButtonPressed signal will not be emitted due to
    # left clicks being handled by the regionZoomButton.
    # viewer.middleMouseButtonReleased.connect(handleLeftClick)

    # Show the viewer and run the application.
    # mainwindow.show()
    sys.exit(app.exec())
