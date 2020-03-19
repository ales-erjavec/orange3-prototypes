import math
import re
import json
from xml.sax.saxutils import escape
from types import SimpleNamespace as namespace

from typing import (
    cast, Optional, TypeVar, List, Dict, Callable, SupportsFloat, Union
)
from AnyQt.QtCore import Qt, QSize, QRect, QEvent, QObject, Signal
from AnyQt.QtGui import (
    QTextCursor, QFontDatabase, QFont, QKeyEvent, QKeySequence,
    QTextCharFormat
)
from AnyQt.QtWidgets import (
    QWidget, QPlainTextEdit, QTextEdit, QGridLayout, QVBoxLayout, QLabel,
    QCompleter, QToolTip, QSizePolicy, QScrollArea, QTextBrowser
)
from qtconsole.client import QtKernelClient
from qtconsole.manager import QtKernelManager

from qtconsole.base_frontend_mixin import BaseFrontendMixin
from qtconsole.pygments_highlighter import PygmentsHighlighter

from orangewidget.utils.itemmodels import PyListModel

from orangecontrib.prototypes.widgets.utils.kernel_client import remove_ansi_control
from orangecontrib.prototypes.widgets.utils.editor import TextEditShortcutFilter
from orangecontrib.prototypes.widgets.utils.kernel_client import on_reply
from orangecontrib.prototypes.widgets.utils.svgtextobject import SvgTextObject

T = TypeVar("T")


class Cell(namespace):
    cell_type: str
    metadata: dict = {}
    source: str = ""

    def __init__(self, source="", metadata={}, **kwargs):
        super().__init__(**kwargs)
        self.source = source
        self.metadata = dict(metadata)


class CodeCell(Cell):
    cell_type = "code"
    execution_count: Optional[int]

    def __init__(self, source="", metadata={}, execution_count=None, **kwargs):
        super().__init__(source, metadata, **kwargs)
        self.execution_count = execution_count


class MarkdownCell(Cell):
    cell_type = "markdown"


class RawCell(Cell):
    cell_type = "raw"


class TextEditFocusNavigationFilter(QObject):
    """
    Simple key press filter installed on Q(Plain)TextEdit that moves
    focus prev/next when cursor reaches top/bottom
    """
    _keys = {Qt.Key_Up, Qt.Key_Down}

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.KeyPress and isinstance(obj, QPlainTextEdit):
            event = cast(QKeyEvent, event)
            if event.key() in self._keys:
                return self.move_focus_for_event(obj, event)
        return super().eventFilter(obj, event)

    @staticmethod
    def move_focus_for_event(widget: QPlainTextEdit, event: QKeyEvent) -> bool:
        parent = widget.parent()
        if event.key() == Qt.Key_Down:
            cursor = widget.textCursor()
            block = cursor.blockNumber()
            block_count = widget.blockCount()

            if block_count == 0 or block == block_count - 1:
                parent.focusNextChild()
                event.accept()
                return True
        elif event.key() == Qt.Key_Up:
            cursor = widget.textCursor()
            if cursor.blockNumber() == 0:
                parent.focusPreviousChild()
                return True
        return False


class VisibilityChangeFilter(QObject):
    #: Emitted when the visibilit of an observed object changes (note: when
    #: the widget is show/hidden to its immediate parent)
    visibilityChanged = Signal(bool)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.ShowToParent:
            self.visibilityChanged.emit(True)
        if event.type() == QEvent.HideToParent:
            self.visibilityChanged.emit(False)
        return super().eventFilter(obj, event)


class _CellLayout(QGridLayout):
    def addRow(self, label: Optional[QLabel], editor: QWidget):
        self.insertRow(self.rowCount(), label, editor)

    def insertRow(self, index: int, label, widget: QWidget):
        if label is not None:
            self.addWidget(label, index, 0, alignment=Qt.AlignRight | Qt.AlignTop)
        self.addWidget(widget, index, 1)


def append_plain_text(view, text):
    cursor: QTextCursor = view.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertText(text)


def append_html_contents(view, content: str):
    cursor: QTextCursor = view.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertHtml(content)


def append_svg_contents(view: QTextEdit, content: str):
    cursor: QTextCursor = view.textCursor()
    cursor.movePosition(QTextCursor.End)
    insert_svg_contents(cursor, content)


