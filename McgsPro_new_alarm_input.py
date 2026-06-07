import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QInputDialog, QTextEdit, QDialog, QLabel,
    QComboBox, QSpinBox, QFormLayout, QDialogButtonBox
)
import xml.etree.ElementTree as ET
import copy
import re


HEADERS = [
    "序号", "变量名称", "变量类型", "报警类型", "可用性",
    "基准值", "触发误差", "解除误差", "报警分组", "报警级别", "报警描述"
]

TYPE_MAP = {
    "DI": "开入量",
    "DO": "开出量",
    "SOE": "SOE量"
}
PREFIX_TO_TYPE = {v: k for k, v in TYPE_MAP.items()}  # "开入量" -> "DI"


class PasteDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("批量粘贴")
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("一行一个点名 / 描述："))

        self.text = QTextEdit()
        layout.addWidget(self.text)

        btn = QPushButton("确认导入")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def get_lines(self):
        return [l.strip() for l in self.text.toPlainText().splitlines() if l.strip()]


class TypeWidthDialog(QDialog):
    """
    你截图里“选择类型”的升级版：
    - 选择类型：DI/DO/SOE
    - 该类型编号位数（独立）
    """
    def __init__(self, parent=None, width_map=None, title="选择类型"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 160)

        self.width_map = width_map or {"DI": 4, "DO": 4, "SOE": 4}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.combo = QComboBox()
        self.combo.addItems(list(TYPE_MAP.keys()))
        form.addRow("请选择变量类型：", self.combo)

        self.spin = QSpinBox()
        self.spin.setRange(1, 8)
        form.addRow("编号位数(该类型独立)：", self.spin)

        self.hint = QLabel("例：3 位 → 182；4 位 → 0182")
        self.hint.setStyleSheet("color: #666;")
        layout.addWidget(self.hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # 初始化：按当前类型的独立位数显示
        self.combo.currentTextChanged.connect(self._sync_spin_from_type)
        self._sync_spin_from_type(self.combo.currentText())

        # 当用户改位数时，立即写回该类型的独立配置
        self.spin.valueChanged.connect(self._write_back_width)

    def _sync_spin_from_type(self, t: str):
        w = int(self.width_map.get(t, 4))
        self.spin.blockSignals(True)
        self.spin.setValue(w)
        self.spin.blockSignals(False)

    def _write_back_width(self, v: int):
        t = self.combo.currentText()
        self.width_map[t] = int(v)

    def get_result(self):
        return self.combo.currentText(), int(self.spin.value())


class AlarmEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("报警统一配置")
        self.resize(1200, 600)

        # 各类型独立计数器
        self.type_counter = {"DI": 0, "DO": 0, "SOE": 0}

        # 各类型独立位数（关键：独立！）
        self.width_map = {"DI": 4, "DO": 4, "SOE": 4}

        # 撤销栈
        self.undo_stack = []

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()

        btn_add = QPushButton("添加一行(DI)")
        btn_batch = QPushButton("批量导入（DI / DO / SOE）")
        btn_import_xml = QPushButton("导入 XML")
        btn_undo = QPushButton("撤销")
        btn_clear = QPushButton("清空")
        btn_export = QPushButton("导出 XML")

        btn_add.clicked.connect(lambda: self.add_row(desc="", io_type="DI"))
        btn_batch.clicked.connect(self.batch_import)
        btn_import_xml.clicked.connect(self.import_xml)
        btn_undo.clicked.connect(self.undo)
        btn_clear.clicked.connect(self.clear_all)
        btn_export.clicked.connect(self.export_xml)

        for b in [btn_add, btn_batch, btn_import_xml, btn_undo, btn_clear, btn_export]:
            btn_layout.addWidget(b)

        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

    # ---------- 变量名位数（独立） ----------
    def _make_var_name(self, io_type: str, num: int) -> str:
        prefix = TYPE_MAP[io_type]
        w = int(self.width_map.get(io_type, 4))
        # zfill(w) 控制补零位数，w=3 -> 001 / 182(>=3 不补)
        return f"{prefix}{str(num).zfill(w)}"

    def _parse_prefix_and_num(self, var_name: str):
        """
        识别变量名称是否为：开入量xxxx / 开出量xxxx / SOE量xxxx
        返回 (io_type, num) 或 (None, None)
        """
        var_name = (var_name or "").strip()
        for prefix, io_type in PREFIX_TO_TYPE.items():
            if var_name.startswith(prefix):
                tail = var_name[len(prefix):]
                m = re.search(r"(\d+)$", tail)
                if m:
                    return io_type, int(m.group(1))
        return None, None

    def _renumber_seq_col(self):
        for r in range(self.table.rowCount()):
            self.table.setItem(r, 0, QTableWidgetItem(str(r + 1)))

    # ---------- 状态管理（撤销需要把 width_map 一起保存） ----------
    def save_state(self):
        state = {
            "table": [
                [self.table.item(r, c).text() if self.table.item(r, c) else ""
                 for c in range(self.table.columnCount())]
                for r in range(self.table.rowCount())
            ],
            "counter": copy.deepcopy(self.type_counter),
            "width_map": copy.deepcopy(self.width_map),
        }
        self.undo_stack.append(state)

    def restore_state(self, state):
        self.table.setRowCount(0)
        for row in state["table"]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val))

        self.type_counter = copy.deepcopy(state["counter"])
        self.width_map = copy.deepcopy(state.get("width_map", {"DI": 4, "DO": 4, "SOE": 4}))

    def undo(self):
        if not self.undo_stack:
            QMessageBox.information(self, "提示", "没有可撤销的操作")
            return
        state = self.undo_stack.pop()
        self.restore_state(state)

    # ---------- 功能：新增 ----------
    def add_row(self, desc="", io_type="DI"):
        self.save_state()

        self.type_counter[io_type] += 1
        var_name = self._make_var_name(io_type, self.type_counter[io_type])

        row = self.table.rowCount()
        self.table.insertRow(row)

        defaults = [
            str(row + 1),
            var_name,
            "整数",
            "开关量",
            "1",
            "1",
            "-",
            "-",
            "0",
            "0",
            desc
        ]
        for col, val in enumerate(defaults):
            self.table.setItem(row, col, QTableWidgetItem(val))

    # ---------- 功能：批量导入 ----------
    def batch_import(self):
        # 这里也用同一个“选择类型+位数”的对话框（位数独立）
        dlg_type = TypeWidthDialog(self, self.width_map, title="选择类型")
        if dlg_type.exec() != QDialog.Accepted:
            return
        io_type, _w = dlg_type.get_result()  # _w 已经写入 width_map[io_type]

        dlg = PasteDialog()
        if dlg.exec() != QDialog.Accepted:
            return

        self.save_state()
        for line in dlg.get_lines():
            self.type_counter[io_type] += 1
            var_name = self._make_var_name(io_type, self.type_counter[io_type])

            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                str(row + 1),
                var_name,
                "整数",
                "开关量",
                "1",
                "1",
                "-",
                "-",
                "0",
                "0",
                line
            ]
            for c, v in enumerate(values):
                self.table.setItem(row, c, QTableWidgetItem(v))

    # ---------- 功能：清空 ----------
    def clear_all(self):
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有数据吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.save_state()
        self.table.setRowCount(0)
        self.type_counter = {"DI": 0, "DO": 0, "SOE": 0}

    # ---------- XML：导出 ----------
    def export_xml(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 XML", "alarm.xml", "XML Files (*.xml)"
        )
        if not path:
            return

        root = ET.Element("root", attrib={
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
        })

        for r in range(self.table.rowCount()):
            item = ET.SubElement(root, "报警项", ID=str(r + 1))

            def text(c):
                it = self.table.item(r, c)
                return it.text() if it else ""

            mapping = {
                "变量名称": 1,
                "变量类型": 2,
                "报警类型": 3,
                "可用性": 4,
                "基准值": 5,
                "触发误差": 6,
                "解除误差": 7,
                "报警分组": 8,
                "报警级别": 9,
                "多语言ID": None,
                "多语言类型名称": None,
                "报警描述": 10
            }

            for k, c in mapping.items():
                e = ET.SubElement(item, k)
                if k == "多语言ID":
                    e.text = "-1"
                elif k == "多语言类型名称":
                    e.text = "中文"
                else:
                    e.text = text(c)

        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        QMessageBox.information(self, "成功", "XML 导出完成！")

    # ---------- XML：导入（重点：位数独立选择） ----------
    def import_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 XML", "", "XML Files (*.xml)"
        )
        if not path:
            return

        # 在你截图“选择类型”弹窗里，选择要设置哪一类的位数（独立）
        dlg_type = TypeWidthDialog(self, self.width_map, title="选择类型")
        if dlg_type.exec() != QDialog.Accepted:
            return
        _io_type, _w = dlg_type.get_result()
        # 注意：这里的选择是“独立写入 width_map[_io_type]”，不会影响其他类型

        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"XML 解析失败：\n{e}")
            return

        items = root.findall(".//报警项")
        if not items:
            QMessageBox.information(self, "提示", "未找到 <报警项> 节点，确认 XML 格式是否正确。")
            return

        self.save_state()

        self.table.setRowCount(0)
        max_seen = {"DI": 0, "DO": 0, "SOE": 0}

        for idx, node in enumerate(items, start=1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            def get_tag(tag: str, default: str = "") -> str:
                n = node.find(tag)
                return n.text.strip() if (n is not None and n.text is not None) else default

            var_name_raw = get_tag("变量名称", "")
            var_type = get_tag("变量类型", "整数")
            alarm_type = get_tag("报警类型", "开关量")
            avail = get_tag("可用性", "1")
            base = get_tag("基准值", "1")
            trig = get_tag("触发误差", "-")
            rel = get_tag("解除误差", "-")
            group = get_tag("报警分组", "0")
            level = get_tag("报警级别", "0")
            desc = get_tag("报警描述", "")

            # 变量名称：识别 DI/DO/SOE，按“各自独立位数”格式化
            io_type, num = self._parse_prefix_and_num(var_name_raw)
            if io_type and num is not None:
                var_name = self._make_var_name(io_type, num)  # 这里使用 width_map[io_type]（独立）
                if num > max_seen[io_type]:
                    max_seen[io_type] = num
            else:
                var_name = var_name_raw

            values = [
                str(idx),
                var_name,
                var_type,
                alarm_type,
                avail,
                base,
                trig,
                rel,
                group,
                level,
                desc
            ]
            for c, v in enumerate(values):
                self.table.setItem(row, c, QTableWidgetItem(v))

        self.type_counter = max_seen
        self._renumber_seq_col()

        QMessageBox.information(
            self, "导入完成",
            f"导入 {len(items)} 行。\n"
            f"独立位数：DI={self.width_map['DI']}  DO={self.width_map['DO']}  SOE={self.width_map['SOE']}\n"
            f"计数器：DI={self.type_counter['DI']}  DO={self.type_counter['DO']}  SOE={self.type_counter['SOE']}"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AlarmEditor()
    w.show()
    sys.exit(app.exec())
