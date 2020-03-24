from AnyQt.QtTest import QSignalSpy

from orangecontrib.prototypes.widgets.utils.asyncutils import get_event_loop
from orangewidget.tests.base import WidgetTest, GuiTest

from orangecontrib.prototypes.widgets.owipythonproc import OWIPythonConsole, \
    collect_execute_output
from orangewidget.utils.concurrent import FutureWatcher


class TestOWIPythonProc(WidgetTest):
    def setUp(self):
        super().setUp()
        self.widget = self.create_widget(
            OWIPythonConsole, stored_settings={
                "content": "out_object = in_object"
            }
        )

    def tearDown(self):
        self.widget.onDeleteWidget()
        self.widget.deleteLater()
        self.widget = None
        super().tearDown()

    def test_simple(self):
        w = self.widget
        self.send_signal(w.Inputs.object_, "a", widget=w)
        out = self.get_output(w.Outputs.object_, widget=w)
        self.assertEqual(out, "a")

        self.send_signal(w.Inputs.object_, 42, widget=w)
        out = self.get_output(w.Outputs.object_, widget=w)
        self.assertEqual(out, 42)

        w.set_source("out_object = in_object + 1")
        self.send_signal(w.Inputs.object_, 42, widget=w)
        out = self.get_output(w.Outputs.object_, widget=w)
        self.assertEqual(out, 43)


class TestOther(GuiTest):
    def setUp(self) -> None:
        from qtconsole.manager import QtKernelManager
        self.kernel_manager = QtKernelManager()
        self.kernel_manager.start_kernel()
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()

    def tearDown(self) -> None:
        self.kernel_client.shutdown(restart=False)

    def test_collect_execute_output(self):
        msg_id = self.kernel_client.execute(
            "print('a');\n"
            "1"
        )
        f = collect_execute_output(self.kernel_client, msg_id)
        w = FutureWatcher(f, )
        spy = QSignalSpy(w.finished)
        assert spy.wait()
        res = f.result()
        assert res["execute_reply"]["content"]["status"] == "ok"

        msg_id = self.kernel_client.execute("1/0")
        f = collect_execute_output(self.kernel_client, msg_id)
        w = FutureWatcher(f, )
        spy = QSignalSpy(w.finished)
        assert spy.wait()
        res = f.result()
        assert res["execute_reply"]["content"]["status"] == "error"