def insert_svg_contents(cursor: QTextCursor, contents: Union[str, bytes]):
    """
    Insert a svg contents at the cursor position.

    Parameters
    ----------
    cursor: QTextCursor
    contents: Union[str, bytes]

    Returns
    -------

    """
    if cursor.isNull():
        return
    layout = cursor.document().documentLayout()
    interface = layout.findChild(SvgTextObject)
    if interface is None:
        interface = SvgTextObject(layout)
        interface.setParent(layout)
        layout.registerHandler(interface.SvgTextFormat, interface)

    cformat = QTextCharFormat()
    cformat.setObjectType(SvgTextObject.SvgTextFormat)
    cformat.setProperty(SvgTextObject.SvgData, contents)
    cursor.insertText("\N{Object Replacement Character}", cformat)


def qtextcursor_prev_char(cursor: QTextCursor) -> str:
    """Return the character string preceding the current cursor position."""
    cursor = QTextCursor(cursor)
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.KeepAnchor)
    return cursor.selectedText()


class _CellData:
    #: The current pending execute_request message id
    execute_request_msg_id: Optional[str] = None
    #: The cell source editor widget
    editor: QWidget
    #: The cell output view
    output: QWidget
    #: The cell execution count
    execution_count: Optional[int] = None
    #: Clear cell output
    clearoutput: Callable[[], None]
    #: Cell source
    source: Callable[[], str]
    #: The cell output contents. A sequence of jupyter messages as received
    #: for the current/last 'execution_request'
    output_content = List[dict]

    def __init__(self):
        self.output_content = []

    def append_stream_output(self, data):
        self.output_content.append(data)
        view = self.output


def ceil(x: SupportsFloat) -> int:
    return int(math.ceil(x))


