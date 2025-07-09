import sys
import re
import subprocess
from PyQt5.QtWidgets import (
   QApplication, QMainWindow, QAction, QFileDialog, QTextEdit, QMessageBox, QLabel, QListWidget, QSplitter, QGraphicsView, QGraphicsScene
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
#from PyQt5.QtSvg import QGraphicsSvgItem
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPixmap
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QDialog, QVBoxLayout
import os, glob, tempfile, difflib

def parse_cfg_to_dot(cfg_text):
    dot_lines = ["digraph CFG {", "node [shape=box, fontname=\"Courier\"];"]

    blocks = {}
    current_block = None
    block_lines = []
    successors_map = {}
    block_order = []

    lines = cfg_text.splitlines()

    for line in lines:
        line = line.strip()

        if re.match(r'^<bb \d+>', line):
            if current_block is not None:
                blocks[current_block] = "\n".join(block_lines).strip()
                block_lines = []
            current_block = re.findall(r'<bb (\d+)>', line)[0]
            block_order.append(current_block)

        elif line.startswith(";;"):
            succ_match = re.match(r';;\s*([0-9]+)\s+succs\s+\{(.+?)\}', line)
            if succ_match:
                block_id = succ_match.group(1)
                succs = re.findall(r'\d+', succ_match.group(2))
                successors_map[block_id] = succs

        elif current_block is not None:
            block_lines.append(line)

    # Final block
    if current_block and block_lines:
        blocks[current_block] = "\n".join(block_lines).strip()

    # Add labeled nodes
    for block_id, content in blocks.items():
        label = content.replace("\"", "\\\"")
        dot_lines.append(f'"{block_id}" [label="{block_id}:\\n{label}"];')

    # Add edges with labels
    for src, targets in successors_map.items():
        block_text = blocks.get(src, "")
        label_candidates = []

        if "if" in block_text:
            # Likely a conditional
            if len(targets) == 2:
                label_candidates = ["True", "False"]
        elif "goto" in block_text:
            # Probably unconditional or loop
            if len(targets) == 1:
                if int(targets[0]) < int(src):
                    label_candidates = ["Loop"]
                else:
                    label_candidates = ["Jump"]

        for i, tgt in enumerate(targets):
            label = ""
            if i < len(label_candidates):
                label = label_candidates[i]
            dot_lines.append(f'"{src}" -> "{tgt}" [label="{label}"];')

    dot_lines.append("}")
    return "\n".join(dot_lines)

def extract_cfgs_per_function(cfg_text):
    functions = {}
    current_func = None
    current_lines = []

    for line in cfg_text.splitlines():
        if line.startswith(";; Function "):
            if current_func and current_lines:
                functions[current_func] = "\n".join(current_lines)
            current_func = re.findall(r";; Function (\w+)", line)[0]
            current_lines = []
        elif current_func is not None:
            current_lines.append(line)

    if current_func and current_lines:
        functions[current_func] = "\n".join(current_lines)

    return functions

from PyQt5.QtWidgets import QTabWidget

class TabbedCFGWindow(QDialog):
    def __init__(self, per_func_cfgs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Function-wise Control Flow Graphs")
        self.resize(1000, 800)

        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        for func_name, cfg_text in per_func_cfgs.items():
            dot = parse_cfg_to_dot(cfg_text)
            tab = self.create_webview_tab(dot)
            self.tabs.addTab(tab, func_name)

    def create_webview_tab(self, dot_source):
        view = QWebEngineView()
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".dot") as dot_file:
                dot_file.write(dot_source.encode('utf-8'))
                dot_path = dot_file.name

            svg_path = dot_path + ".svg"
            subprocess.run(["dot", "-Tsvg", dot_path, "-o", svg_path], check=True)

            file_url = QUrl.fromLocalFile(svg_path)
            view.load(file_url)

            # Cleanup SVG file when view is destroyed
            def cleanup():
                if os.path.exists(svg_path):
                    os.remove(svg_path)
            view.destroyed.connect(cleanup)

        except Exception as e:
            view.setHtml(f"<h3>Error rendering CFG:</h3><pre>{e}</pre>")

        return view


class GimpleDiffViewer(QDialog):
    def __init__(self, file_a, file_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"GIMPLE Diff Viewer: {os.path.basename(file_a)} vs {os.path.basename(file_b)}")
        self.resize(1000, 600)

        with open(file_a) as f:
            self.lines_a = f.readlines()
        with open(file_b) as f:
            self.lines_b = f.readlines()

        self.diff = list(difflib.unified_diff(self.lines_a, self.lines_b, lineterm=""))
        self.sections = self.segment_diff(self.diff)

        self.sidebar = QListWidget()
        self.sidebar.addItems(self.sections.keys())
        self.sidebar.currentTextChanged.connect(self.show_section)

        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Courier", 10))

        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.text_view)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Sections"))
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.sidebar.setCurrentRow(0)

    def segment_diff(self, diff):
        sections = {"All": diff}
        curr_section = "Misc"
        section_lines = []

        keyword_map = {
            "Dead Code": ["eliminate", "unused", "dce"],
            "Inlining": ["inline"],
            "Constant Folding": ["fold", "constant"],
            "Loop Optimizations": ["loop", "unroll", "ivopt"],
            "Strength Reduction": ["strength", "reduction"],
            "Reordering": ["reorder", "schedule"],
        }

        for line in diff:
            matched = False
            for section, keywords in keyword_map.items():
                if any(kw in line.lower() for kw in keywords):
                    sections.setdefault(section, []).append(line)
                    matched = True
            if not matched:
                sections.setdefault("Misc", []).append(line)
        return sections

    def show_section(self, section_name):
        lines = self.sections.get(section_name, [])
        colored = []
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                colored.append(f'<span style="color:green;">{line}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                colored.append(f'<span style="color:red;">{line}</span>')
            else:
                colored.append(f'<span>{line}</span>')
        html = "<pre>" + "\n".join(colored) + "</pre>"
        self.text_view.setHtml(html)

class CFGWindow(QDialog):
    def __init__(self, dot_source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Flow Graph (Zoomable SVG in WebView)")
        self.resize(1000, 800)

        self.web_view = QWebEngineView()
        layout = QVBoxLayout()
        layout.addWidget(self.web_view)
        self.setLayout(layout)

        self.render_svg(dot_source)

    def render_svg(self, dot_source):
        try:
            with tempfile.NamedTemporaryFile(dir=self.parent().temp_path, delete=False, suffix=".dot") as dot_file:
                dot_file.write(dot_source.encode('utf-8'))
                dot_path = dot_file.name

            svg_path = os.path.join(self.parent().temp_path, os.path.basename(dot_path) + ".svg")
            subprocess.run(["dot", "-Tsvg", dot_path, "-o", svg_path], check=True)

            # Load the SVG into the web view
            file_url = QUrl.fromLocalFile(svg_path)
            self.web_view.load(file_url)

        except Exception as e:
            self.web_view.setHtml(f"<h3>Error rendering CFG:</h3><pre>{e}</pre>")

        finally:
            # Don't delete the svg until the dialog is closed
            self.svg_path = svg_path

    def closeEvent(self, event):
        # Cleanup the SVG file when the window closes
        if hasattr(self, "svg_path") and os.path.exists(self.svg_path):
            os.remove(self.svg_path)
        event.accept()

class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setRenderHints(self.renderHints() | Qt.Antialiasing | Qt.SmoothTransformation)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.scale_factor = 1.15

    def wheelEvent(self, event):
        # Zoom in/out with mouse wheel
        if event.angleDelta().y() > 0:
            self.scale(self.scale_factor, self.scale_factor)
        else:
            self.scale(1 / self.scale_factor, 1 / self.scale_factor)

class CSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("blue"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = [
            "int", "float", "char", "double", "void", "return", "if", "else", "while",
            "for", "do", "switch", "case", "break", "continue", "struct", "typedef",
            "static", "const", "sizeof"
        ]
        for word in keywords:
            pattern = re.compile(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format))

        preprocessor_format = QTextCharFormat()
        preprocessor_format.setForeground(QColor("darkred"))
        preprocessor_pattern = re.compile(r'^\s*#\s*(include|define).*$')
        self.highlighting_rules.append((preprocessor_pattern, preprocessor_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("green"))
        comment_pattern = re.compile(r'//.*')
        self.highlighting_rules.append((comment_pattern, comment_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("magenta"))
        string_pattern = re.compile(r'"[^"\\]*(\\.[^"\\]*)*"')
        self.highlighting_rules.append((string_pattern, string_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                self.setFormat(start, end - start, fmt)

def parse_cfg(cfg_file_path):
    cfg_data = {}
    current_block_id = None

    with open(cfg_file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Start of a basic block
            match = re.match(r'^;; basic block (\d+), preds.*$', line)
            if match:
                current_block_id = int(match.group(1))
                cfg_data[current_block_id] = {'text': '', 'edges': []}
                continue

            # Successors (edges)
            match = re.match(r'^;; succs\s+(.+)$', line)
            if match and current_block_id is not None:
                successors = re.findall(r'(\d+)', match.group(1))
                cfg_data[current_block_id]['edges'] = list(map(int, successors))
                continue

            # Inside a block
            if current_block_id is not None:
                cfg_data[current_block_id]['text'] += line + "\n"

    return cfg_data


class OptimizationViewer(QDialog):
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Optimization Dump: {os.path.basename(title)}")
        self.resize(800, 600)

        layout = QVBoxLayout()
        self.text_area = QTextEdit()
        self.text_area.setPlainText(content)
        self.text_area.setReadOnly(True)
        layout.addWidget(self.text_area)

        self.setLayout(layout)

class RtlDiffViewer(QDialog):
    def __init__(self, file_a, file_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"RTL Diff: {os.path.basename(file_a)} vs {os.path.basename(file_b)}")
        self.resize(1000, 600)

        with open(file_a) as fa, open(file_b) as fb:
            a = fa.readlines(); b = fb.readlines()

        diff = list(difflib.unified_diff(a, b, lineterm=""))
        self.sections = self.segment_rtl(diff)

        self.sidebar = QListWidget()
        self.sidebar.addItems(self.sections.keys())
        self.sidebar.currentTextChanged.connect(self.show_section)

        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Courier", 10))

        splitter = QSplitter()
        splitter.addWidget(self.sidebar); splitter.addWidget(self.text_view)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("RTL Optimizations"))
        layout.addWidget(splitter)
        self.setLayout(layout)
        self.sidebar.setCurrentRow(0)

    def segment_rtl(self, diff):
        mapping = {
            "Instr Combine": ["combine", "peephole"],
            "Reg Allocation": ["reg", "reload"],
            "Branch Align": ["align"],
        }
        secs = {"All": diff}
        for line in diff:
            for sec, kw in mapping.items():
                if any(w in line.lower() for w in kw):
                    secs.setdefault(sec, []).append(line)
        secs["Misc"] = [l for l in diff if all(l not in v for v in secs.values())]
        return secs

    def show_section(self, sec):
        html = "<pre>"
        for line in self.sections.get(sec, []):
            c = "green" if line.startswith("+") and not line.startswith("+++") else \
                "red" if line.startswith("-") and not line.startswith("---") else "black"
            html += f'<span style="color:{c};">{line}</span>\n'
        html += "</pre>"
        self.text_view.setHtml(html)

def generate_pass_diffs(passes):
    diffs = []
    for i in range(len(passes) - 1):
        _, name1, file1 = passes[i]
        _, name2, file2 = passes[i + 1]
        with open(file1) as f1, open(file2) as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()
        diff = list(difflib.unified_diff(lines1, lines2, lineterm=""))
        diffs.append(((name1, name2), diff))
    return diffs

class GimplePassDiffTimeline(QDialog):
    def __init__(self, pass_diffs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GIMPLE Pass Diff Timeline")
        self.resize(1000, 600)

        self.sidebar = QListWidget()
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Courier", 10))

        for (name1, name2), _ in pass_diffs:
            self.sidebar.addItem(f"{name1} → {name2}")

        self.pass_diffs = dict(((name1, name2), diff) for (name1, name2), diff in pass_diffs)
        self.sidebar.currentRowChanged.connect(self.display_diff)

        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.text_view)

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.sidebar.setCurrentRow(0)

    def display_diff(self, index):
        item_text = self.sidebar.item(index).text()
        name1, name2 = item_text.split(" → ")
        diff = self.pass_diffs.get((name1, name2), [])
        html = "<pre>" + "\n".join(
            f'<span style="color:green;">{l}</span>' if l.startswith('+') and not l.startswith('+++') else
            f'<span style="color:red;">{l}</span>' if l.startswith('-') and not l.startswith('---') else
            l for l in diff
        ) + "</pre>"
        self.text_view.setHtml(html)

def generate_rtl_pass_diffs(passes):
    diffs = []
    for i in range(len(passes) - 1):
        _, name1, file1 = passes[i]
        _, name2, file2 = passes[i + 1]
        with open(file1) as f1, open(file2) as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()
        diff = list(difflib.unified_diff(lines1, lines2, lineterm=""))
        diffs.append(((name1, name2), diff))
    return diffs

class RtlPassDiffTimeline(QDialog):
    def __init__(self, pass_diffs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RTL Pass Diff Timeline")
        self.resize(1000, 600)

        self.sidebar = QListWidget()
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Courier", 10))

        for (name1, name2), _ in pass_diffs:
            self.sidebar.addItem(f"{name1} → {name2}")

        self.pass_diffs = dict(((name1, name2), diff) for (name1, name2), diff in pass_diffs)
        self.sidebar.currentRowChanged.connect(self.display_diff)

        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.text_view)

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.sidebar.setCurrentRow(0)

    def display_diff(self, index):
        item_text = self.sidebar.item(index).text()
        name1, name2 = item_text.split(" → ")
        diff = self.pass_diffs.get((name1, name2), [])
        html = "<pre>" + "\n".join(
            f'<span style="color:green;">{l}</span>' if l.startswith('+') and not l.startswith('+++') else
            f'<span style="color:red;">{l}</span>' if l.startswith('-') and not l.startswith('---') else
            l for l in diff
        ) + "</pre>"
        self.text_view.setHtml(html)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = self.temp_dir.name
        self.setWindowTitle("C File Viewer & Editor")
        self.setGeometry(100, 100, 800, 600)

        self.current_file = None

        self.text_edit = QTextEdit(self)
        self.setCentralWidget(self.text_edit)

        self.highlighter = CSyntaxHighlighter(self.text_edit.document())
        self.optimization_level = "-O2"  # default optimization level

        self.create_menu()

    def create_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        saveas_action = QAction("Save As", self)
        saveas_action.setShortcut("Ctrl+S")
        saveas_action.triggered.connect(self.save_as_file)
        file_menu.addAction(saveas_action)

        # Build menu
        build_menu = menubar.addMenu("Build")

        build_action = QAction("Build (Compile Only)", self)
        build_action.setShortcut("Ctrl+B")
        build_action.triggered.connect(self.build_only)
        build_menu.addAction(build_action)

        build_cfg_action = QAction("Build with CFG", self)
        build_cfg_action.setShortcut("Ctrl+Shift+B")
        build_cfg_action.triggered.connect(self.build_with_cfg)
        build_menu.addAction(build_cfg_action)

                # Optimization Level menu
        opt_menu = menubar.addMenu("Optimization Level")

        self.opt_group = {}

        def set_opt_level(opt):
            def setter():
                self.optimization_level = opt
                for level, action in self.opt_group.items():
                    action.setChecked(level == opt)
            return setter

        for level in ["-O0", "-O1", "-O2", "-O3", "-Og", "-Os", "-Ofast"]:
            action = QAction(level, self, checkable=True)
            if level == self.optimization_level:
                action.setChecked(True)
            action.triggered.connect(set_opt_level(level))
            opt_menu.addAction(action)
            self.opt_group[level] = action


        optimizations_menu = build_menu.addMenu("Build and Show Optimizations")

        gimple_action = QAction("Machine Independent (GIMPLE)", self)
        gimple_action.triggered.connect(lambda: self.build_and_show_optimizations(mode="gimple"))
        optimizations_menu.addAction(gimple_action)

        rtl_action = QAction("Machine Dependent (RTL)", self)
        rtl_action.triggered.connect(lambda: self.build_and_show_optimizations(mode="rtl"))
        optimizations_menu.addAction(rtl_action)

    def build_only(self):
        if not self.current_file:
            QMessageBox.warning(self, "Warning", "Please open or save a C file first.")
            return

        try:
            with open(self.current_file, 'w') as file:
                file.write(self.text_edit.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save before build:\n{e}")
            return

        cmd = ['gcc', self.current_file, self.optimization_level, '-o', os.path.join(self.temp_path, 'a.out')]

        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if process.returncode == 0:
                QMessageBox.information(self, "Build Success", "Compiled successfully!")
            else:
                QMessageBox.critical(self, "Build Failed", f"Errors:\n{process.stderr}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"GCC execution failed:\n{e}")

    def build_with_cfg(self):
        if not self.current_file:
            QMessageBox.warning(self, "Warning", "Please open or save a C file first.")
            return

        try:
            with open(self.current_file, 'w') as file:
                file.write(self.text_edit.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save before build:\n{e}")
            return

        cmd = ['gcc', self.current_file, self.optimization_level, '-fdump-tree-cfg', '-o', os.path.join(self.temp_path, 'a.out')]

        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            output = process.stdout
            error = process.stderr

            if process.returncode == 0:
                QMessageBox.information(self, "Build Success", "Compilation succeeded!")

                
                base = os.path.basename(self.current_file)
                pattern = os.path.join(self.temp_path, f"a-{base}.*.cfg")
                files = glob.glob(pattern)
                if not files:
                    QMessageBox.warning(self, "Warning", "No CFG dump file found.")
                    return

                cfg_file = files[-1]

                with open(cfg_file, 'r') as f:
                    cfg_text = f.read()

                # dot_source = parse_cfg_to_dot(cfg_text)
                # cfg_window = CFGWindow(dot_source, parent=self)
                # cfg_window.exec_()

                per_func_cfgs = extract_cfgs_per_function(cfg_text)
                if not per_func_cfgs:
                    QMessageBox.warning(self, "No CFGs", "Could not extract any functions.")
                    return

                cfg_tabbed_window = TabbedCFGWindow(per_func_cfgs, parent=self)
                cfg_tabbed_window.exec_()


                for fpath in files:
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        print(f"Warning: Could not remove CFG dump file {fpath}: {e}")


            else:
                QMessageBox.critical(self, "Build Failed", f"Errors:\n{error}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run gcc:\n{e}")


    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open C File",
            "",
            "C Files (*.c);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    content = file.read()
                    self.text_edit.setPlainText(content)
                    self.current_file = file_path
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def save_as_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            "",
            "C Files (*.c);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w') as file:
                    content = self.text_edit.toPlainText()
                    file.write(content)
                    self.current_file = file_path
                    QMessageBox.information(self, "Saved", "File saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def build_and_show_optimizations(self, mode):
        if not self.current_file:
            QMessageBox.warning(self, "Warning", "Please open or save a C file first.")
            return

        try:
            with open(self.current_file, 'w') as file:
                file.write(self.text_edit.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save before build:\n{e}")
            return

        base = os.path.splitext(os.path.basename(self.current_file))[0]
        cmd = ["gcc", self.current_file, self.optimization_level ]  # Enable optimizations

        # Append dump flags
        if mode == "gimple":
            cmd += ["-fdump-tree-all"]
            dump_ext = "*t.*"
        elif mode == "rtl":
            cmd += ["-fdump-rtl-all"]
            dump_ext = "*r.*"




        try:
            subprocess.run(cmd,cwd=self.temp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Pattern to find dump files
            pattern = os.path.join(self.temp_path, f"a-{base}.c.{dump_ext}")
            print(f"Looking for dump files with pattern: {pattern}")
            dump_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

            if not dump_files:
                QMessageBox.information(self, "No Dumps", f"No {mode.upper()} optimization dumps found.")
                return

            # Let user pick a dump file to view
            # if mode == "gimple":
            #     if len(dump_files) < 2:
            #         QMessageBox.warning(self, "Not Enough Dumps", "Need at least 2 GIMPLE dump files.")
            #         return

            #     file_a, ok1 = QFileDialog.getOpenFileName(self, "Select First GIMPLE Pass", self.temp_path, "GIMPLE (*t.*)")
            #     if not ok1: return
            #     file_b, ok2 = QFileDialog.getOpenFileName(self, "Select Second GIMPLE Pass", self.temp_path, "GIMPLE (*t.*)")
            #     if not ok2: return

            #     viewer = GimpleDiffViewer(file_a, file_b, parent=self)
            #     viewer.exec_()
            if mode == "gimple":
                passes = self.get_ordered_gimple_passes(base)
                if len(passes) < 2:
                    QMessageBox.warning(self, "Not Enough Dumps", "Need at least 2 GIMPLE dump files.")
                    return

                diffs = generate_pass_diffs(passes)
                viewer = GimplePassDiffTimeline(diffs, self)
                viewer.exec_()


            # if mode == "rtl":
            #     if len(dump_files) < 2:
            #         QMessageBox.warning(self, "Need 2 RTL dumps", "Run -fdump-rtl-all and select two files.")
            #         return
            #     f1, ok1 = QFileDialog.getOpenFileName(
            #         self, "Select First RTL Pass", os.getcwd(), "RTL Dumps (*r.*)"
            #     )
            #     if not ok1 or not f1: return

            #     f2, ok2 = QFileDialog.getOpenFileName(
            #         self, "Select Second RTL Pass", os.getcwd(), "RTL Dumps (*r.*)"
            #     )
            #     if not ok2 or not f2: return

            #     viewer = RtlDiffViewer(f1, f2, self)
            #     viewer.exec_()
            if mode == "rtl":    
                passes = self.get_ordered_rtl_passes(base)
                if len(passes) < 2:
                    QMessageBox.warning(self, "Not Enough RTL Dumps", "Need at least 2 RTL dump files.")
                    return

                diffs = generate_rtl_pass_diffs(passes)
                viewer = RtlPassDiffTimeline(diffs, self)
                viewer.exec_()


        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run gcc with {mode.upper()} optimizations:\n{e}")
    def get_ordered_rtl_passes(self, base_filename):
        pattern = os.path.join(self.temp_path, f"a-{base_filename}.c.*r.*")
        dump_files = glob.glob(pattern)

        def extract_info(f):
            match = re.search(r"\.(\d+)r\.(.+)$", f)
            if match:
                return int(match.group(1)), match.group(2), f
            return -1, "", f

        passes = sorted([extract_info(f) for f in dump_files], key=lambda x: x[0])
        return passes

    
    def get_ordered_gimple_passes(self, base_filename):
        pattern = os.path.join(self.temp_path, f"a-{base_filename}.c.*t.*")
        dump_files = glob.glob(pattern)

        def extract_info(f):
            match = re.search(r"\.(\d+)t\.(.+)$", f)
            if match:
                return int(match.group(1)), match.group(2), f
            return -1, "", f  # fallback

        passes = sorted([extract_info(f) for f in dump_files], key=lambda x: x[0])
        return passes

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
