""" QtImageViewer.py: PyQt image viewer widget based on QGraphicsView with mouse zooming/panning and ROIs.

"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from matplotlib.backend_tools import Cursors
from pathlib import Path
import platform
import traceback


import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from PyQt6.QtCore import Qt, QRectF, QPoint, QPointF, pyqtSignal, QEvent, QSize, QProcess, QSettings
from PyQt6.QtGui import QAction, QImage, QPixmap, QPainterPath, QMouseEvent, QPainter, QPen, QBrush, QColor, QDragEnterEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import QToolBar, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene, QFileDialog, QSizePolicy, QGraphicsItem, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsLineItem, QGraphicsPolygonItem, QLabel, QMessageBox, QGraphicsProxyWidget, QPushButton, QInputDialog, QDialog, QRadioButton, QButtonGroup, QDialogButtonBox, QFormLayout, QLineEdit


def errorDialog(parent, title, message):
    print(message)
    QMessageBox.critical(parent, str(title), message)
    return


class MainWindow(QMainWindow):
    def __init__(self, ):
        QMainWindow.__init__(self)
        self.setWindowTitle("Scratch View")
        self.viewer = QtImageViewer()
        self.plot = Plot()
        self.label = QLabel('')
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

        self.setAcceptDrops(True)
        self.viewer.setAcceptDrops(True)

        self.viewer.dropEvent = self.dropEvent
        self.plot.dropEvent = self.dropEvent

        self.viewer.dragEnterEvent = self.dragEnterEvent
        self.viewer.dragMoveEvent = self.dragMoveEvent
        self.plot.dragEnterEvent = self.dragEnterEvent

        self.p = None

        self.imgFiletypes = ['.jpg', '.bmp', '.png']
        self.dataFiletypes = ['.csv', '.tsv']

        self.filetypes = self.imgFiletypes + self.dataFiletypes

        self.scales = {'olympus': 0.44}
        self.scaleCurrentName = 'olympus'
        self.scaleCurrentValue = 0.44

        self.zeroEllipse = None

        self.lastDir = ""
        self.readSettings()

        self.show()

    def setScaleFromBtn(self, button):
        self.scaleCurrentName = button.text()
        self.scaleCurrentValue = self.scales[self.scaleCurrentName]

    def setScaleFromText(self, nombre, valor):
        self.scaleCurrentValue = self.scales[nombre] = float(valor)
        self.scaleCurrentName = nombre

    def eraseScale(self, nombre):
        self.scales.pop(nombre)

    def _createMenuBar(self):
        menuBar = self.menuBar()
        # File menu
        fileMenu = menuBar.addMenu("Archivo")
        fileMenu.addAction(self.newFileAction)
        # Img menu
        imgMenu = menuBar.addMenu("Imagen")
        imgMenu.addAction(self.newStitchAction)
        imgMenu.addAction(self.setScaleAction)

    def _createToolBars(self):
        mainToolBar = QToolBar("Main", self)
        self.addToolBar(mainToolBar)
        mainToolBar.addAction(self.enableSetZeroAction)
        mainToolBar.addAction(self.enableMarcarLineaAction)

    def _createActions(self):
        self.newFileAction = QAction("Abrir archivos", self)
        self.newFileAction.triggered.connect(self.open)

        self.newStitchAction = QAction("Juntar imagenes", self)
        self.newStitchAction.triggered.connect(self.juntarImagenes)

        self.enableSetZeroAction = QAction("Elegir origen", self)
        self.enableSetZeroAction.setToolTip(
            "Click derecho para definir el origen.")
        self.enableSetZeroAction.setCheckable(True)
        self.enableSetZeroAction.toggled.connect(self.enableSetZero)

        self.enableMarcarLineaAction = QAction("Marcar linea", self)
        self.enableMarcarLineaAction.setToolTip(
            "Click derecho para marcar linea en el grafico.")
        self.enableMarcarLineaAction.setCheckable(True)
        self.enableMarcarLineaAction.toggled.connect(self.enableMarcarLinea)
        self.enableMarcarLineaAction.setDisabled(True)

        self.viewer.mousePositionOnImageChanged.connect(self.printPos)
        self.viewer.setTitleAction.connect(self.setTitle)

        self.setScaleAction = QAction("Cambiar escala", self)
        self.setScaleAction.triggered.connect(lambda: ScaleDialog(self))

    def enableSetZero(self, enable):
        if enable:
            self.viewer.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.viewer.rightMouseButtonReleased.connect(self.setZero)
            self.enableMarcarLineaAction.setChecked(False)
        else:
            self.viewer.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewer.rightMouseButtonReleased.disconnect(self.setZero)

    def enableMarcarLinea(self, enable):
        if enable:
            if not self.zeroEllipse:
                errorDialog(self, "Error", "Primero hay que definir el origen")
                return
            self.enableSetZeroAction.setChecked(False)
            self.viewer.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.viewer.mousePositionOnImageChanged.connect(
                self.plot.mostrarLinea)
            self.viewer.drawROI = 'Line'
            self.viewer.rightMouseButtonReleased.connect(self.plot.marcarLinea)
        else:
            self.viewer.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewer.rightMouseButtonReleased.disconnect(
                self.plot.marcarLinea)
            self.viewer.mousePositionOnImageChanged.disconnect(
                self.plot.mostrarLinea)
            self.viewer.drawROI = None

    def setZero(self, x, y):
        if self.zeroEllipse:
            self.viewer.scene.removeItem(self.zeroEllipse)
        r = 25
        self.zeroEllipse = self.viewer.scene.addEllipse(
            x-r, y-r, 2*r, 2*r, pen=0, brush=QColor("#FFD141"))
        self.zeroEllipsePos = QPointF(round(x-r), round(y-r))

        self.enableSetZeroAction.toggle()
        self.enableMarcarLineaAction.setDisabled(False)

    def printPos(self, point):
        if self.zeroEllipse:
            self.plot.x, y = self._mapToum(
                QPointF(point) - self.zeroEllipsePos)
            self.plot.fIn = self.plot.getfIn(self.plot.x)
            self.status.showMessage(
                f"x={self.plot.x}, y={y}   F={self.plot.fIn:.2f}N")

    def _mapToum(self, point):
        x, y = point.x(), point.y()
        return round(self.scaleCurrentValue * x), round(self.scaleCurrentValue * y)

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

            self.p.start(fiji, ["--headless", "--run", "stitch-macro.py",
                         f'{x=},{y=},{overlap=},directory="{str(directory)}",outpath="{self.outpath}"'])

    def p_finished(self):
        self.status.showMessage(f'Imagen guardada en {self.outpath}')
        self.viewer.open(self.outpath)
        if self.csv_juntadas:
            self.plot.open(self.csv_juntadas[0])
        self.p = None

    def open(self, filepaths=None):
        """Abre lista de archivos, o abre un seleccionador de archivos"""
        if not filepaths:
            filepaths, _ = QFileDialog.getOpenFileNames(
                self, caption="Abrir imagen y csv", directory=self.lastDir, filter="(*.jpg *.bmp *.png *.csv *.tsv)")
            filepaths = [Path(filepath).resolve() for filepath in filepaths]
        elif not isinstance(filepaths, list):
            filepaths = [filepaths]
        self.lastDir = str(filepaths[0].resolve())
        for filepath in filepaths:
            if filepath.suffix in self.imgFiletypes:
                self.viewer.open(filepath=filepath)
            elif filepath.suffix in self.dataFiletypes:
                self.plot.open(filepath=filepath)

    def dragEnterEvent(self, event):
        """Acepta archivos si alguno tiene formato valido"""
        if (event.mimeData().hasFormat("text/uri-list")):
            urls = event.mimeData().urls()
            self.paths = [path for path in (
                Path(url.path()) for url in urls) if path.suffix in self.filetypes]
            if self.paths:
                event.accept()

    def dropEvent(self, _):
        self.open(self.paths)

    def dragMoveEvent(self, event):
        pass

    def closeEvent(self, event):
        self.saveSettings()
        event.accept()

    def readSettings(self):
        self.settings = QSettings("INFINA", "Scratch View")
        self.resize(self.settings.value("size", QSize(1000, 500)))
        self.move(self.settings.value("pos", QPoint(100, 100)))
        if not self.settings.value("isMaximized", False):
            self.showMaximized()
        self.lastDir = self.settings.value("lastDir", self.lastDir)
        self.scaleCurrentName = self.settings.value(
            "scaleCurrentName", 'olympus')
        self.scaleCurrentValue = float(
            self.settings.value("scaleCurrentValue", 0.44))
        self.scales = self.settings.value("scales", self.scales)

    def saveSettings(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.settings.setValue("isMaximized", self.isMaximized())
        self.settings.setValue("lastDir", self.lastDir)
        self.settings.setValue("scaleCurrentName", self.scaleCurrentName)
        self.settings.setValue("scaleCurrentValue", self.scaleCurrentValue)
        self.settings.setValue("scales", self.scales)


class ScaleDialog(QDialog):
    def __init__(self, parent=None):
        super(QDialog, self).__init__(parent)
        self.parent = parent
        self.pushButtons = []
        self.trashIcon = QIcon.fromTheme('user-trash')
        self.trashIconWidth = self.trashIcon.pixmap(100).width()
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("Escala de microscopio")
        self.buttonGroup = QButtonGroup(self)
        self.vboxLayout = QVBoxLayout(self)

        for i, (nombre, escala) in enumerate(parent.scales.items()):
            self.addItem(i, nombre, escala)

        btnBox = QDialogButtonBox(self)
        btnBox.setStandardButtons(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        newScaleBtn = QPushButton("Nueva escala", btnBox)
        newScaleBtn.clicked.connect(lambda: self.newScale(self.dialog))
        btnBox.addButton(newScaleBtn, QDialogButtonBox.ButtonRole.ActionRole)
        self.vboxLayout.addWidget(btnBox)
        self.dialog.setLayout(self.vboxLayout)
        self.buttonGroup.buttonReleased.connect(parent.setScaleFromBtn)

        btnBox.accepted.connect(self.dialog.accept)
        btnBox.rejected.connect(self.dialog.close)
        self.btnBox = btnBox
        if len(self.buttonGroup.buttons()) == 1:
            self.disableTrashing()
        self.dialog.open()

    def removeItem(self, pushButton, radioButton, nombre, widget):
        if len(self.buttonGroup.buttons()) > 1:
            self.parent.eraseScale(nombre)
            self.buttonGroup.removeButton(radioButton)
            self.pushButtons.remove(pushButton)
            widget.close()

        if len(self.buttonGroup.buttons()) == 1:
            self.disableTrashing()

        self.checkItem(0)

    def addItem(self, i, nombre, escala):
        hbox = QWidget(self.dialog)
        hboxLayout = QHBoxLayout(self.dialog)
        button = QRadioButton(nombre, self.dialog)
        button.setChecked(nombre == self.parent.scaleCurrentName)
        self.buttonGroup.addButton(button)
        hboxLayout.addWidget(button)
        hboxLayout.addWidget(QLabel(str(escala)))
        if not self.trashIcon.isNull():
            hboxLayout.addWidget(borrar := QPushButton(self.trashIcon, ''))
            borrar.setFixedWidth(self.trashIconWidth//2)
        else:
            hboxLayout.addWidget(borrar := QPushButton('Borrar'))
        borrar.clicked.connect(lambda: self.removeItem(
            borrar, button, nombre, hbox))
        hbox.setLayout(hboxLayout)
        self.vboxLayout.insertWidget(i, hbox)
        self.pushButtons.append(borrar)
        return button

    def addItemAndCheck(self, i, nombre, escala):
        button = self.addItem(i, nombre, escala)
        button.setChecked(True)
        self.parent.setScaleFromText(nombre, escala)

    def checkItem(self, i):
        button = self.buttonGroup.buttons()[i]
        button.setChecked(True)
        self.parent.setScaleFromBtn(button)

    def enableTrashing(self):
        self.pushButtons[0].setEnabled(True)

    def disableTrashing(self):
        self.pushButtons[0].setEnabled(False)

    def newScale(self, parent):
        dialog = QDialog(parent)
        dialog.setWindowTitle("Nueva escala")
        layout = QFormLayout(dialog)
        layout.addRow("Nombre", nombre := QLineEdit())
        layout.addRow("Valor (um/pixel)", valor := QLineEdit())

        btnBox = QDialogButtonBox(dialog)
        btnBox.setStandardButtons(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btnBox)
        dialog.setLayout(layout)
        # deshabilita el Ok si no estan los dos campos llenos
        ok = btnBox.buttons()[0]
        ok.setDisabled(True)
        nombre.textChanged.connect(lambda: ok.setDisabled(
            False) if valor.text() else None)
        valor.textChanged.connect(lambda: ok.setDisabled(
            False) if nombre.text() else None)

        btnBox.accepted.connect(dialog.accept)
        btnBox.accepted.connect(self.enableTrashing)
        # selecciona ok en el dialogo anterior
        btnBox.accepted.connect(
            lambda: self.btnBox.buttons()[0].setFocus())
        # agrega el nuevo item al menu y lo selecciona
        btnBox.accepted.connect(
            lambda: self.addItemAndCheck(len(self.parent.scales.keys()), nombre.text(), valor.text()))
        btnBox.rejected.connect(dialog.close)
        dialog.open()


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

        self.x = 0
        self.fIn = 0
        self.line = None

        # TODO leerlas de los metadatos
        self.lineasMarcadas = []
        self.lineasMarcadasX = []
        self.lineasMarcadasXnp = np.array([])
        self.lines = []

        self.cursorOnLine = False
        self.closestLineIdx = 0

        self.moved = None
        self.point = None
        self.pressed = False
        self.start = False

        self.figureCanvas.mpl_connect(
            'button_press_event', self.mousePressEvent)
        self.figureCanvas.mpl_connect(
            'button_release_event', self.mouseReleaseEvent)
        self.figureCanvas.mpl_connect(
            'motion_notify_event', self.mouseMoveEvent)

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
        self.ax.set_xlabel(r"$\mathrm{Largo\ (\mu m)}$")
        self.ax.set_ylabel("Fuerza (N)")
        self.ax.set_title(title)
        self.figureCanvas.draw_idle()
        self.figure.tight_layout()

    def getfIn(self, x):
        try:
            idx = np.searchsorted(self.df['um'], x, side='left')
            return self.df.fIn[idx]
        except (ValueError, KeyError):
            return 0

    def mostrarLinea(self, point):
        if point.x() > -1:
            if not self.line:
                self.line = self.ax.axvline(self.x, ls='-.', color="gray")
            else:
                self.line.set(xdata=[self.x, self.x], visible=True)
        else:
            if self.line:
                self.line.set(visible=False)
        self.figureCanvas.draw()

    def marcarLinea(self, x, y):
        if self.line is not None:
            self.lineasMarcadas.append((self.x, self.fIn))
            self.lineasMarcadasX.append(self.x)
            self.lineasMarcadasXnp = np.array(self.lineasMarcadasX)
            self.line.set(ls=":", color="gray", alpha=0.5)
            self.lines.append(self.line)
            self.line = None

    def mousePressEvent(self, event):
        if self.ax.get_navigate_mode() != None:
            return
        if not event.inaxes:
            return
        if event.inaxes != self.ax:
            return
        if self.start:
            return
        self.point = event.xdata
        self.pressed = True

    def mouseReleaseEvent(self, event):
        if self.ax.get_navigate_mode() != None:
            return
        if not event.inaxes:
            return
        if event.inaxes != self.ax:
            return
        if self.cursorOnLine:
            self.lines.pop(self.closestLineIdx).remove()
            self.lineasMarcadasX.pop(self.closestLineIdx)
            self.lineasMarcadasXnp = np.array(self.lineasMarcadasX)
            self.figureCanvas.draw_idle()
            return
        # if self.pressed:
        #     self.pressed = False
        #     self.start = False
        #     self.point = None
        #     return

    def mouseMoveEvent(self, event):
        if self.ax.get_navigate_mode() != None:
            return
        if not event.inaxes:
            return
        # if not self.pressed:
        #     return
        if self.lineasMarcadasX:
            if np.min(m := np.abs(int(event.xdata) - self.lineasMarcadasXnp)) < 20:
                self.closestLineIdx = np.argmin(m)
                self.figureCanvas.set_cursor(Cursors.HAND)
                self.cursorOnLine = True
        elif self.cursorOnLine:
            self.figureCanvas.set_cursor(Cursors.POINTER)
            self.cursorOnLine = False


# Hay que hacer estas clases para poder tener drag & drop
class MyScene(QGraphicsScene):
    def dragEnterEvent(self, _):
        pass

    def dropEvent(self, _):
        pass

    def dragMoveEvent(self, _):
        pass


class MyProxy(QGraphicsProxyWidget):
    def dragEnterEvent(self, _):
        pass

    def dropEvent(self, _):
        pass

    def dragMoveEvent(self, _):
        pass


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

    author = "Marcel Goldschen-Ohm <marcel.goldschen@gmail.com>"
    version = '2.0.0'
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
        self.scene = MyScene()
        my_proxy = MyProxy()
        button = QPushButton()
        my_proxy.setWidget(button)
        my_proxy.setAcceptDrops(True)
        self.scene.addItem(my_proxy)
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
        # Button to add ROIs when option is enabled
        self.addROIsButton = Qt.MouseButton.RightButton

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
        self.drawROI = None

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

        self._image.height = self._image.pixmap().height()
        self._image.width = self._image.pixmap().width()

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

        scenePos = self.mapToScene(event.pos())

        # Draw ROI
        if (self.drawROI is not None) and (event.button() == self.addROIsButton) and (self.imagePos.y() >= 0):
            if self.drawROI == "Ellipse":
                # Click and drag to draw ellipse. +Shift for circle.
                pass
            elif self.drawROI == "Rect":
                # Click and drag to draw rectangle. +Shift for square.
                pass
            elif self.drawROI == "Line":
                # Click and drag to draw line.
                self.addLine(scenePos.x())
            elif self.drawROI == "Polygon":
                # Click to add points to polygon. Double-click to close polygon.
                pass

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

        # scenePos = self.mapToScene(event.pos())
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

        # try:
        #     if self.wheelZoomFactor == 1:
        #         return
        #
        #     # self.setTransformationAnchor(
        #     #     QGraphicsView.ViewportAnchor.NoAnchor)
        #     # self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        #
        #     # # Save the scene pos
        #     # oldPos = self.mapToScene(
        #     #     int(event.position().x()), int(event.position().y()))
        #     # # oldPos = event.globalPosition()
        #     #
        #     # # Zoom
        #     # if event.angleDelta().y() > 0:
        #     #     zoomFactor = self.wheelZoomFactor
        #     # else:
        #     #     zoomFactor = 1 / self.wheelZoomFactor
        #     # self.scale(zoomFactor, zoomFactor)
        #     #
        #     # # Get the new position
        #     # newPos = self.mapToScene(
        #     #     int(event.position().x()), int(event.position().y()))
        #     #
        #     # # Move scene to old position
        #     # delta = newPos - oldPos
        #     # self.translate(delta.x(), delta.y())
        #
        #     if event.angleDelta().y() > 0:
        #         # zoom in
        #         if len(self.zoomStack) == 0:
        #             self.zoomStack.append(self.sceneRect())
        #         elif len(self.zoomStack) > 1:
        #             del self.zoomStack[:-1]
        #         zoomRect = self.zoomStack[-1]
        #         # center = zoomRect.center()
        #         # center = event.position()
        #         center = self.mapToScene(
        #             int(event.position().x()), int(event.position().y()))
        #         zoomRect.setWidth(zoomRect.width() / self.wheelZoomFactor)
        #         zoomRect.setHeight(zoomRect.height() /
        #                            self.wheelZoomFactor)
        #         zoomRect.moveCenter(center)
        #         self.zoomStack[-1] = zoomRect.intersected(self.sceneRect())
        #         self.updateViewer()
        #         self.viewChanged.emit()
        #     else:
        #         # zoom out
        #         if len(self.zoomStack) == 0:
        #             # Already fully zoomed out.
        #             return
        #         if len(self.zoomStack) > 1:
        #             del self.zoomStack[:-1]
        #         zoomRect = self.zoomStack[-1]
        #         # center = zoomRect.center()
        #         # center = event.position()
        #         center = self.mapToScene(
        #             int(event.position().x()), int(event.position().y()))
        #         zoomRect.setWidth(zoomRect.width() * self.wheelZoomFactor)
        #         zoomRect.setHeight(zoomRect.height() *
        #                            self.wheelZoomFactor)
        #         zoomRect.moveCenter(center)
        #         self.zoomStack[-1] = zoomRect.intersected(self.sceneRect())
        #         if self.zoomStack[-1] == self.sceneRect():
        #             self.zoomStack = []
        #         self.updateViewer()
        #
        #     print(center)
        #
        #     self.viewChanged.emit()
        #     event.accept()
        # except Exception as e:
        #     print(e)
        # return

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

    def addLine(self, x):
        line = LineROI(self)
        line.setLine(x, 0, x, self._image.height)
        self.scene.addItem(line)
        self.ROIs.append(line)

    def addSpots(self, points, radius):
        for point in points:
            x, y = point
            spot = EllipseROI(self)
            spot.setRect(x - radius, y - radius, 2 * radius, 2 * radius)
            self.scene.addItem(spot)
            self.ROIs.append(spot)


class EllipseROI(QGraphicsEllipseItem):

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
    from PyQt6.QtWidgets import QApplication

    def my_exception_hook(exctype, value, traceback):
        # Print the error and traceback
        print(exctype, value, traceback)
        errorDialog(mainwindow, exctype, traceback)
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
    # viewer.zoomOutButton = Qt.MouseButton.RightButton  # set to None to disable
    viewer.zoomOutButton = None  # set to None to disable

    # Mouse wheel zooming.
    viewer.wheelZoomFactor = 1.25  # Set to None or 1 to disable

    # Allow panning with the middle mouse button.
    viewer.panButton = Qt.MouseButton.LeftButton  # set to None to disable

    # Load an image file to be displayed (will popup a file dialog).
    img = "/home/marco/documents/fac/tesis2/ensayos2/CrCrN/M1402C/scratch/5-60.jpg"
    csv = "/home/marco/documents/fac/tesis2/ensayos2/CrCrN/M1402C/scratch/M1402_5-60_1.csv"
    mainwindow.open([Path(img), Path(csv)])

    # Handle left mouse clicks with your own custom slot
    # handleLeftClick(x, y). (x, y) are image coordinates.
    # For (row, col) matrix indexing, row=y and col=x.
    # QtImageViewer also provides similar signals for
    # left/right mouse button press, release and doubleclick.
    # Here I bind the slot to leftMouseButtonReleased only because
    # the leftMouseButtonPressed signal will not be emitted due to
    # left clicks being handled by the regionZoomButton.
    # viewer.middleMouseButtonReleased.connect(handleLeftClick)

    # Show the viewer and run the application.formlayout
    # mainwindow.show()
    sys.exit(app.exec())