class NotebookEditor(QWidget, BaseFrontendMixin):
    def __init__(self, parent=None, kernel_client=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.kernel_client = kernel_client
        ffont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font = QFont()
        font.setFamily(ffont.family())
        self.setFont(font)
        self._cells: List[_CellData] = []
        self.__layout = layout = _CellLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self._focus_nav = TextEditFocusNavigationFilter(self)
        self._execute_shortcut_filter = TextEditShortcutFilter(
            QKeySequence(Qt.ShiftModifier | Qt.Key_Return), self
        )
        self._execute_shortcut_filter.activated.connect(self._execute_activated)

        self._execute_msg_ids = {}  # type: Dict[str, _CellData]

    def append_cell(self, cell: Cell):
        layout = self.__layout
        index = layout.rowCount()
        if isinstance(cell, CodeCell):
            self._insert_code_cell(cell, index)
        elif isinstance(cell, MarkdownCell):
            self._insert_markdown_cell(cell, index)
        elif isinstance(cell, RawCell):
            self._insert_raw_cell(cell, index)

    def _insert_code_cell(self, cell: CodeCell, index: int):
        layout = self.__layout
        if not 0 <= index < layout.rowCount():
            index = layout.rowCount()
        if cell.execution_count:
            prompt_text = f"In [{cell.execution_count:}]:"
            out_prompt_text = f"Out [{cell.execution_count:}]:"
        else:
            prompt_text = f"In [ ]:"
            out_prompt_text = f"Out [ ]:"

        label = QLabel(prompt_text)
        label.setProperty("class", "input-prompt-label")
        editor = CellSourceEditor(
            kernel_client=self.kernel_client,
            sizePolicy=QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        )

        editor.setPlainText(cell.source)
        self._setup_editor_filters(editor)
        margin = ceil(editor.document().documentMargin())
        label.setMargin(margin)
        layout.insertRow(index, label, editor)

        output = RichOutputView(visible=False)
        output.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        output.setReadOnly(True)
        output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        output.setFocusPolicy(Qt.NoFocus)
        output._label = QLabel(out_prompt_text, visible=False)
        output._label.setProperty("class", "output-prompt-label")
        vizfilter = VisibilityChangeFilter(output)
        output.installEventFilter(vizfilter)
        vizfilter.visibilityChanged.connect(output._label.setVisible)

        layout.insertRow(index + 1, output._label, output)

        def set_execution_count(count):
            if count is not None:
                count = str(count)
            else:
                count = " "
            label.setText(f"In [{count}]")
            output._label.setText(f"Out [{count}]")

        data = _CellData()
        data.output_content = []
        data.editor = editor
        data.output = output
        data.clearoutput = output.clear
        data.source = editor.source
        data.set_execution_count = set_execution_count
        self._cells.insert(index, data)

    def _insert_markdown_cell(self, cell: MarkdownCell, index: int):
        layout = self.__layout
        if not 0 <= index < layout.rowCount():
            index = layout.rowCount()

        view = QPlainTextEdit()
        view.setPlainText(cell.source)
        view.installEventFilter(self._focus_nav)
        layout.addWidget(view, index, 1)

    def _insert_raw_cell(self, cell: Cell, index: int):
        layout = self.__layout
        if not 0 <= index < layout.rowCount():
            index = layout.rowCount()

        view = QPlainTextEdit()
        view.setPlainText(cell.source)
        view.installEventFilter(self._focus_nav)
        layout.addWidget(view, index, 1)

    def _setup_editor_filters(self, editor: QWidget):
        editor.installEventFilter(self._focus_nav)
        editor.installEventFilter(self._execute_shortcut_filter)

    def _remove_cell(self, index):
        layout = self.__layout
        if not 0 <= index < layout.rowCount():
            return
        it1, it2 = layout.itemAtPos(index, 0), layout.itemAtPos(index, 1)
        if it1 is not None:
            layout.removeItem(it1)
        if it2 is not None:
            layout.removeItem(it2)

    def _execute_activated(self, editor: QWidget):
        for i, cell in enumerate(self._cells):
            if cell.editor is editor:
                self.execute_cell(i)
                self.focusNextChild()
                return

    def execute_cell(self, index):
        cell = self._cells[index]
        old_msg_id = cell.execute_request_msg_id
        self._execute_msg_ids.pop(old_msg_id, None)
        source = cell.source()
        cell.clearoutput()
        cell.execute_request_msg_id = self.kernel_client.execute(source, )
        self._execute_msg_ids[cell.execute_request_msg_id] = cell

    def _handle_image_display_data(self, cell: _CellData, data: dict):
        image_data = {key: value for key, value in data.items()
                      if key.startswith("image/")}
        mimetype, payload = image_data.popitem()
        view = cell.output
        if isinstance(view, QPlainTextEdit):
            # no rich content in view
            text = data.get("text/plain", "")
            if text:
                append_plain_text(view, text)
                view.setVisible(True)
            return

        if mimetype == "image/png":
            # image/png already comes base64 encoded
            data = "data:image/png;base64," + payload
            append_html_contents(view, f'<br/><img src="{data}" />')
        elif mimetype == "image/svg+xml":
            append_plain_text(view, "\n")
            append_svg_contents(view, payload.encode("utf-8"))
        else:
            return

    def _handle_html_display_data(self, cell: _CellData, data: dict):
        view = cell.output
        content = data.get("text/html", "")
        print("Html data", data)
        if isinstance(view, QTextEdit):
            append_html_contents(view, content)
        # ?? convert to plain text ??

    # --------------------------------------------------------------------------
    # BaseFrontendMixin
    # --------------------------------------------------------------------------
    def _handle_execute_reply(self, msg):
        parent_msg_id = msg.get("parent_header", {}).get('msg_id')
        cell = self._execute_msg_ids.get(parent_msg_id)
        print(msg)
        if cell is not None:
            content = msg.get("content", {})
            status = content["status"]
            if status == "error":
                tb = remove_ansi_control("\n".join(content.get("traceback", [])))
                if tb:
                    append_plain_text(cell.output, tb)
                    cell.output.setVisible(True)

            cell.set_execution_count(content.get("execution_count", None))

    def _handle_execute_result(self, msg):
        parent_msg_id = msg.get("parent_header", {}).get('msg_id')
        cell = self._execute_msg_ids.get(parent_msg_id)
        if cell is not None:
            content = msg.get("content", {})
            data = content.get("data", {})
            text = data.get("text/plain", "")
            if text:
                append_plain_text(cell.output, text)
                cell.output.setVisible(True)
            cell.set_execution_count(content.get("execution_count", None))
            cell.output_content.append(data)

    def _handle_display_data(self, msg):
        parent_msg_id = msg.get("parent_header", {}).get('msg_id')
        cell = self._execute_msg_ids.get(parent_msg_id)
        if cell is not None:
            content = msg.get("content", {})
            data = content.get("data", {})
            image_data = {key: value for key, value in data.items()
                          if key.startswith("image/")}
            if image_data:
                self._handle_image_display_data(cell, image_data)
                return
            html_data = data.get("text/html", "")
            if html_data:
                self._handle_html_display_data(cell, data)

    def _handle_stream(self, msg):
        parent_msg_id = msg.get("parent_header", {}).get('msg_id')
        cell = self._execute_msg_ids.get(parent_msg_id)
        if cell is not None:
            content = msg.get("content", {})
            text = content.get("text", "")
            name = content.get("name")  # 'stdout' or stderr
            if text:
                print(f'<span class="{name}">{escape(text)}</span>')
                append_html_contents(
                    cell.output, f'<span class="{name}">{escape(text)}</span>'
                )
                # if text.endswith("\n"):
                #     # the trailing \n in <pre> does not appear to have any
                #     # effect.
                #     append_plain_text(cell.output, "\n")
                cell.output.setVisible(True)
            cell.set_execution_count(content.get("execution_count", None))


class CellSourceEditor(QPlainTextEdit):
    def __init__(self, parent=None, **kwargs):
        self.kernel_client = kwargs.pop("kernel_client")  # type: QtKernelClient
        self._cell_output = []
        super().__init__(parent, **kwargs)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = PygmentsHighlighter(self.document())
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setWidget(self)
        self.completer.setModel(PyListModel(parent=self))
        self.completer.activated.connect(self._insert_completion)
        # self.document().documentLayoutChanged.connect(self.updateGeometry)
        self.document().documentLayout().documentSizeChanged.connect(self.updateGeometry)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        w = ceil(fm.width("X" * 80))
        margin = ceil(self.document().documentMargin())
        frame = self.frameWidth()
        w = w + 2 * margin + 2 * frame
        sh = super().sizeHint()
        sh.setWidth(max(sh.width(), w))
        linecount = self.document().blockCount()
        # (linecount + 1) to get rid scroll
        h = fm.lineSpacing() * (linecount + 1) + 2 * margin + 2 * frame
        sh.setHeight(h + 2)
        return sh

    def minimumSizeHint(self) -> QSize:
        fm = self.fontMetrics()
        w = ceil(fm.width("X" * 80))
        margin = ceil(self.document().documentMargin())
        frame = self.frameWidth()
        return QSize(w // 8, 2 * margin + 2 * frame + fm.lineSpacing())

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Tab:
            cur = self.textCursor()
            pos = cur.position()
            cur.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 1)
            source = self.source()
            if pos != cur.position() and source:
                char = source[cur.position()]
                if not re.match("\\s", char):
                    self.complete()
                    event.accept()
                    return
        super().keyPressEvent(event)
        if event.key() == Qt.Key_ParenLeft:
            self.inspect(self.textCursor().position())

    def complete(self):
        code = self.source()
        pos = self.textCursor().position()
        msg_id = self.kernel_client.complete(code=code, cursor_pos=pos)

        @on_reply(self.kernel_client, "complete_reply", msg_id)
        def _(msg):
            self._complete(msg)

    def _complete(self, msg):
        content = msg["content"]
        print(content)
        matches = content.get("matches", [])
        cursor_start = content.get("cursor_start", -1)
        cursor_end = content.get("cursor_end", -1)
        experimental = content.get("metadata", {}).get("_jupyter_types_experimental", [])

        print(matches)
        print(experimental)

        cursor = self.textCursor()
        pos = cursor.position()
        if pos != cursor_end:
            return
        completer = self.completer
        model = self.completer.model()
        model[:] = matches
        rect = self.cursorRect(cursor)
        popup = completer.popup()
        rect.setWidth(
            popup.sizeHintForColumn(0) +
            popup.verticalScrollBar().sizeHint().width()
        )
        completer.setCompletionPrefix(self.source()[cursor_start: cursor_end])
        completer.complete(rect)

    def _insert_completion(self, text):
        # print(text)
        tc = self.textCursor()
        extra = len(text) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.Left)
        tc.movePosition(QTextCursor.EndOfWord)
        tc.insertText(text[-extra:])
        self.completer.popup().hide()
        self.setTextCursor(tc)

    def inspect(self, pos: int):
        code = self.source()
        msg_id = self.kernel_client.inspect(code=code, cursor_pos=pos)

        @on_reply(self.kernel_client, "inspect_reply", msg_id)
        def handle_inspect(msg):
            self._handle_inspect_reply(msg, pos)

    def _handle_inspect_reply(self, msg, pos):
        # print(msg)
        content = msg.get("content", {})
        data = content.get("data", {})
        text = ""
        if content.get("status") == "ok":
            text = data.get("text/plain", "")
            text = remove_ansi_control(text)
        curpos = self.textCursor().position()
        if text and pos == curpos:
            point = self.mapToGlobal(self.cursorRect().bottomLeft())
            QToolTip.showText(point, text, self, QRect(), 1000)

    def source(self):
        return self.toPlainText()


