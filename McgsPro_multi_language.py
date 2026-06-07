# -*- coding: utf-8 -*-
"""

多语言配置 - XML 导入/导出 编辑器（PySide6）

有梯子：
pip install PySide6
清华园：
pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
阿里源：
pip install PySide6 -i https://mirrors.aliyun.com/pypi/simple

"""

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction, QKeySequence, QColor, QBrush, QFont
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QToolBar, QAbstractItemView,
    QDockWidget, QGroupBox, QFormLayout, QSpinBox, QPlainTextEdit,
    QPushButton, QHBoxLayout, QLabel, QCheckBox,
    QInputDialog, QDialog, QLineEdit, QDialogButtonBox, QRadioButton,
    QButtonGroup, QGridLayout
)
from PySide6.QtGui import QUndoStack, QUndoCommand


@dataclass
class TextRow:
    text_id: int
    langs: Dict[str, str]


def parse_xml(path: str) -> Tuple[List[TextRow], List[str]]:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "root":
        raise ValueError(f"根节点不是 <root>，实际为 <{root.tag}>")

    rows: List[TextRow] = []
    lang_set = set()

    for node in root.findall("文本"):
        if "ID" not in node.attrib:
            continue
        try:
            tid = int(node.attrib["ID"])
        except Exception:
            continue

        langs: Dict[str, str] = {}
        for child in list(node):
            lang_set.add(child.tag)
            langs[child.tag] = (child.text or "")
        rows.append(TextRow(text_id=tid, langs=langs))

    langs_sorted = []
    if "中文" in lang_set:
        langs_sorted.append("中文")
    for t in sorted(lang_set):
        if t != "中文":
            langs_sorted.append(t)

    rows.sort(key=lambda r: r.text_id)
    return rows, langs_sorted


def export_xml(path: str, rows: List[TextRow], lang_cols: List[str]) -> None:
    root = ET.Element("root")
    rows_sorted = sorted(rows, key=lambda r: r.text_id)

    for r in rows_sorted:
        text_node = ET.SubElement(root, "文本", {"ID": str(r.text_id)})
        for lang in lang_cols:
            child = ET.SubElement(text_node, lang)
            child.text = r.langs.get(lang, "")

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ", level=0)
    except Exception:
        pass
    tree.write(path, encoding="utf-8", xml_declaration=True)


# -------------------- Undo Commands --------------------

class CellEditCommand(QUndoCommand):
    """仅用于语言列(col>=2)的单元格编辑撤销/重做"""
    def __init__(self, window: "MainWindow", row: int, col: int, old: str, new: str, desc: str = "编辑单元格"):
        super().__init__(desc)
        self.w = window
        self.row = row
        self.col = col
        self.old = old
        self.new = new

    def _apply(self, val: str):
        t = self.w.table
        it = t.item(self.row, self.col)
        if it is None:
            it = QTableWidgetItem("")
            t.setItem(self.row, self.col, it)

        self.w._building = True
        try:
            it.setText(val)
            it.setBackground(self.w.modified_brush)
            it.setData(Qt.UserRole, val)   # 旧值缓存同步
        finally:
            self.w._building = False

    def undo(self):
        self._apply(self.old)

    def redo(self):
        self._apply(self.new)


# -------------------- 中文查找/替换对话框 --------------------

