from AnyQt.QtCore import QObject, QSizeF, QRectF
from AnyQt.QtGui import QTextObjectInterface, QTextDocument, QTextFormat, \
    QPainter
from AnyQt.QtSvg import QSvgRenderer


SvgTextFormat = QTextFormat.UserObject + 0x576
SvgData = 1


class SvgTextObject(QObject, QTextObjectInterface):
    SvgTextFormat = SvgTextFormat
    SvgData = SvgData

    def __init__(self, parent=None, **kwargs,):
        super().__init__(parent, **kwargs)
        # self.__contents = contents
        self.__cached_renderer = None

    def __renderer(self, contents) -> QSvgRenderer:
        if isinstance(contents, str):
            contents = contents.encode("utf-8")
        return QSvgRenderer(contents)

    def intrinsicSize(
            self, doc: QTextDocument, posInDocument: int, format: QTextFormat
    ) -> QSizeF:
        contents = format.property(SvgData)
        renderer = self.__renderer(contents)
        vb = renderer.viewBox()
        if vb.isValid():
            return QSizeF(vb.size())
        else:
            return QSizeF(renderer.defaultSize())

    def drawObject(
            self, painter: QPainter, rect: QRectF, doc: 'QTextDocument',
            posInDocument: int, format: QTextFormat
    ) -> None:
        renderer = self.__renderer(format.property(SvgData))
        renderer.render(painter, rect)
