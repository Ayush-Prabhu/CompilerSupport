# C Code Viewer & Optimization Visualizer

A PyQt5-based GUI application for viewing, editing, compiling, and analyzing C programs. This tool integrates with `gcc` to visualize control flow graphs (CFGs), view optimization passes (GIMPLE and RTL), and explore compiler transformations across optimization levels.

## Features

- **C Code Editor** with syntax highlighting
- **Compile with Optimization Levels** (`-O0`, `-O1`, `-O2`, `-O3`, `-Og`, `-Os`, `-Ofast`)
- **CFG Visualization**
  - Generates control flow graphs using Graphviz
  - Function-wise CFG tabs rendered as interactive SVG
- **Optimization Pass Diff Viewer**
  - View machine-independent (`GIMPLE`) and machine-dependent (`RTL`) compiler transformations
  - Compare changes between passes
  - Categorize diffs into sections (Inlining, Loop Optimizations, Constant Folding, etc.)
- **Interactive Timeline**
  - Navigate through optimization stages using a sidebar timeline
- Temporary files are stored in isolated temp directories and cleaned up automatically

## Requirements

- Python 3.6+
- PyQt5
- PyQtWebEngine
- Graphviz (with `dot` command in PATH)
- GCC (with `-fdump-tree-*` and `-fdump-rtl-*` support)

### Install dependencies

```bash
pip install pyqt5 pyqtwebengine
sudo apt install graphviz gcc     # On Debian/Ubuntu
```

## How to Use

```bash
python main.py
```

### Menu Overview

* **File**

  * `Open`: Load a `.c` file
  * `Save As`: Save edited code
* **Build**

  * `Build (Compile Only)`: Compile without running
  * `Build with CFG`: Compile with CFG dump and visualize
  * `Build and Show Optimizations`

    * `GIMPLE`: View high-level optimization changes
    * `RTL`: View low-level machine-specific optimizations
* **Optimization Level**

  * Choose `-O0`, `-O1`, ..., `-Ofast` for compilation

## Known Limitations

* Designed for use with `gcc`; Clang/LLVM not yet supported
* WebEngine is required to render SVG views
* May not render complex CFGs correctly if Graphviz is missing
