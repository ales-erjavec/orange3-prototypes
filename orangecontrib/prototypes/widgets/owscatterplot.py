import sys

from types import SimpleNamespace
from typing import List, Sequence, Optional, NamedTuple

import numpy as np

from PyQt5.QtCore import Qt, QSize, QAbstractListModel
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QVector3D, QColor
from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QApplication, QGroupBox, QListView
)

from PyQt5.QtDataVisualization import (
    QScatterDataItem, QScatter3DSeries, QScatterDataProxy, Q3DScatter, Q3DTheme
)

import Orange.data
from Orange.widgets import widget
from Orange.widgets.utils import itemmodels, colorbrewer


class Data(SimpleNamespace):
    xyz = ...  # type: np.ndarray
    mask = ...  # type: np.ndarray


class Models(SimpleNamespace):
    x = ...  # type: QAbstractListModel
    y = ...  # type: QAbstractListModel
    z = ...  # type: QAbstractListModel
    color = ...  # type: QAbstractListModel
    shape = ...  # type: QAbstractListModel
    size = ...   # type: QAbstractListModel

    def __init__(self, parent=None):
        self.x = itemmodels.VariableListModel(parent)
        self.y = itemmodels.VariableListModel(parent)
        self.z = itemmodels.VariableListModel(parent)
        self.color = itemmodels.VariableListModel(parent)
        self.shape = itemmodels.VariableListModel(parent)
        self.size = itemmodels.VariableListModel(parent)


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

        self._plotdata = SimpleNamespace()
        self.models = Models(

        )
        self.models = SimpleNamespace()
        self.models.x = itemmodels.VariableListModel(parent=self)
        self.models.y = itemmodels.VariableListModel(parent=self)
        self.models.z = itemmodels.VariableListModel(parent=self)
        self.models.color = itemmodels.VariableListModel(parent=self)
        self.models.shape = itemmodels.VariableListModel(parent=self)
        self.models.size = itemmodels.VariableListModel(parent=self)

        box = QGroupBox("Axes")
        form = QFormLayout(
            # labelAlignment=Qt.AlignLeft,
            fieldGrowthPolicy=QFormLayout.AllNonFixedFieldsGrow,
        )

        def combobox(*args, **kwargs):
            cb = QComboBox(
                *args,
                minimumContentsLength=12,
                sizeAdjustPolicy=QComboBox.AdjustToMinimumContentsLengthWithIcon,
                **kwargs
            )
            view = cb.view()  # type: QListView
            assert isinstance(view, QListView)
            view.setUniformItemSizes(True)
            return cb

        self.axesgui = SimpleNamespace()
        self.axesgui.x = combobox(
            self, objectName="cb-x", activated=self._updateplot)
        self.axesgui.y = combobox(
            self, objectName="cb-y", activated=self._updateplot)
        self.axesgui.z = combobox(
            self, objectName="cb-z", activated=self._updateplot)
        self.axesgui.color = combobox(
            self, objectName="cb-color", activated=self._updateplot)
        self.axesgui.shape = combobox(
            self, objectName="cb-shape", activated=self._updateplot)
        self.axesgui.size = combobox(
            self, objectName="cb-size", activated=self._updateplot)

        self.axesgui.x.setModel(self.models.x)
        self.axesgui.y.setModel(self.models.y)
        self.axesgui.z.setModel(self.models.z)
        self.axesgui.color.setModel(self.models.color)
        # self.axesgui.shape.setModel(self.models.shape)

        form.addRow("X", self.axesgui.x)
        form.addRow("Y", self.axesgui.y)
        form.addRow("Z", self.axesgui.z)

        form.addRow("Color", self.axesgui.color)
        form.addRow("Shape", self.axesgui.shape)
        form.addRow("Size", self.axesgui.size)

        box.setLayout(form)
        self.controlArea.layout().addWidget(box)
        self.controlArea.layout().addStretch()

        self.__scatter = Q3DScatter()
        self.__scatter.setShadowQuality(Q3DScatter.ShadowQualityNone)
        self.__scatter.setOptimizationHints(Q3DScatter.OptimizationStatic)
        # self.__scatter.setActiveTheme(Q3DTheme(Q3DTheme.ThemeIsabelle))
        self.mainArea.layout().addWidget(
            QWidget.createWindowContainer(self.__scatter)
        )

    def sizeHint(self):
        return super().sizeHint().expandedTo(QSize(1027, 900))

    def clear(self):
        for series in self.__scatter.seriesList():
            self.__scatter.removeSeries(series)
        self._plotdata = SimpleNamespace()

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
            self.models.x[:] = primary
            self.models.y[:] = primary
            self.models.z[:] = primary

            self.models.color[:] = primary
            self.models.shape[:] = varsdisc
            self.models.size[:] = primary

            self.axesgui.x.setCurrentIndex(0)
            self.axesgui.y.setCurrentIndex(1)
            self.axesgui.z.setCurrentIndex(2)
            self._plotdata.data = None

            def data_(var):
                values, mask = get_column_data(data, vars)
                return values, mask

            self._plotdata.data_source = data_
        self._update()

    def set_subset_data(self, subset):
        self._plotdata.subsetmask = None
        self._plotdata.subsetids = None
        if subset is not None:
            self.__plotdata.subsetids = subset.ids
        self._update()

    def _update(self):
        # sch update
        ...

    def handleNewSignals(self):
        self._updateplot()

    def _updateplot(self):
        xi = self.axesgui.x.currentIndex()
        yi = self.axesgui.y.currentIndex()
        zi = self.axesgui.z.currentIndex()

        varx = self.models.x[xi]
        vary = self.models.y[yi]
        varz = self.models.z[zi]

        x, _ = self.data.get_column_view(varx)
        y, _ = self.data.get_column_view(vary)
        z, _ = self.data.get_column_view(varz)

        xymask = np.isfinite(x) & np.isfinite(y)

        ci = self.axesgui.color.currentIndex()
        color_dims = shape_dims = 1
        varcolor = varshape = None

        if ci != -1:
            varcolor = self.models.color[ci]
            color, _ = self.data.get_column_view(varcolor)
            if varcolor.is_continuous:
                mask = np.isfinite(color)
                color_non_na = color[mask]
                if color_non_na.size > 0:
                    cmin, cmax = np.min(color_non_na), np.max(color_non_na)
                else:
                    cmin, cmax = 0., 1.0
                color_dims = 256
                edges = np.linspace(cmin, cmax, color_dims - 1, endpoint=True)
                color = np.empty_like(color, dtype=np.uint8)
                color[mask] = np.digitize(color_non_na, bins=edges) - 1
                color[~mask] = np.iinfo(np.uint8).max
                # print(color)
                color_map = "jet"
            else:
                mask = np.isfinite(color)
                color_non_na = color[mask]
                color = color.astype(np.intp)
                color_map = ...
                color_dims = len(varcolor.values) + 1
        else:
            color = np.zeros(x.shape, int)

        varshape = self.axesgui.shape.currentIndex()
        if varshape != -1:
            shape, _ = self.data.get_column_view(varshape)
        else:
            shape = np.zeros(x.shape, int)

        series = []

        group = np.ravel_multi_index((color, shape), dims=(color_dims, shape_dims))
        keys, indices = group_by_indices(group)
        theme = self.__scatter.activeTheme()  # type: Q3DTheme
        base_colors = theme.baseColors()
        base_colors = colorbrewer.colorSchemes["qualitative"]["Dark2"][8]
        base_colors = [QColor(*c) for c in base_colors]
        mesh_smooth = x.size < 300
        base_mesh = [QScatter3DSeries.MeshPoint]
        for group, gindices in zip(keys, indices):
            color_i, shape_i = np.unravel_index(group, (color_dims, shape_dims))
            array = [QScatterDataItem(QVector3D(*t))
                     for t in zip(x[gindices], y[gindices], z[gindices])]
            ser = QScatter3DSeries()
            ser.setItemLabelFormat(
                "@xTitle: @xLabel @yTitle: @yLabel @zTitle: @zLabel"
            )
            # print(color_i, len(base_colors))

            ser.setMeshSmooth(mesh_smooth)
            ser.dataProxy().addItems(array)
            ser.setBaseColor(base_colors[color_i % len(base_colors)])
            ser.setMesh(QScatter3DSeries.MeshPoint)
            series.append(ser)

        self.__scatter.axisX().setTitle(self.axesgui.x.currentText())
        self.__scatter.axisY().setTitle(self.axesgui.y.currentText())
        self.__scatter.axisZ().setTitle(self.axesgui.z.currentText())

        # array = [QScatterDataItem(QVector3D(*t)) for t in zip(x, y, z)]
        # ser = QScatter3DSeries()
        # ser.setItemLabelFormat(
        #     "@xTitle: @xLabel @yTitle: @yLabel @zTitle: @zLabel"
        # )
        # ser.setMeshSmooth(True)
        # ser.dataProxy().addItems(array)

        for _ser in self.__scatter.seriesList():
            self.__scatter.removeSeries(_ser)

        for ser in series:
            self.__scatter.addSeries(ser)


def group_by_indices(ar):
    isort = np.argsort(ar)
    ar = ar[isort]
    inverse = np.empty_like(isort)
    inverse[isort] = np.arange(isort.size)
    diff = np.empty(isort.shape, dtype=np.bool_)
    diff[0] = True
    np.not_equal(ar[:-1], ar[1:], out=diff[1:])
    uidx = np.flatnonzero(diff)
    unq = ar[uidx]
    if unq.size == 0:
        return [], []
    elif unq.size == 1:
        return unq, [inverse]
    else:
        return unq, np.split(inverse, uidx[1:])


from numbers import Integral
from typing import Union


def get_column_data(data, column, dtype=None):
    # type: (Orange.data.Table, Union[int, Orange.data.Variable]) -> np.ma.MaskedArray
    d, isview = data.get_column_view(column)
    var = data.domain[column] # type: Orange.data.Variable

    if var.is_primitive and not np.issubdtype(d.dtype, np.inexact):
        d = d.astype(np.float)

    if var.is_primitive():
        pass


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