class ChineseFindReplaceDialog(QDialog):
    """
    中文列(语言ID:0) 查找/替换
    - 查找下一个（定位）
    - 替换当前
    - 全部替换（全表/仅选中行）
    """
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.w = parent
        self.setWindowTitle("中文(语言ID:0) 查找/替换")
        self.resize(520, 220)

        grid = QGridLayout(self)

        grid.addWidget(QLabel("查找内容："), 0, 0)
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("输入要查找的中文（支持包含匹配）")
        grid.addWidget(self.ed_find, 0, 1, 1, 3)

        grid.addWidget(QLabel("替换为："), 1, 0)
        self.ed_replace = QLineEdit()
        self.ed_replace.setPlaceholderText("输入替换文本（可为空）")
        grid.addWidget(self.ed_replace, 1, 1, 1, 3)

        # 匹配模式
        self.rb_contains = QRadioButton("包含匹配（推荐）")
        self.rb_exact = QRadioButton("完全匹配")
        self.rb_contains.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_contains)
        grp.addButton(self.rb_exact)
        grid.addWidget(QLabel("匹配模式："), 2, 0)
        grid.addWidget(self.rb_contains, 2, 1)
        grid.addWidget(self.rb_exact, 2, 2)

        # 范围
        self.chk_only_selected = QCheckBox("仅在“选中行”内查找/替换")
        self.chk_only_selected.setChecked(False)
        grid.addWidget(self.chk_only_selected, 3, 1, 1, 3)

        # 按钮
        self.btn_find_next = QPushButton("查找下一个")
        self.btn_replace_one = QPushButton("替换当前")
        self.btn_replace_all = QPushButton("全部替换")

        self.btn_find_next.clicked.connect(self._on_find_next)
        self.btn_replace_one.clicked.connect(self._on_replace_one)
        self.btn_replace_all.clicked.connect(self._on_replace_all)

        # 右侧按钮排布
        grid.addWidget(self.btn_find_next, 4, 1)
        grid.addWidget(self.btn_replace_one, 4, 2)
        grid.addWidget(self.btn_replace_all, 4, 3)

        # 关闭
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 5, 0, 1, 4)

        # 小提示
        hint = QLabel("提示：定位到匹配单元格后，会自动滚动并选中该格。全部替换支持 Ctrl+Z 撤销。")
        hint.setWordWrap(True)
        grid.addWidget(hint, 6, 0, 1, 4)

    def _params(self):
        find = self.ed_find.text()
        rep = self.ed_replace.text()
        exact = self.rb_exact.isChecked()
        only_sel = self.chk_only_selected.isChecked()
        return find, rep, exact, only_sel

    def _on_find_next(self):
        find, _, exact, only_sel = self._params()
        if not find:
            QMessageBox.information(self, "提示", "请输入“查找内容”。")
            return
        ok = self.w.find_chinese_next(find, exact=exact, only_selected_rows=only_sel)
        if not ok:
            QMessageBox.information(self, "未找到", "未找到匹配项。")

    def _on_replace_one(self):
        find, rep, exact, only_sel = self._params()
        if not find:
            QMessageBox.information(self, "提示", "请输入“查找内容”。")
            return
        done = self.w.replace_chinese_current(find, rep, exact=exact, only_selected_rows=only_sel)
        if not done:
            QMessageBox.information(self, "提示", "当前位置不是匹配项（或不在限定范围内），请先“查找下一个”。")

    def _on_replace_all(self):
        find, rep, exact, only_sel = self._params()
        if not find:
            QMessageBox.information(self, "提示", "请输入“查找内容”。")
            return
        count = self.w.replace_chinese_all(find, rep, exact=exact, only_selected_rows=only_sel)
        QMessageBox.information(self, "完成", f"已替换 {count} 处。")


