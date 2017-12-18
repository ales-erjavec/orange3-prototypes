import sys

from types import SimpleNamespace
from typing import List, Sequence, Optional

import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QVector3D
from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QApplication, QGroupBox
)



from PyQt5.QtDataVisualization import (
    QScatterDataItem, QScatter3DSeries, QScatterDataProxy, Q3DScatter
)

import Orange.data
from Orange.widgets import widget
from Orange.widgets.utils import itemmodels


class Data(SimpleNamespace):
    xyz = ...  # type: np.ndarray
    mask = ...  # type: nd.ndarray


class OWScatterPlot(widget.OWWidget):
    name = "Scatter 3D"

    inputs = [
        ("Data", Orange.data.Table, "set_data", widget.Default),
        ("Subset", Orange.data.Table, "set_subset_data")
    ]

    var_x = None
    var_y = None
    var_z = None

    var_color = None
    var_size = None
    var_shape = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = None  # type: Optional[Orange.data.Table]

        self._inputs = SimpleNamespace()
        self._inputs.data = None  # type: Optional[Orange.data.Table]
        self._inputs.subset = None  # type: Optional[Orange.data.Table]

        self.models = SimpleNamespace()
        self.models.varx = itemmodels.VariableListModel(parent=self)
        self.models.vary = itemmodels.VariableListModel(parent=self)
        self.models.varz = itemmodels.VariableListModel(parent=self)
        self.models.color = itemmodels.VariableListModel(parent=self)
        self.models.shape = itemmodels.VariableListModel(parent=self)
        self.models.size = itemmodels.VariableListModel(parent=self)

        box = QGroupBox("Axes")
        form = QFormLayout(
            labelAlignment=Qt.AlignLeft,
            fieldGrowthPolicy=QFormLayout.AllNonFixedFieldsGrow,
        )

        self.axesgui = SimpleNamespace()
        self.axesgui.cbx = QComboBox(
            self, objectName="cb-x", activated=self._updateplot)
        self.axesgui.cby = QComboBox(
            self, objectName="cb-y", )
        self.axesgui.cbz = QComboBox(
            self, objectName="cb-z", activated=self._updateplot)
        self.axesgui.color = QComboBox(
            self, objectName="cb-color", activated=self._updateplot)
        self.axesgui.shape = QComboBox(
            self, objectName="cb-shape", activated=self._updateplot)
        self.axesgui.size = QComboBox(
            self, objectName="cb-size", activated=self._updateplot)

        self.axesgui.cbx.setModel(self.models.varx)
        self.axesgui.cby.setModel(self.models.vary)
        self.axesgui.cbz.setModel(self.models.varz)

        form.addRow("X", self.axesgui.cbx)
        form.addRow("Y", self.axesgui.cby)
        form.addRow("Z", self.axesgui.cbz)

        form.addRow("Color", self.axesgui.color)
        form.addRow("Shape", self.axesgui.shape)
        form.addRow("Size", self.axesgui.size)

        box.setLayout(form)
        self.controlArea.layout().addWidget(box)
        self.controlArea.layout().addStretch()

        self.__scatter = Q3DScatter()
        self.mainArea.layout().addWidget(
            QWidget.createWindowContainer(self.__scatter)
        )

    def clear(self):
        # self.plot.clear()
        self._plotdata = None

    def set_data(self, data):
        # type: (Optional[Orange.data.Table]) -> None
        self.clear()
        self._inputs.data = data

        self.data = data
        if data is not None:
            domain = data.domain
            vars = domain.variables + domain.metas
            primary = [var for var in vars if var.is_primitive()]
            aux = [var for var in vars if not var.is_primitive()]
            varsdisc = [var for var in primary if var.is_discrete]
            self.variables = primary
            self.auxvariables = aux
            self.models.varx[:] = primary
            self.models.vary[:] = primary
            self.models.varz[:] = primary

            self.models.color[:] = primary
            self.models.shape[:] = varsdisc
            self.models.size[:] = primary

            self.axesgui.cbx.setCurrentIndex(0)
            self.axesgui.cby.setCurrentIndex(1)
            self.axesgui.cbz.setCurrentIndex(2)

        self._update()

    def set_subset_data(self, subset):
        self.__plotdata.subsetmask = None
        self.__plotdata.subsetids = None
        if subset is not None:
            self.__plotdata.subsetids = subset.ids
        self._update()

    def _update(self):
        # sch update
        ...

    def handleNewSignals(self):
        self._updateplot()

    def _updateplot(self):
        varx = self.axesgui.cbx.currentIndex()
        vary = self.axesgui.cby.currentIndex()
        varz = self.axesgui.cbz.currentIndex()

        x, _ = self.data.get_column_view(varx)
        y, _ = self.data.get_column_view(vary)
        z, _ = self.data.get_column_view(varz)

        array = [QScatterDataItem(QVector3D(*t)) for t in zip(x, y, z)]
        ser = QScatter3DSeries()
        ser.dataProxy().addItems(array)

        for _ser in self.__scatter.seriesList():
            self.__scatter.removeSeries(_ser)

        self.__scatter.addSeries(ser)


def main(argv=None):
    if argv is None:
        argv = list(sys.argv)
    app = QApplication(argv)
    argv = app.arguments()
    if len(argv) > 1:
        filename = argv[1]
    else:
        filename = "iris.tab"
    data = Orange.data.Table(filename)

    w = OWScatterPlot()
    w.show()
    w.set_data(data)
    w.handleNewSignals()
    app.exec()
    w.onDeleteWidget()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
