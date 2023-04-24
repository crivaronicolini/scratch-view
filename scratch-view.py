""" Scratch View: Analizador de ensayos de rayado.
Licence at the end of the file.
"""

__author__ = "Marco Crivaro Nicolini <mcn.hola@gmail.com>"
__version__ = 0.1
__year__ = 2023
__org__ = "INFINA, FCEN UBA"
__website__ = 'https://github.com/crivaronicolini/scratch-view/'

from pathlib import Path
import platform
import traceback

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from matplotlib.backend_tools import Cursors

from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal, QSize, QProcess, QSettings
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import QToolBar, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel, QMessageBox, QPushButton, QDialog, QRadioButton, QButtonGroup, QDialogButtonBox, QFormLayout, QLineEdit
from QtImageViewer import QtImageViewer


def errorDialog(parent, title, message):
    print(message)
    QMessageBox.critical(parent, str(title), message)
    return


class MainWindow(QMainWindow):
    def __init__(self, ):
        QMainWindow.__init__(self)
        self.icon = QIcon()
        self.icon.addFile('iconf512.svg', QSize(512, 512))
        self.setWindowIcon(self.icon)
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

        helpMenu = menuBar.addMenu("Ayuda")
        helpMenu.addAction(self.showTutorialAction)
        helpMenu.addAction(self.showAboutAction)

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

        self.showTutorialAction = QAction("Tutorial", self)
        self.showTutorialAction.triggered.connect(self.showTutorial)

        self.showAboutAction = QAction("Sobre Scratch View", self)
        self.showAboutAction .triggered.connect(self.showAbout)

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

    def showAbout(self):
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Sobre Scratch View")
        msgBox.setTextFormat(Qt.TextFormat(Qt.TextFormat.RichText))
        msgBox.setText(
            f"<center><p><img src='icone128.png' width=128></img></p><h3>Scratch View    </h3></center>")
        msgBox.setInformativeText(
            f"<center><p>{__version__}</p><p>Analiza ensayos de rayado</p><p><a href='{__website__}'>Web</a></p><p>{__author__}, {__year__}</p><p><small>{__org__}</small></p><p><small>Este programa no brinda absolutamente ninguna garantia.<br>Ver la <a href='https://www.gnu.org/licenses/gpl-3.0.html'>licencia GPL version 2 o superior</a> para mas informacion</small></p></center>")
        msgBox.open()

    def showTutorial(self):
        pass


class ScaleDialog(QDialog):
    def __init__(self, parent):
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
    # mainwindow.open([Path(img), Path(csv)])

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

"""
Copyright (C) 2023  Marco Crivaro Nicolini

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