# -------------------- Main Window --------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多语言配置")
        self.resize(1120, 800)

        self.current_file: Optional[str] = None
        self.lang_cols: List[str] = ["中文"]
        self._building = False

        self.modified_brush = QBrush(QColor(255, 210, 210))

        # Undo Stack
        self.undo_stack = QUndoStack(self)

        # 中文查找/替换对话框缓存
        self._cn_dialog: Optional[ChineseFindReplaceDialog] = None

        # -------------------- 表格 --------------------
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["序号", "文本ID", "中文(语言ID:0)"])
        self.table.verticalHeader().setVisible(False)

        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setAlternatingRowColors(True)

        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 110)

        # 锁定模式点击自动选中
        self.table.cellClicked.connect(self.on_cell_clicked)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_menus_toolbar()
        self._build_batch_dock()

        self.table.itemChanged.connect(self._on_item_changed)

    # -------------------- Actions / Menus / Toolbar --------------------

    def _build_actions(self):
        self.act_open = QAction("打开(&O)...", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_file)

        self.act_save_as = QAction("另存为(&S)...", self)
        self.act_save_as.setShortcut(QKeySequence.SaveAs)
        self.act_save_as.triggered.connect(self.save_as)

        self.act_add = QAction("新增行", self)
        self.act_add.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_N))
        self.act_add.triggered.connect(self.add_row)

        self.act_delete = QAction("删除选中", self)
        self.act_delete.setShortcut(QKeySequence.Delete)
        self.act_delete.triggered.connect(self.delete_selected_rows)

        self.act_sort_by_id = QAction("按文本ID排序", self)
        self.act_sort_by_id.triggered.connect(self.sort_by_id)

        self.act_toggle_batch = QAction("批量修改面板", self)
        self.act_toggle_batch.setCheckable(True)
        self.act_toggle_batch.setChecked(True)
        self.act_toggle_batch.triggered.connect(self._toggle_batch_dock)

        # 文本ID 搜索：Ctrl+F
        self.act_find = QAction("查找文本ID(&F)...", self)
        self.act_find.setShortcut(QKeySequence.Find)  # Ctrl+F
        self.act_find.triggered.connect(self.find_text_id)

        # ✅ 中文查找：Ctrl+Shift+F
        self.act_find_cn = QAction("查找中文(&C)...", self)
        self.act_find_cn.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_find_cn.triggered.connect(self.find_chinese_dialog)

        # ✅ 中文替换：Ctrl+H
        self.act_replace_cn = QAction("替换中文(&H)...", self)
        self.act_replace_cn.setShortcut(QKeySequence("Ctrl+H"))
        self.act_replace_cn.triggered.connect(self.replace_chinese_dialog)

        # 撤销 / 重做
        self.act_undo = self.undo_stack.createUndoAction(self, "撤销(&Z)")
        self.act_undo.setShortcuts([QKeySequence.Undo])  # Ctrl+Z
        self.act_redo = self.undo_stack.createRedoAction(self, "重做(&Y)")
        self.act_redo.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Shift+Z")])

        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self.about)

        self.act_exit = QAction("退出", self)
        self.act_exit.setShortcut(QKeySequence.Quit)
        self.act_exit.triggered.connect(self.close)

    def _build_menus_toolbar(self):
        menubar = self.menuBar()
        m_file = menubar.addMenu("文件(&F)")
        m_file.addAction(self.act_open)
        m_file.addSeparator()
        m_file.addAction(self.act_save_as)
        m_file.addSeparator()
        m_file.addAction(self.act_exit)

        m_edit = menubar.addMenu("编辑(&E)")
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        m_edit.addSeparator()
        m_edit.addAction(self.act_find)
        m_edit.addAction(self.act_find_cn)
        m_edit.addAction(self.act_replace_cn)
        m_edit.addSeparator()
        m_edit.addAction(self.act_add)
        m_edit.addAction(self.act_delete)
        m_edit.addSeparator()
        m_edit.addAction(self.act_sort_by_id)
        m_edit.addSeparator()
        m_edit.addAction(self.act_toggle_batch)

        m_help = menubar.addMenu("帮助(&H)")
        m_help.addAction(self.act_about)

        tb = QToolBar("工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.act_open)
        tb.addAction(self.act_save_as)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_find)
        tb.addAction(self.act_find_cn)
        tb.addAction(self.act_replace_cn)
        tb.addSeparator()
        tb.addAction(self.act_add)
        tb.addAction(self.act_delete)
        tb.addSeparator()
        tb.addAction(self.act_sort_by_id)
        tb.addSeparator()
        tb.addAction(self.act_toggle_batch)

    # -------------------- Batch Dock --------------------

    def _build_batch_dock(self):
        self.batch_dock = QDockWidget("批量修改(纵向)", self)
        self.batch_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        root = QWidget()
        v = QVBoxLayout(root)

        tip = QLabel(
            "使用法：\n"
            "【锁定=开】点击一格自动向下选中 X 行 -> 点应用\n"
            "【锁定=关】请手动选中同列连续 X 行单元格 -> 点应用\n"
            "存储池每行一条，应用会消耗前 X 行。"
        )
        tip.setWordWrap(True)
        v.addWidget(tip)

        box = QGroupBox("纵向批量粘贴")
        form = QFormLayout(box)

        self.spin_x = QSpinBox()
        self.spin_x.setRange(1, 99999)
        self.spin_x.setValue(32)
        form.addRow("X 行数：", self.spin_x)

        self.chk_lock = QCheckBox("行数锁定：开启")
        self.chk_lock.setChecked(True)
        self.chk_lock.stateChanged.connect(self._on_lock_changed)
        form.addRow("选中策略：", self.chk_lock)

        self.pool_count_label = QLabel("存储池行数：0")
        form.addRow("状态：", self.pool_count_label)

        self.pool_edit = QPlainTextEdit()
        self.pool_edit.setPlaceholderText("在这里粘贴多行内容（每行一条）...")
        self.pool_edit.setMinimumHeight(260)
        self.pool_edit.textChanged.connect(self._update_pool_count_label)
        form.addRow("存储池：", self.pool_edit)

        btn_row = QWidget()
        h = QHBoxLayout(btn_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        self.btn_apply = QPushButton("应用（取前X行）")
        self.btn_apply.clicked.connect(self.apply_vertical_batch)
        self.btn_apply.setMinimumHeight(56)
        self.btn_apply.setMinimumWidth(240)
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        self.btn_apply.setFont(f)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
            QPushButton:disabled { background-color: #90A4AE; color: #ECEFF1; }
        """)

        self.btn_clear_pool = QPushButton("清空存储池")
        self.btn_clear_pool.clicked.connect(self._clear_pool)
        self.btn_clear_pool.setMinimumHeight(42)
        self.btn_clear_pool.setStyleSheet("""
            QPushButton {
                background-color: #EEEEEE;
                color: #333333;
                border: 1px solid #CCCCCC;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QPushButton:hover { background-color: #E0E0E0; }
            QPushButton:pressed { background-color: #D6D6D6; }
        """)

        h.addWidget(self.btn_apply, 1)
        h.addWidget(self.btn_clear_pool)
        form.addRow("", btn_row)

        v.addWidget(box)
        v.addStretch(1)

        self.batch_dock.setWidget(root)
        self.addDockWidget(Qt.RightDockWidgetArea, self.batch_dock)

    def _toggle_batch_dock(self):
        self.batch_dock.setVisible(self.act_toggle_batch.isChecked())

    def _clear_pool(self):
        self.pool_edit.setPlainText("")
        self._update_pool_count_label()

    def _update_pool_count_label(self):
        self.pool_count_label.setText(f"存储池行数：{len(self._pool_lines())}")

    # -------------------- 文本ID 查找(Ctrl+F) --------------------

    def find_text_id(self):
        text, ok = QInputDialog.getText(self, "查找文本ID", "输入要查找的文本ID（支持包含匹配）：")
        if not ok:
            return
        key = text.strip()
        if not key:
            return

        n = self.table.rowCount()
        if n <= 0:
            QMessageBox.information(self, "提示", "表格为空。")
            return

        start = self.table.currentRow()
        if start < 0:
            start = -1

        def get_id(r: int) -> str:
            it = self.table.item(r, 1)
            return (it.text() if it else "")

        is_digit = key.isdigit()
        idx = self._find_in_range(key, start + 1, n - 1, is_digit, get_id)
        if idx is None:
            idx = self._find_in_range(key, 0, start, is_digit, get_id)

        if idx is None:
            QMessageBox.information(self, "未找到", f"未找到文本ID匹配：{key}")
            return

        self.table.setCurrentCell(idx, 1)
        self.table.scrollToItem(self.table.item(idx, 1), QAbstractItemView.PositionAtCenter)
        self.table.clearSelection()
        self.table.item(idx, 1).setSelected(True)

    def _find_in_range(self, key: str, a: int, b: int, is_digit: bool, getter) -> Optional[int]:
        if a > b:
            return None
        if is_digit:
            for r in range(a, b + 1):
                if getter(r).strip() == key:
                    return r
        for r in range(a, b + 1):
            if key in getter(r):
                return r
        return None

    # -------------------- 中文 查找/替换 Dialog --------------------

    def find_chinese_dialog(self):
        # Ctrl+Shift+F：直接打开对话框并聚焦查找框
        if self._cn_dialog is None:
            self._cn_dialog = ChineseFindReplaceDialog(self)
        self._cn_dialog.show()
        self._cn_dialog.raise_()
        self._cn_dialog.activateWindow()
        self._cn_dialog.ed_find.setFocus()

    def replace_chinese_dialog(self):
        # Ctrl+H：打开同一个对话框并聚焦替换框
        if self._cn_dialog is None:
            self._cn_dialog = ChineseFindReplaceDialog(self)
        self._cn_dialog.show()
        self._cn_dialog.raise_()
        self._cn_dialog.activateWindow()
        self._cn_dialog.ed_replace.setFocus()

    # -------------------- 中文 查找/替换 核心实现 --------------------

    def _iter_target_rows(self, only_selected_rows: bool) -> List[int]:
        if not only_selected_rows:
            return list(range(self.table.rowCount()))
        sel = self.table.selectedIndexes()
        if not sel:
            return []
        return sorted({i.row() for i in sel})

    def _cn_col(self) -> int:
        # 中文列固定为第3列（索引2）
        return 2

    def _match(self, text: str, key: str, exact: bool) -> bool:
        if exact:
            return text == key
        return key in text

    def find_chinese_next(self, key: str, exact: bool = False, only_selected_rows: bool = False) -> bool:
        """
        在中文列查找下一个匹配并定位（循环查找）
        """
        col = self._cn_col()
        rows = self._iter_target_rows(only_selected_rows)
        if only_selected_rows and not rows:
            return False
        if not rows:
            rows = list(range(self.table.rowCount()))
        if not rows:
            return False

        # 当前起点（按当前行之后开始）
        cur = self.table.currentRow()
        if cur < 0:
            cur = rows[0] - 1

        # 构造查找顺序：先从“当前行之后”到尾，再从头到当前
        ordered: List[int] = [r for r in rows if r > cur] + [r for r in rows if r <= cur]

        for r in ordered:
            it = self.table.item(r, col)
            txt = (it.text() if it else "")
            if self._match(txt, key, exact):
                self.table.setCurrentCell(r, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(r, col, it)
                    it.setData(Qt.UserRole, "")
                self.table.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                self.table.clearSelection()
                it.setSelected(True)
                return True

        return False

    def replace_chinese_current(self, key: str, rep: str, exact: bool = False, only_selected_rows: bool = False) -> bool:
        """
        替换当前单元格（必须当前在中文列且匹配，且若仅选中行则当前行必须在选中行内）
        """
        col = self._cn_col()
        r = self.table.currentRow()
        c = self.table.currentColumn()
        if r < 0 or c != col:
            return False

        if only_selected_rows:
            rows = self._iter_target_rows(True)
            if r not in rows:
                return False

        it = self.table.item(r, col)
        txt = (it.text() if it else "")
        if not self._match(txt, key, exact):
            return False

        # 替换策略：包含匹配 -> replace；完全匹配 -> 整格替换成 rep
        if exact:
            new_txt = rep
        else:
            new_txt = txt.replace(key, rep)

        if it is None:
            it = QTableWidgetItem("")
            self.table.setItem(r, col, it)
            it.setData(Qt.UserRole, "")

        old = (it.data(Qt.UserRole) or it.text() or "")
        if new_txt == old:
            return True

        self.undo_stack.push(CellEditCommand(self, r, col, old, new_txt, "中文替换(当前)"))
        return True

    def replace_chinese_all(self, key: str, rep: str, exact: bool = False, only_selected_rows: bool = False) -> int:
        """
        全部替换：全表或仅选中行
        返回替换次数（按“替换的单元格数”计数）
        """
        col = self._cn_col()
        rows = self._iter_target_rows(only_selected_rows)
        if only_selected_rows and not rows:
            return 0
        if not rows:
            rows = list(range(self.table.rowCount()))

        changed = 0
        self.undo_stack.beginMacro("中文全部替换")
        try:
            for r in rows:
                it = self.table.item(r, col)
                txt = (it.text() if it else "")
                if not self._match(txt, key, exact):
                    continue

                if exact:
                    new_txt = rep
                else:
                    new_txt = txt.replace(key, rep)

                # 如果包含匹配但 replace 后内容没变化（例如 key==""）也跳过
                if new_txt == txt:
                    # 但如果 exact 模式且 txt==key，new_txt 可能等于 txt（rep==key），这也算无需替换
                    continue

                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(r, col, it)
                    it.setData(Qt.UserRole, "")

                old = (it.data(Qt.UserRole) or it.text() or "")
                if new_txt != old:
                    self.undo_stack.push(CellEditCommand(self, r, col, old, new_txt, "中文批量替换"))
                    changed += 1
        finally:
            self.undo_stack.endMacro()

        return changed

    # -------------------- Lock behavior --------------------

    def _on_lock_changed(self):
        if self.chk_lock.isChecked():
            r = self.table.currentRow()
            c = self.table.currentColumn()
            if r >= 0 and c >= 2:
                self._select_down_block(r, c, self.spin_x.value())

    def on_cell_clicked(self, row: int, col: int):
        if self.chk_lock.isChecked() and col >= 2:
            self._select_down_block(row, col, self.spin_x.value())

    def _select_down_block(self, start_row: int, col: int, X: int):
        if self.table.rowCount() <= 0:
            return
        end_row = min(self.table.rowCount() - 1, start_row + int(X) - 1)

        self._building = True
        try:
            self.table.clearSelection()
            for rr in range(start_row, end_row + 1):
                it = self.table.item(rr, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(rr, col, it)
                    it.setData(Qt.UserRole, "")
                it.setSelected(True)
            self.table.setCurrentCell(start_row, col)
        finally:
            self._building = False

    # -------------------- Apply vertical batch --------------------

    def apply_vertical_batch(self):
        X = int(self.spin_x.value())
        pool_lines = self._pool_lines()

        if len(pool_lines) < X:
            QMessageBox.warning(self, "提示", f"存储池行数不足：需要 {X} 行，但当前只有 {len(pool_lines)} 行。")
            return

        if self.chk_lock.isChecked():
            self._apply_locked_mode(X, pool_lines)
        else:
            self._apply_unlocked_mode(X, pool_lines)

    def _apply_locked_mode(self, X: int, pool_lines: List[str]):
        col = self.table.currentColumn()
        row0 = self.table.currentRow()

        if row0 < 0 or col < 0:
            QMessageBox.warning(self, "提示", "请先点击要修改的单元格。")
            return
        if col < 2:
            QMessageBox.warning(self, "提示", "批量修改仅用于语言内容列（从第3列开始）。")
            return

        self._select_down_block(row0, col, X)

        end_row = min(self.table.rowCount() - 1, row0 + X - 1)
        target_rows = list(range(row0, end_row + 1))
        if len(target_rows) < X:
            QMessageBox.warning(self, "提示", f"从当前行向下不足 {X} 行（到表尾了）。")
            return

        self.undo_stack.beginMacro(f"批量应用 {X} 行")
        try:
            for i, rr in enumerate(target_rows):
                it = self.table.item(rr, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(rr, col, it)
                    it.setData(Qt.UserRole, "")
                old = (it.data(Qt.UserRole) or it.text() or "")
                new = pool_lines[i]
                if new != old:
                    self.undo_stack.push(CellEditCommand(self, rr, col, old, new, "批量编辑"))
        finally:
            self.undo_stack.endMacro()

        self._consume_pool(X)

        next_start = row0 + X
        if next_start < self.table.rowCount():
            self.table.setCurrentCell(next_start, col)
            self._select_down_block(next_start, col, X)

    def _apply_unlocked_mode(self, X: int, pool_lines: List[str]):
        selected = self.table.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "提示", "请在表格中纵向选择要修改的 X 个单元格。")
            return

        cols = {idx.column() for idx in selected}
        if len(cols) != 1:
            QMessageBox.warning(self, "提示", "纵向批量修改要求：选中的单元格必须在同一列。")
            return
        col = next(iter(cols))
        if col in (0, 1):
            QMessageBox.warning(self, "提示", "批量修改仅用于语言内容列（从第3列开始）。")
            return

        rows = sorted({idx.row() for idx in selected})
        if len(rows) < X:
            QMessageBox.warning(self, "提示", f"选中行数不足：需要选择 {X} 行，但当前只选中了 {len(rows)} 行。")
            return

        target_rows = rows[:X]
        if any(target_rows[i] + 1 != target_rows[i + 1] for i in range(len(target_rows) - 1)):
            QMessageBox.warning(self, "提示", "请选中连续的 X 行（从上到下连续）。")
            return

        self.undo_stack.beginMacro(f"批量应用 {X} 行")
        try:
            for i, rr in enumerate(target_rows):
                it = self.table.item(rr, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(rr, col, it)
                    it.setData(Qt.UserRole, "")
                old = (it.data(Qt.UserRole) or it.text() or "")
                new = pool_lines[i]
                if new != old:
                    self.undo_stack.push(CellEditCommand(self, rr, col, old, new, "批量编辑"))
        finally:
            self.undo_stack.endMacro()

        self._consume_pool(X)

        next_start = target_rows[-1] + 1
        if next_start < self.table.rowCount():
            self.table.clearSelection()
            end = min(self.table.rowCount() - 1, next_start + X - 1)
            for rr in range(next_start, end + 1):
                it = self.table.item(rr, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table.setItem(rr, col, it)
                    it.setData(Qt.UserRole, "")
                it.setSelected(True)
            self.table.setCurrentCell(next_start, col)

    def _consume_pool(self, X: int):
        pool_lines = self._pool_lines()
        remain = pool_lines[X:]
        self.pool_edit.setPlainText("\n".join(remain))
        self._update_pool_count_label()

    def _pool_lines(self) -> List[str]:
        raw = self.pool_edit.toPlainText().splitlines()
        while raw and raw[-1].strip() == "":
            raw.pop()
        return raw

    # -------------------- Table data helpers --------------------

    def load_rows(self, rows: List[TextRow], lang_cols: List[str]):
        self._building = True
        try:
            self.undo_stack.clear()

            self.lang_cols = lang_cols[:] if lang_cols else ["中文"]
            headers = ["序号", "文本ID"]
            for lang in self.lang_cols:
                headers.append("中文(语言ID:0)" if lang == "中文" else lang)

            self.table.clear()
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setRowCount(0)

            for r in rows:
                self._append_row(r.text_id, {k: r.langs.get(k, "") for k in self.lang_cols})

            self._refresh_serials()
        finally:
            self._building = False

    def dump_rows(self) -> List[TextRow]:
        rows: List[TextRow] = []
        for i in range(self.table.rowCount()):
            tid_item = self.table.item(i, 1)
            if not tid_item:
                continue
            tid_str = tid_item.text().strip()
            if not tid_str:
                continue
            try:
                tid = int(tid_str)
            except Exception:
                continue

            langs: Dict[str, str] = {}
            for j, lang in enumerate(self.lang_cols, start=2):
                it = self.table.item(i, j)
                langs[lang] = (it.text() if it else "")
            rows.append(TextRow(text_id=tid, langs=langs))
        return rows

    def _append_row(self, text_id: int, langs: Dict[str, str]):
        r = self.table.rowCount()
        self.table.insertRow(r)

        serial = QTableWidgetItem(str(r + 1))
        serial.setFlags(serial.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 0, serial)

        tid_item = QTableWidgetItem(str(text_id))
        self.table.setItem(r, 1, tid_item)

        for idx, lang in enumerate(self.lang_cols, start=2):
            it = QTableWidgetItem(langs.get(lang, ""))
            it.setData(Qt.UserRole, it.text())
            self.table.setItem(r, idx, it)

    def _refresh_serials(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setText(str(r + 1))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._building:
            return

        # 文本ID列不进撤销
        if item.column() == 1:
            s = item.text().strip()
            try:
                int(s)
            except Exception:
                QMessageBox.warning(self, "提示", "文本ID 必须是整数。")
                self._building = True
                item.setText("0")
                self._building = False
            return

        # 语言列：手工编辑入撤销栈
        if item.column() >= 2:
            old = item.data(Qt.UserRole)
            if old is None:
                old = ""
            new = item.text()
            if new == old:
                return
            self.undo_stack.push(CellEditCommand(self, item.row(), item.column(), str(old), new, "手工编辑"))

    # -------------------- File ops --------------------

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开XML", "", "XML Files (*.xml);;All Files (*.*)")
        if not path:
            return
        try:
            rows, lang_cols = parse_xml(path)
            self.load_rows(rows, lang_cols)
            self.current_file = path
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出XML", self.current_file or "多语言配置.xml", "XML Files (*.xml)"
        )
        if not path:
            return
        try:
            rows = self.dump_rows()
            export_xml(path, rows, self.lang_cols)
            self.current_file = path
            QMessageBox.information(self, "成功", "导出完成。")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # -------------------- Edit ops --------------------

    def add_row(self):
        used = set()
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            if it:
                try:
                    used.add(int(it.text().strip()))
                except Exception:
                    pass
        new_id = (max(used) + 1) if used else 0

        self._building = True
        try:
            self._append_row(new_id, {lang: "" for lang in self.lang_cols})
            self._refresh_serials()
        finally:
            self._building = False

        self.table.setCurrentCell(self.table.rowCount() - 1, 2)
        if self.chk_lock.isChecked():
            self._select_down_block(self.table.currentRow(), self.table.currentColumn(), self.spin_x.value())

    def delete_selected_rows(self):
        selected = self.table.selectedIndexes()
        if not selected:
            return
        rows = sorted({idx.row() for idx in selected}, reverse=True)

        self._building = True
        try:
            for r in rows:
                self.table.removeRow(r)
            self._refresh_serials()
        finally:
            self._building = False

    def sort_by_id(self):
        rows = self.dump_rows()
        rows.sort(key=lambda r: r.text_id)
        self.load_rows(rows, self.lang_cols)

    def about(self):
        QMessageBox.information(
            self, "关于",
            "多语言配置编辑器（PySide6）\n"
            "支持：文本ID查找(Ctrl+F)，中文查找(Ctrl+Shift+F)，中文替换(Ctrl+H)，撤销/重做(Ctrl+Z/Ctrl+Y)。"
        )


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