class RichOutputView(QTextBrowser):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        doc = self.document()
        doc.documentLayout().documentSizeChanged.connect(self.updateGeometry)
        doc.setDefaultStyleSheet(
            ".stderr { color: red; white-space: pre-wrap; }\n"
            ".stdout { white-space: pre-wrap; }\n"
            "th { font-weight: bold; }\n"
        )

    def sizeHint(self) -> QSize:
        doc = self.document()
        size = doc.size()
        margin = self.document().documentMargin()
        frame = self.frameWidth()
        return QSize(size.width() + 2 * (margin + frame),
                     size.height() + 2 * (margin + frame))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class NotebookWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, **kwargs):
        kernel_manager = kwargs.pop("kernel_manager", None)
        super().__init__(parent, **kwargs)
        if kernel_manager is None:
            kernel_manager = QtKernelManager()
            kernel_manager.setParent(self)
            kernel_manager.start_kernel()

        self.kernel_client = kernel_manager.client()
        self.kernel_client.start_channels()

        scroll = QScrollArea(
            objectName="notebook-scroll-area",
            widgetResizable=True,
        )
        scroll.setFrameStyle(QScrollArea.NoFrame)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self.editor = NotebookEditor(kernel_client=self.kernel_client)
        self.editor.setStyleSheet(
            ".input-prompt-label { color: #080088; }\n"
            ".output-prompt-label { color: #980000; }\n"
        )
        scroll.setWidget(self.editor)
        self.setLayout(layout)

    def load(self, nb):
        with open(nb, "rb") as f:
            content = f.read()
        self.setSource(content, )

    def setSource(self, data: Union[str, bytes, bytearray]):
        data = json.loads(data)
        self.setNoteBookCells(data)

    def setNoteBookCells(self, data):
        format = data.get("nbformat", 0), data.get("nbformat_minor", 0)
        metadata = data.get("metadata", {})
        cells = data.get("cells", [])

        def normalize_source(source):
            if isinstance(source, list):
                source = "".join(source)
            return source

        for cell in map(lambda ns: Cell(**ns), cells):
            if cell.cell_type == "code":
                cell.source = normalize_source(cell.source)
                cell = CodeCell(**cell.__dict__)
                self.editor.append_cell(cell)
            elif cell.cell_type == "markdown":
                cell.source = normalize_source(cell.source)
                cell = MarkdownCell(**cell.__dict__)
                self.editor.append_cell(cell)
            elif cell.cell_type == "raw":
                cell.source = normalize_source(cell.source)
                cell = Cell(**cell.__dict__)
                self.editor.append_cell(cell)

    def closeEvent(self, event) -> None:
        self.kernel_client.shutdown()
        super().closeEvent(event)

    def close(self):
        super().close()


def main(argv=None):
    import sys
    from AnyQt.QtWidgets import QApplication

    app = QApplication(argv or sys.argv)
    argv = app.arguments()
    w = NotebookWidget()
    if len(argv) > 1:
        fname = argv[1]
        w.load(fname)
    else:
        w.setSource(
            br'''{"cells": [
                   {"cell_type": "code", "source": ["print('Hello')\n"]},
                   {"cell_type": "code", "source": ["1 + 1\n"]},
                   {"cell_type": "code", "source": ["%config InlineBackend.figure_format = 'svg'"]},
                   {"cell_type": "code", "source": ["%pylab inline"]},
                   {"cell_type": "code", "source": ["plot([0,1], [0,1])"]},
                   {"cell_type": "markdown", "source": [
                       "### Title\n", "\n", "* 1\n"
                    ]}
            ]}
            '''
        )
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
