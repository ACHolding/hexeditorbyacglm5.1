#!/usr/bin/env python3.14
"""
AC's Hex Editor
A HexFiend-style hex editor with Atari & PS5 file format support
Blue text on black background
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import struct
import hashlib
import zlib

# ─── Constants ───────────────────────────────────────────────
BYTES_PER_ROW = 16

# ─── Atari Format Detector ──────────────────────────────────
class AtariFormatDetector:
    @staticmethod
    def detect(data, filename):
        ext = os.path.splitext(filename)[1].lower()
        fmt = {"name": "Unknown", "system": "Unknown", "details": {}}
        detectors = {
            '.a78': AtariFormatDetector._parse_a78,
            '.atr': AtariFormatDetector._parse_atr,
            '.car': AtariFormatDetector._parse_car,
            '.xex': AtariFormatDetector._parse_xex,
            '.rom': lambda d: {"name": "Atari ROM", "system": "Atari", "details": {"size": len(d)}},
        }
        if ext in detectors:
            fmt = detectors[ext](data)
        elif len(data) >= 2 and data[0] == 0xFF and data[1] == 0xFF:
            fmt = AtariFormatDetector._parse_xex(data)
        return fmt

    @staticmethod
    def _parse_a78(data):
        fmt = {"name": "Atari 7800 ROM (.a78)", "system": "Atari 7800", "details": {}}
        if len(data) >= 128:
            hdr = data[:128]
            magic = hdr[:4]
            if magic in (b'ATARI', b'A780'):
                fmt["details"]["magic"] = magic.decode('ascii', errors='replace')
                fmt["details"]["cart_name"] = hdr[4:36].decode('ascii', errors='replace').strip('\x00')
                fmt["details"]["mapper"] = hdr[49]
                fmt["details"]["mirroring"] = hdr[50]
                fmt["details"]["cart_type"] = hdr[51]
                fmt["details"]["controller1"] = hdr[52]
                fmt["details"]["controller2"] = hdr[53]
        return fmt

    @staticmethod
    def _parse_atr(data):
        fmt = {"name": "Atari Disk Image (.atr)", "system": "Atari 8-bit", "details": {}}
        if len(data) >= 16:
            magic = struct.unpack('<H', data[0:2])[0]
            if magic == 0x0296:
                paras = struct.unpack('<H', data[2:4])[0]
                sec_size = struct.unpack('<H', data[4:6])[0]
                fmt["details"]["magic"] = f"0x{magic:04X}"
                fmt["details"]["paragraphs"] = paras
                fmt["details"]["sector_size"] = sec_size
                fmt["details"]["total_bytes"] = paras * 16
                fmt["details"]["sectors"] = (paras * 16) // sec_size if sec_size else 0
        return fmt

    @staticmethod
    def _parse_car(data):
        fmt = {"name": "Atari Cartridge (.car)", "system": "Atari 8-bit", "details": {}}
        if len(data) >= 24 and data[:4] == b'CART':
            fmt["details"]["magic"] = "CART"
            cart_type = struct.unpack('<I', data[4:8])[0]
            fmt["details"]["cart_type_id"] = cart_type
            fmt["details"]["cart_name"] = data[8:24].decode('ascii', errors='replace').strip('\x00')
        return fmt

    @staticmethod
    def _parse_xex(data):
        fmt = {"name": "Atari Executable (.xex)", "system": "Atari 8-bit", "details": {}}
        if len(data) >= 4:
            if struct.unpack('<H', data[0:2])[0] == 0xFFFF:
                fmt["details"]["magic"] = "0xFFFF"
                segments = []
                pos = 2
                while pos + 3 < len(data):
                    if struct.unpack('<H', data[pos:pos+2])[0] == 0xFFFF:
                        pos += 2
                    if pos + 4 > len(data):
                        break
                    start = struct.unpack('<H', data[pos:pos+2])[0]
                    end   = struct.unpack('<H', data[pos+2:pos+4])[0]
                    if end < start:
                        break
                    segments.append((start, end))
                    pos += 4 + (end - start + 1)
                    while pos + 1 < len(data) and data[pos:pos+2] == b'\xff\xff':
                        pos += 2
                fmt["details"]["segments"] = segments
                fmt["details"]["segment_count"] = len(segments)
        return fmt


# ─── PS5 Format Detector ────────────────────────────────────
class PS5FormatDetector:
    @staticmethod
    def detect(data, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.elf' or (len(data) >= 4 and data[:4] == b'\x7fELF'):
            return PS5FormatDetector._parse_elf(data)
        if ext == '.pkg':
            return PS5FormatDetector._parse_pkg(data)
        if ext == '.self':
            return PS5FormatDetector._parse_self(data)
        if ext == '.sprx':
            return {"name": "PS5 SPRX Module", "system": "PlayStation 5",
                    "details": {"size": len(data)}}
        if ext == '.prc':
            return {"name": "PS5 PRC File", "system": "PlayStation 5",
                    "details": {"size": len(data), "magic": data[:4].hex() if len(data) >= 4 else ""}}
        if ext == '.eboot':
            return PS5FormatDetector._parse_elf(data)
        return {"name": "Unknown", "system": "Unknown", "details": {}}

    @staticmethod
    def _parse_elf(data):
        fmt = {"name": "ELF Executable", "system": "Unknown", "details": {}}
        if len(data) < 64 or data[:4] != b'\x7fELF':
            return fmt
        ei_class = data[4]
        ei_data  = data[5]
        ei_osabi = data[7]
        le = (ei_data == 1)
        e = '<' if le else '>'
        e_type    = struct.unpack(e+'H', data[16:18])[0]
        e_machine = struct.unpack(e+'H', data[18:20])[0]
        if ei_class == 2:
            e_entry = struct.unpack(e+'Q', data[24:32])[0]
            e_phoff = struct.unpack(e+'Q', data[32:40])[0]
            e_shoff = struct.unpack(e+'Q', data[40:48])[0]
            e_phnum = struct.unpack(e+'H', data[56:58])[0]
            e_shnum = struct.unpack(e+'H', data[60:62])[0]
        else:
            e_entry = struct.unpack(e+'I', data[24:28])[0]
            e_phoff = struct.unpack(e+'I', data[28:32])[0]
            e_shoff = struct.unpack(e+'I', data[32:36])[0]
            e_phnum = struct.unpack(e+'H', data[44:46])[0]
            e_shnum = struct.unpack(e+'H', data[48:50])[0]
        system = "PlayStation 5" if ei_osabi in (0x64, 0x65) or e_machine == 0xB7 else "Generic"
        if ei_class == 2 and system == "Generic":
            system = "PlayStation (possible)"
        type_names = {0:"NONE",1:"REL",2:"EXEC",3:"DYN",4:"CORE"}
        fmt["name"] = f"{'PS5 ' if system=='PlayStation 5' else ''}ELF ({'64' if ei_class==2 else '32'}-bit)"
        fmt["system"] = system
        fmt["details"] = {
            "class": "64-bit" if ei_class==2 else "32-bit",
            "endian": "Little" if le else "Big",
            "osabi": f"0x{ei_osabi:02X}",
            "type": type_names.get(e_type, f"0x{e_type:04X}"),
            "machine": f"0x{e_machine:04X}",
            "entry_point": f"0x{e_entry:016X}" if ei_class==2 else f"0x{e_entry:08X}",
            "program_headers": e_phnum,
            "section_headers": e_shnum,
        }
        return fmt

    @staticmethod
    def _parse_pkg(data):
        fmt = {"name": "PlayStation Package (.pkg)", "system": "PlayStation 5", "details": {}}
        if len(data) >= 64:
            magic = struct.unpack('>I', data[0:4])[0]
            if magic == 0x7F504B47:
                fmt["details"]["magic"] = "\\x7fPKG"
                pkg_type = struct.unpack('>I', data[4:8])[0]
                content_size = struct.unpack('>Q', data[8:16])[0]
                pkg_size = struct.unpack('>Q', data[24:32])[0]
                fmt["details"]["pkg_type"] = f"0x{pkg_type:08X}"
                fmt["details"]["content_size"] = f"{content_size:,}"
                fmt["details"]["pkg_size"] = f"{pkg_size:,}"
                title_id = data[48:58].decode('ascii', errors='replace').strip('\x00')
                fmt["details"]["title_id"] = title_id
        return fmt

    @staticmethod
    def _parse_self(data):
        fmt = {"name": "PS5 SELF File", "system": "PlayStation 5", "details": {}}
        if len(data) >= 4:
            fmt["details"]["magic"] = data[:4].hex()
        return fmt


# ─── Main Application ────────────────────────────────────────
class ACHexEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("AC's Hex Editor")
        self.root.geometry("1320x820")
        self.root.minsize(960, 600)
        self.root.configure(bg="#060610")

        # ── Colour palette ──
        self.C_BG          = "#080810"
        self.C_TEXT         = "#4499ff"
        self.C_OFFSET      = "#2e6ab8"
        self.C_ASCII       = "#5aa8e6"
        self.C_NULL        = "#1c3050"
        self.C_HEADER_BG   = "#0c0c1e"
        self.C_STATUS_BG   = "#0a0a16"
        self.C_SEL_BG      = "#1a4488"
        self.C_SEL_FG      = "#e8f0ff"
        self.C_CURSOR_BG   = "#0e2855"
        self.C_CURSOR_OUT  = "#5599ff"
        self.C_MODIFIED    = "#ff6644"
        self.C_BORDER      = "#1a2848"
        self.C_ACCENT      = "#66bbff"
        self.C_INFO        = "#44cc88"
        self.C_WARN        = "#ffaa44"

        # ── Data ──
        self.file_data       = bytearray()
        self.original_data   = bytearray()
        self.modified_offsets: set[int] = set()
        self.file_path       = None
        self.file_format_info = None
        self.scroll_offset   = 0
        self.selected_offset = -1
        self.selection_start = -1
        self.selection_end   = -1
        self.editing_hex     = True
        self.cursor_nibble   = 0
        self.visible_rows    = 0
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.search_bytes    = None
        self.last_search_pos = -1

        # ── Font ──
        self.font_family = "Consolas"
        self.font_size   = 13
        self.font = (self.font_family, self.font_size)
        self.char_w = self._measure_char_width()

        self._build_menu()
        self._build_gui()
        self._bind_events()
        self._refresh()

    # ────────── helpers ──────────
    def _measure_char_width(self):
        tmp = tk.Canvas(self.root)
        tid = tmp.create_text(0, 0, text="A", font=self.font, anchor=tk.NW)
        bbox = tmp.bbox(tid)
        tmp.destroy()
        return (bbox[2] - bbox[0]) if bbox else 9

    @property
    def row_h(self):
        return self.font_size + 8

    # ────────── geometry constants for hex layout ──────────
    def _layout(self):
        cw = self.char_w
        hex_start_x     = 110
        byte_w          = cw * 2.65
        group_gap       = cw * 1.4
        group_w         = byte_w * 8 + group_gap
        ascii_start_x   = hex_start_x + group_w * 2 + cw * 1.8
        return hex_start_x, byte_w, group_gap, group_w, ascii_start_x, cw

    # ────────── menu ──────────
    def _build_menu(self):
        mb = tk.Menu(self.root, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))

        fm = tk.Menu(mb, tearoff=0, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))
        fm.add_command(label="Open File…", command=self.open_file, accelerator="Ctrl+O")
        fm.add_command(label="Import Hex Dump…", command=self.import_hex, accelerator="Ctrl+I")
        fm.add_separator()
        fm.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        fm.add_command(label="Save As…", command=self.save_as, accelerator="Ctrl+Shift+S")
        fm.add_separator()
        fm.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        fm.add_separator()
        fm.add_command(label="Exit", command=self.root.quit, accelerator="Ctrl+Q")
        mb.add_cascade(label="File", menu=fm)

        em = tk.Menu(mb, tearoff=0, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))
        em.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        em.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        em.add_separator()
        em.add_command(label="Copy Hex", command=self.copy_hex, accelerator="Ctrl+C")
        em.add_command(label="Copy ASCII", command=self.copy_ascii, accelerator="Ctrl+Shift+C")
        em.add_command(label="Paste", command=self.paste, accelerator="Ctrl+V")
        em.add_separator()
        em.add_command(label="Select All", command=self.select_all, accelerator="Ctrl+A")
        em.add_command(label="Fill Selection…", command=self.fill_selection)
        mb.add_cascade(label="Edit", menu=em)

        vm = tk.Menu(mb, tearoff=0, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))
        vm.add_command(label="Go to Offset…", command=self.goto_offset, accelerator="Ctrl+G")
        vm.add_command(label="Jump Start", command=self.jump_start, accelerator="Home")
        vm.add_command(label="Jump End", command=self.jump_end, accelerator="End")
        vm.add_separator()
        vm.add_command(label="Toggle HEX / ASCII Edit", command=self.toggle_mode, accelerator="Tab")
        vm.add_separator()
        vm.add_command(label="Font +", command=lambda: self._font_resize(1), accelerator="Ctrl++")
        vm.add_command(label="Font −", command=lambda: self._font_resize(-1), accelerator="Ctrl+−")
        mb.add_cascade(label="View", menu=vm)

        sm = tk.Menu(mb, tearoff=0, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))
        sm.add_command(label="Find…", command=self.find_dialog, accelerator="Ctrl+F")
        sm.add_command(label="Find Next", command=self.find_next, accelerator="F3")
        sm.add_command(label="Find Previous", command=self.find_prev, accelerator="Shift+F3")
        sm.add_separator()
        sm.add_command(label="Replace…", command=self.replace_dialog, accelerator="Ctrl+H")
        mb.add_cascade(label="Search", menu=sm)

        tm = tk.Menu(mb, tearoff=0, bg=self.C_HEADER_BG, fg=self.C_TEXT,
                     activebackground=self.C_SEL_BG, activeforeground=self.C_SEL_FG,
                     font=(self.font_family, 10))
        tm.add_command(label="File Info…", command=self.show_file_info, accelerator="Ctrl+D")
        tm.add_command(label="Checksums…", command=self.show_checksums)
        tm.add_separator()
        tm.add_command(label="Atari Format Info", command=self.show_atari_info)
        tm.add_command(label="PS5 Format Info", command=self.show_ps5_info)
        tm.add_separator()
        tm.add_command(label="Export Hex Dump…", command=self.export_hex_dump)
        tm.add_command(label="Export C Array…", command=self.export_c)
        tm.add_command(label="Export Python…", command=self.export_py)
        mb.add_cascade(label="Tools", menu=tm)

        self.root.config(menu=mb)

    # ────────── GUI ──────────
    def _build_gui(self):
        main = tk.Frame(self.root, bg=self.C_BG)
        main.pack(fill=tk.BOTH, expand=True)

        # title bar
        tb = tk.Frame(main, bg=self.C_HEADER_BG, height=38)
        tb.pack(fill=tk.X); tb.pack_propagate(False)
        tk.Label(tb, text="⚡ AC's Hex Editor", bg=self.C_HEADER_BG,
                 fg=self.C_ACCENT, font=(self.font_family, 14, "bold")).pack(side=tk.LEFT, padx=10)
        self.lbl_format = tk.Label(tb, text="", bg=self.C_HEADER_BG,
                                   fg=self.C_INFO, font=(self.font_family, 10))
        self.lbl_format.pack(side=tk.LEFT, padx=20)
        self.lbl_file = tk.Label(tb, text="No file loaded", bg=self.C_HEADER_BG,
                                 fg=self.C_WARN, font=(self.font_family, 10))
        self.lbl_file.pack(side=tk.RIGHT, padx=10)

        # column headers
        hf = tk.Frame(main, bg="#0c0c1a", height=28)
        hf.pack(fill=tk.X); hf.pack_propagate(False)
        hc = tk.Canvas(hf, bg="#0c0c1a", highlightthickness=0, height=28)
        hc.pack(fill=tk.X)
        hx, bw, gg, gw, asc_x, cw = self._layout()
        hc.create_text(10, 14, text="Offset", anchor=tk.W, fill=self.C_OFFSET,
                       font=(self.font_family, 10, "bold"))
        col_hdr = ""
        for i in range(16):
            if i == 8: col_hdr += "  "
            col_hdr += f"{i:02X} "
        hc.create_text(hx, 14, text=col_hdr.strip(), anchor=tk.W, fill=self.C_TEXT,
                       font=(self.font_family, 10, "bold"))
        hc.create_text(asc_x, 14, text="ASCII", anchor=tk.W, fill=self.C_ASCII,
                       font=(self.font_family, 10, "bold"))

        # hex canvas + scrollbars
        cf = tk.Frame(main, bg=self.C_BG)
        cf.pack(fill=tk.BOTH, expand=True)
        self.vscroll = tk.Scrollbar(cf, orient=tk.VERTICAL, bg=self.C_HEADER_BG,
                                    troughcolor=self.C_BG, activebackground=self.C_SEL_BG)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(cf, bg=self.C_BG, highlightthickness=0,
                                yscrollcommand=self._vscroll_set)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.vscroll.config(command=self._vscroll_cmd)

        # status bar
        sb = tk.Frame(main, bg=self.C_STATUS_BG, height=30)
        sb.pack(fill=tk.X, side=tk.BOTTOM); sb.pack_propagate(False)
        self.st_off = tk.Label(sb, text="Offset: —", bg=self.C_STATUS_BG,
                               fg=self.C_TEXT, font=(self.font_family, 10))
        self.st_off.pack(side=tk.LEFT, padx=8)
        self.st_val = tk.Label(sb, text="Value: —", bg=self.C_STATUS_BG,
                               fg=self.C_INFO, font=(self.font_family, 10))
        self.st_val.pack(side=tk.LEFT, padx=8)
        self.st_mode = tk.Label(sb, text="HEX", bg=self.C_STATUS_BG,
                                fg=self.C_WARN, font=(self.font_family, 10, "bold"))
        self.st_mode.pack(side=tk.LEFT, padx=8)
        self.st_size = tk.Label(sb, text="0 bytes", bg=self.C_STATUS_BG,
                                fg=self.C_TEXT, font=(self.font_family, 10))
        self.st_size.pack(side=tk.LEFT, padx=8)
        self.st_mod = tk.Label(sb, text="", bg=self.C_STATUS_BG,
                               fg=self.C_MODIFIED, font=(self.font_family, 10, "bold"))
        self.st_mod.pack(side=tk.LEFT, padx=8)
        self.st_sel = tk.Label(sb, text="", bg=self.C_STATUS_BG,
                               fg=self.C_ACCENT, font=(self.font_family, 10))
        self.st_sel.pack(side=tk.RIGHT, padx=8)

    # ────────── events ──────────
    def _bind_events(self):
        self.canvas.bind("<Configure>", lambda e: self._refresh())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_wheel)          # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-3)) # Linux up
        self.canvas.bind("<Button-5>", lambda e: self._scroll(3))  # Linux down
        self.canvas.bind("<Key>", self._on_key)
        self.canvas.bind("<FocusIn>", lambda e: self.canvas.focus_set())

        for seq, cmd in [
            ("<Control-o>",  lambda e: self.open_file()),
            ("<Control-i>",  lambda e: self.import_hex()),
            ("<Control-s>",  lambda e: self.save_file()),
            ("<Control-S>",  lambda e: self.save_as()),
            ("<Control-n>",  lambda e: self.new_file()),
            ("<Control-q>",  lambda e: self.root.quit()),
            ("<Control-z>",  lambda e: self.undo()),
            ("<Control-y>",  lambda e: self.redo()),
            ("<Control-c>",  lambda e: self.copy_hex()),
            ("<Control-C>",  lambda e: self.copy_ascii()),
            ("<Control-v>",  lambda e: self.paste()),
            ("<Control-a>",  lambda e: self.select_all()),
            ("<Control-g>",  lambda e: self.goto_offset()),
            ("<Control-f>",  lambda e: self.find_dialog()),
            ("<Control-h>",  lambda e: self.replace_dialog()),
            ("<Control-d>",  lambda e: self.show_file_info()),
            ("<Control-equal>", lambda e: self._font_resize(1)),
            ("<Control-minus>", lambda e: self._font_resize(-1)),
            ("<F3>",         lambda e: self.find_next()),
            ("<Shift-F3>",   lambda e: self.find_prev()),
            ("<Home>",       lambda e: self.jump_start()),
            ("<End>",        lambda e: self.jump_end()),
            ("<Tab>",        lambda e: self.toggle_mode()),
            ("<Up>",         lambda e: self._move(0, -1)),
            ("<Down>",       lambda e: self._move(0, 1)),
            ("<Left>",       lambda e: self._move(-1, 0)),
            ("<Right>",      lambda e: self._move(1, 0)),
            ("<Prior>",      lambda e: self._page(-1)),
            ("<Next>",       lambda e: self._page(1)),
        ]:
            self.root.bind(seq, cmd)

    # ────────── file ops ──────────
    def open_file(self):
        p = filedialog.askopenfilename(
            title="Open — AC's Hex Editor",
            filetypes=[("All","*.*"),("Atari","*.a78 *.atr *.car *.xex *.rom"),
                       ("PS5","*.elf *.self *.sprx *.pkg *.prc *.eboot"),("Binary","*.bin *.dat")])
        if p: self._load(p)

    def import_hex(self):
        p = filedialog.askopenfilename(
            title="Import Hex Dump — AC's Hex Editor",
            filetypes=[("Hex / Text","*.hex *.txt"),("All","*.*")])
        if not p: return
        try:
            txt = open(p, 'r').read()
            data = self._parse_hex_dump(txt)
            if data:
                self._set_data(bytearray(data), file_path=None)
        except Exception as ex:
            messagebox.showerror("Import Error", str(ex))

    def _parse_hex_dump(self, txt):
        data = bytearray()
        for line in txt.strip().splitlines():
            line = line.strip()
            if not line: continue
            if line.startswith(':'):                       # Intel HEX
                bc = int(line[1:3], 16)
                data.extend(bytes.fromhex(line[9:9+bc*2]))
                continue
            parts = line.split(':')
            if len(parts) >= 2:
                hp = parts[1].split('|')[0].split('  ')[0].strip()
                try:
                    for bs in hp.split():
                        if len(bs) == 2: data.append(int(bs, 16))
                except: pass
            else:
                try:
                    clean = txt.replace(' ','').replace('\n','').replace('\r','')
                    return bytes.fromhex(clean)
                except: pass
        return data or None

    def _load(self, path):
        try:
            with open(path, 'rb') as f:
                self._set_data(bytearray(f.read()), file_path=path)
        except Exception as ex:
            messagebox.showerror("Error", f"Cannot open:\n{ex}")

    def _set_data(self, data: bytearray, file_path=None):
        self.file_data = data
        self.original_data = bytearray(data)
        self.modified_offsets.clear()
        self.file_path = file_path
        self.scroll_offset = 0
        self.selected_offset = 0 if data else -1
        self.selection_start = self.selection_end = -1
        self.undo_stack.clear(); self.redo_stack.clear()
        self._detect_format()
        self._refresh(); self._update_status()

    def _detect_format(self):
        path = self.file_path or ""
        ps5  = PS5FormatDetector.detect(self.file_data, path)
        atari = AtariFormatDetector.detect(self.file_data, path)
        ext = os.path.splitext(path)[1].lower()
        atari_exts = {'.a78','.atr','.car','.xex','.rom'}
        ps5_exts   = {'.elf','.self','.sprx','.pkg','.prc','.eboot'}
        if atari["system"].startswith("Atari") or ext in atari_exts:
            self.file_format_info = atari
        elif ps5["system"].startswith("PlayStation") or ext in ps5_exts:
            self.file_format_info = ps5
        else:
            self.file_format_info = {"name":"Binary","system":"Unknown","details":{"size":len(self.file_data)}}

        fn = os.path.basename(path) if path else "Untitled"
        self.lbl_file.config(text=f"📄 {fn}", fg=self.C_TEXT)
        fi = self.file_format_info
        tag = "🎮" if "Atari" in fi.get("system","") or "Play" in fi.get("system","") else "📦"
        self.lbl_format.config(text=f"{tag} {fi['name']}  [{fi['system']}]",
                               fg=self.C_INFO if "Atari" in fi.get("system","") else self.C_ACCENT)

    def save_file(self):
        if self.file_path:
            try:
                open(self.file_path,'wb').write(self.file_data)
                self.original_data = bytearray(self.file_data)
                self.modified_offsets.clear()
                self._refresh(); self._update_status()
            except Exception as ex:
                messagebox.showerror("Error", str(ex))
        else: self.save_as()

    def save_as(self):
        p = filedialog.asksaveasfilename(
            title="Save As — AC's Hex Editor", defaultextension=".bin",
            filetypes=[("Binary","*.bin"),("All","*.*"),("Atari","*.a78 *.car *.rom *.atr *.xex"),
                       ("PS5","*.elf *.pkg *.self")])
        if p:
            try:
                open(p,'wb').write(self.file_data)
                self.file_path = p
                self.original_data = bytearray(self.file_data)
                self.modified_offsets.clear()
                self._detect_format(); self._refresh(); self._update_status()
            except Exception as ex:
                messagebox.showerror("Error", str(ex))

    def new_file(self):
        self._set_data(bytearray(256), file_path=None)
        self.lbl_file.config(text="📄 New File", fg=self.C_WARN)
        self.lbl_format.config(text="")

    # ────────── drawing ──────────
    def _refresh(self):
        self.canvas.delete("all")
        if not self.file_data:
            self.canvas.create_text(400,300, text="AC's Hex Editor\n\nCtrl+O  Open a file\nCtrl+N  New file",
                                    fill=self.C_NULL, font=(self.font_family,16), justify=tk.CENTER)
            return

        hx, bw, gg, gw, asc_x, cw = self._layout()
        rh = self.row_h
        ch = self.canvas.winfo_height()
        self.visible_rows = max(1, ch // rh)
        total = (len(self.file_data) + 15) // 16

        for row in range(self.visible_rows):
            off0 = (self.scroll_offset + row) * BYTES_PER_ROW
            if off0 >= len(self.file_data): break
            y = row * rh + rh // 2

            # offset
            self.canvas.create_text(10, y, text=f"{off0:08X}", anchor=tk.W,
                                    fill=self.C_OFFSET, font=self.font)
            # separator
            self.canvas.create_line(hx-8, y-rh//2+2, hx-8, y+rh//2-2, fill=self.C_BORDER)

            # hex bytes
            for col in range(BYTES_PER_ROW):
                boff = off0 + col
                if boff >= len(self.file_data): break
                val = self.file_data[boff]
                grp = col // 8
                pig = col % 8
                x = hx + grp * gw + pig * bw

                sel  = self._selected(boff)
                mod  = boff in self.modified_offsets
                cur  = boff == self.selected_offset

                # backgrounds
                if sel:
                    self.canvas.create_rectangle(x-2, y-rh//2+1, x+bw-1, y+rh//2-1,
                                                 fill=self.C_SEL_BG, outline="")
                elif cur and self.editing_hex:
                    cx = x + (self.cursor_nibble * cw)
                    tw = cw
                    self.canvas.create_rectangle(cx-1, y-rh//2+1, cx+tw+1, y+rh//2-1,
                                                 fill=self.C_CURSOR_BG, outline=self.C_CURSOR_OUT)

                fg = (self.C_SEL_FG if sel else
                      self.C_MODIFIED if mod else
                      self.C_NULL if val == 0 else
                      self.C_TEXT)
                self.canvas.create_text(x, y, text=f"{val:02X}", anchor=tk.W, fill=fg, font=self.font)

            # separator before ASCII
            self.canvas.create_line(asc_x-8, y-rh//2+2, asc_x-8, y+rh//2-2, fill=self.C_BORDER)

            # ASCII
            for col in range(BYTES_PER_ROW):
                boff = off0 + col
                if boff >= len(self.file_data): break
                val = self.file_data[boff]
                x = asc_x + col * cw

                sel = self._selected(boff)
                mod = boff in self.modified_offsets
                cur = boff == self.selected_offset and not self.editing_hex

                if sel:
                    self.canvas.create_rectangle(x-1, y-rh//2+1, x+cw+1, y+rh//2-1,
                                                 fill=self.C_SEL_BG, outline="")
                elif cur:
                    self.canvas.create_rectangle(x-1, y-rh//2+1, x+cw+1, y+rh//2-1,
                                                 fill=self.C_CURSOR_BG, outline=self.C_CURSOR_OUT)

                ch_ = chr(val) if 0x20 <= val <= 0x7e else '.'
                fg = (self.C_SEL_FG if sel else
                      self.C_MODIFIED if mod else
                      self.C_ASCII if 0x20 <= val <= 0x7e else
                      self.C_NULL)
                self.canvas.create_text(x, y, text=ch_, anchor=tk.W, fill=fg, font=self.font)

    def _selected(self, off):
        if self.selection_start >= 0 and self.selection_end >= 0 and self.selection_start != self.selection_end:
            s, e = sorted((self.selection_start, self.selection_end))
            return s <= off <= e
        return off == self.selected_offset

    # ────────── interaction ──────────
    def _offset_at(self, x, y):
        if not self.file_data: return -1
        hx, bw, gg, gw, asc_x, cw = self._layout()
        rh = self.row_h
        row = int(y // rh) + self.scroll_offset
        col = -1

        if x >= asc_x:
            col = int((x - asc_x) / cw)
        elif x >= hx:
            grp = int((x - hx) / gw)
            pig = int(((x - hx) - grp * gw) / bw)
            col = grp * 8 + pig

        if 0 <= row and 0 <= col < BYTES_PER_ROW:
            off = row * BYTES_PER_ROW + col
            return off if off < len(self.file_data) else -1
        return -1

    def _on_click(self, ev):
        off = self._offset_at(self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y))
        if off >= 0:
            self.selected_offset = off
            self.selection_start = off
            self.selection_end = off
            self.cursor_nibble = 0
            self._refresh(); self._update_status()
        self.canvas.focus_set()

    def _on_drag(self, ev):
        off = self._offset_at(self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y))
        if off >= 0:
            self.selection_end = off
            self.selected_offset = off
            self._refresh(); self._update_status()

    def _on_wheel(self, ev):
        self._scroll(-3 if ev.delta > 0 else 3)

    def _scroll(self, delta):
        total = (len(self.file_data) + 15) // 16 if self.file_data else 0
        self.scroll_offset = max(0, min(max(0, total - self.visible_rows), self.scroll_offset + delta))
        self._refresh()

    def _vscroll_set(self, lo, hi):
        self.vscroll.set(lo, hi)

    def _vscroll_cmd(self, mode, val, *args):
        total = (len(self.file_data)+15)//16 if self.file_data else 0
        if mode == 'moveto':
            self.scroll_offset = int(float(val) * total)
        elif mode == 'scroll':
            self.scroll_offset += int(val) * 3
        self.scroll_offset = max(0, min(max(0, total - self.visible_rows), self.scroll_offset))
        self._refresh()

    # ────────── keyboard ──────────
    def _on_key(self, ev):
        if not self.file_data or self.selected_offset < 0: return
        ch = ev.char
        if self.editing_hex:
            if ch and ch.upper() in '0123456789ABCDEF':
                nib = int(ch, 16)
                off = self.selected_offset
                old = self.file_data[off]
                if self.cursor_nibble == 0:
                    new = (nib << 4) | (old & 0x0F)
                    self.file_data[off] = new
                    self._push_undo(off, old, new)
                    self.cursor_nibble = 1
                else:
                    new = (old & 0xF0) | nib
                    self.file_data[off] = new
                    self._push_undo(off, old, new)
                    self.cursor_nibble = 0
                    if off < len(self.file_data) - 1:
                        self.selected_offset += 1
                self._mark_modified(off)
                self._ensure(); self._refresh(); self._update_status(); return
        else:
            if ch and ord(ch) >= 0x20:
                off = self.selected_offset
                old = self.file_data[off]; new = ord(ch)
                self.file_data[off] = new
                self._push_undo(off, old, new)
                self._mark_modified(off)
                if off < len(self.file_data) - 1:
                    self.selected_offset += 1
                self._ensure(); self._refresh(); self._update_status(); return

        if ev.keysym == 'BackSpace':
            off = self.selected_offset
            if off > 0:
                off -= 1; self.selected_offset = off
                old = self.file_data[off]; self.file_data[off] = 0
                self._push_undo(off, old, 0); self._mark_modified(off)
                self.cursor_nibble = 0; self._ensure(); self._refresh(); self._update_status()
        elif ev.keysym == 'Delete':
            off = self.selected_offset
            if 0 <= off < len(self.file_data):
                old = self.file_data[off]; self.file_data[off] = 0
                self._push_undo(off, old, 0); self._mark_modified(off)
                self._refresh(); self._update_status()

    def _mark_modified(self, off):
        if self.file_data[off] != self.original_data[off]:
            self.modified_offsets.add(off)
        else:
            self.modified_offsets.discard(off)

    def _push_undo(self, off, old, new):
        self.undo_stack.append((off, old, new)); self.redo_stack.clear()

    # ────────── navigation ──────────
    def _move(self, dx, dy):
        if not self.file_data or self.selected_offset < 0: return
        if self.editing_hex and dx:
            if dx > 0:
                if self.cursor_nibble == 0: self.cursor_nibble = 1; self._refresh(); return
                else: self.cursor_nibble = 0; dx = 1
            else:
                if self.cursor_nibble == 1: self.cursor_nibble = 0; self._refresh(); return
                else: self.cursor_nibble = 1; dx = -1
        row = self.selected_offset // BYTES_PER_ROW + dy
        col = self.selected_offset % BYTES_PER_ROW + dx
        no = row * BYTES_PER_ROW + col
        if 0 <= no < len(self.file_data):
            self.selected_offset = no
            self.selection_start = self.selection_end = no
            self._ensure(); self._refresh(); self._update_status()

    def _page(self, d):
        if not self.file_data: return
        delta = self.visible_rows * BYTES_PER_ROW * d
        self.selected_offset = max(0, min(len(self.file_data)-1, self.selected_offset + delta))
        self.selection_start = self.selection_end = self.selected_offset
        self.scroll_offset = max(0, self.scroll_offset + d * self.visible_rows)
        self._ensure(); self._refresh(); self._update_status()

    def _ensure(self):
        if not self.file_data: return
        row = self.selected_offset // BYTES_PER_ROW
        if row < self.scroll_offset:
            self.scroll_offset = row
        elif row >= self.scroll_offset + self.visible_rows:
            self.scroll_offset = row - self.visible_rows + 1

    def goto_offset(self):
        r = simpledialog.askstring("Go to Offset", "Offset (hex / dec):", parent=self.root)
        if not r: return
        try:
            off = int(r, 16) if r.lower().startswith('0x') or all(c in '0123456789abcdefABCDEF' for c in r) else int(r)
        except: messagebox.showerror("Error","Invalid offset"); return
        if 0 <= off < len(self.file_data):
            self.selected_offset = off; self.selection_start = self.selection_end = off
            self.scroll_offset = max(0, off // BYTES_PER_ROW - self.visible_rows // 2)
            self._ensure(); self._refresh(); self._update_status()
        else:
            messagebox.showwarning("Invalid", f"0 – {len(self.file_data)-1}")

    def jump_start(self):
        self.selected_offset = 0; self.scroll_offset = 0
        self._refresh(); self._update_status()

    def jump_end(self):
        if self.file_data:
            self.selected_offset = len(self.file_data)-1
            total = (len(self.file_data)+15)//16
            self.scroll_offset = max(0, total - self.visible_rows)
            self._refresh(); self._update_status()

    def toggle_mode(self):
        self.editing_hex = not self.editing_hex; self.cursor_nibble = 0; self._update_status()
        return "break"

    # ────────── undo / redo ──────────
    def undo(self):
        if not self.undo_stack: return
        off, old, new = self.undo_stack.pop()
        self.file_data[off] = old; self.redo_stack.append((off, old, new))
        self._mark_modified(off); self._refresh(); self._update_status()

    def redo(self):
        if not self.redo_stack: return
        off, old, new = self.redo_stack.pop()
        self.file_data[off] = new; self.undo_stack.append((off, old, new))
        self._mark_modified(off); self._refresh(); self._update_status()

    # ────────── clipboard ──────────
    def copy_hex(self):
        if self.selection_start < 0: return
        s, e = sorted((self.selection_start, self.selection_end))
        self.root.clipboard_clear()
        self.root.clipboard_append(' '.join(f'{self.file_data[i]:02X}' for i in range(s, e+1)))

    def copy_ascii(self):
        if self.selection_start < 0: return
        s, e = sorted((self.selection_start, self.selection_end))
        self.root.clipboard_append(''.join(chr(self.file_data[i]) if 0x20<=self.file_data[i]<=0x7e else '.'
                                     for i in range(s, e+1)))

    def paste(self):
        try:
            clip = self.root.clipboard_get().replace(' ','').replace('\n','').replace('\r','')
            data = bytes.fromhex(clip) if all(c in '0123456789abcdefABCDEF' for c in clip) and len(clip)%2==0 else clip.encode('latin-1')
            off = max(0, self.selected_offset)
            for i, b in enumerate(data):
                if off+i < len(self.file_data):
                    old = self.file_data[off+i]; self.file_data[off+i] = b
                    self._push_undo(off+i, old, b); self._mark_modified(off+i)
            self._refresh(); self._update_status()
        except: pass

    def select_all(self):
        if self.file_data:
            self.selection_start = 0; self.selection_end = len(self.file_data)-1
            self._refresh(); self._update_status()

    def fill_selection(self):
        if self.selection_start < 0: return
        r = simpledialog.askstring("Fill", "Byte (hex):", parent=self.root)
        if not r: return
        try: fv = int(r, 16) & 0xFF
        except: return
        s, e = sorted((self.selection_start, self.selection_end))
        for i in range(s, e+1):
            old = self.file_data[i]; self.file_data[i] = fv
            self._push_undo(i, old, fv); self._mark_modified(i)
        self._refresh(); self._update_status()

    # ────────── search ──────────
    def find_dialog(self):
        d = tk.Toplevel(self.root); d.title("Find — AC's Hex Editor")
        d.geometry("460x210"); d.configure(bg=self.C_BG); d.transient(self.root); d.grab_set()
        tk.Label(d, text="Search:", bg=self.C_BG, fg=self.C_TEXT, font=self.font).pack(pady=(15,5), padx=15, anchor=tk.W)
        ent = tk.Entry(d, bg="#111122", fg=self.C_TEXT, insertbackground=self.C_TEXT, font=self.font, relief=tk.FLAT)
        ent.pack(fill=tk.X, padx=15); ent.focus_set()
        mv = tk.StringVar(value="hex")
        mf = tk.Frame(d, bg=self.C_BG); mf.pack(fill=tk.X, padx=15, pady=8)
        for txt, val in [("Hex","hex"),("ASCII","ascii"),("UTF-8","utf8")]:
            tk.Radiobutton(mf, text=txt, variable=mv, value=val, bg=self.C_BG,
                           fg=self.C_TEXT, selectcolor=self.C_HEADER_BG,
                           activebackground=self.C_BG, font=self.font).pack(side=tk.LEFT, padx=6)
        def go():
            q = ent.get().strip()
            if not q: return
            try:
                if mv.get()=="hex":   self.search_bytes = bytes.fromhex(q.replace(' ',''))
                elif mv.get()=="utf8": self.search_bytes = q.encode('utf-8')
                else:                  self.search_bytes = q.encode('ascii','replace')
                self.last_search_pos = -1; self.find_next(); d.destroy()
            except Exception as ex: messagebox.showerror("Error", str(ex), parent=d)
        bf = tk.Frame(d, bg=self.C_BG); bf.pack(fill=tk.X, padx=15, pady=8)
        tk.Button(bf, text="Find", command=go, bg=self.C_SEL_BG, fg=self.C_SEL_FG,
                  font=self.font, relief=tk.FLAT, padx=20).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text="Cancel", command=d.destroy, bg=self.C_HEADER_BG,
                  fg=self.C_TEXT, font=self.font, relief=tk.FLAT, padx=20).pack(side=tk.RIGHT, padx=4)
        ent.bind('<Return>', lambda e: go())

    def find_next(self):
        if not self.search_bytes or not self.file_data: return
        start = max(0, self.last_search_pos + 1)
        pos = self.file_data.find(self.search_bytes, start)
        if pos >= 0:
            self.selected_offset = pos; self.selection_start = pos
            self.selection_end = pos + len(self.search_bytes) - 1; self.last_search_pos = pos
            self.scroll_offset = max(0, pos // BYTES_PER_ROW - self.visible_rows // 2)
            self._ensure(); self._refresh(); self._update_status()
        else: messagebox.showinfo("Find","No more occurrences"); self.last_search_pos = -1

    def find_prev(self):
        if not self.search_bytes or not self.file_data: return
        pos = self.file_data.rfind(self.search_bytes, 0, self.last_search_pos)
        if pos >= 0:
            self.selected_offset = pos; self.selection_start = pos
            self.selection_end = pos + len(self.search_bytes) - 1; self.last_search_pos = pos
            self.scroll_offset = max(0, pos // BYTES_PER_ROW - self.visible_rows // 2)
            self._ensure(); self._refresh(); self._update_status()
        else: messagebox.showinfo("Find","No more occurrences")

    def replace_dialog(self):
        d = tk.Toplevel(self.root); d.title("Replace — AC's Hex Editor")
        d.geometry("460x250"); d.configure(bg=self.C_BG); d.transient(self.root); d.grab_set()
        tk.Label(d, text="Find (hex):", bg=self.C_BG, fg=self.C_TEXT, font=self.font).pack(pady=(12,3), padx=15, anchor=tk.W)
        fe = tk.Entry(d, bg="#111122", fg=self.C_TEXT, insertbackground=self.C_TEXT, font=self.font, relief=tk.FLAT)
        fe.pack(fill=tk.X, padx=15); fe.focus_set()
        tk.Label(d, text="Replace (hex):", bg=self.C_BG, fg=self.C_TEXT, font=self.font).pack(pady=(8,3), padx=15, anchor=tk.W)
        re_ = tk.Entry(d, bg="#111122", fg=self.C_TEXT, insertbackground=self.C_TEXT, font=self.font, relief=tk.FLAT)
        re_.pack(fill=tk.X, padx=15)
        def go():
            try:
                fd = bytes.fromhex(fe.get().strip().replace(' ',''))
                rd = bytes.fromhex(re_.get().strip().replace(' ',''))
                if len(fd)!=len(rd): messagebox.showerror("Error","Lengths must match",parent=d); return
                c=0; p=0
                while True:
                    i=self.file_data.find(fd,p)
                    if i<0: break
                    for j in range(len(fd)):
                        old=self.file_data[i+j]; self.file_data[i+j]=rd[j]
                        self._push_undo(i+j,old,rd[j]); self._mark_modified(i+j)
                    c+=1; p=i+len(fd)
                messagebox.showinfo("Replace",f"{c} replaced",parent=d)
                self._refresh(); self._update_status(); d.destroy()
            except Exception as ex: messagebox.showerror("Error",str(ex),parent=d)
        bf = tk.Frame(d, bg=self.C_BG); bf.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(bf, text="Replace All", command=go, bg=self.C_SEL_BG, fg=self.C_SEL_FG,
                  font=self.font, relief=tk.FLAT, padx=20).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text="Cancel", command=d.destroy, bg=self.C_HEADER_BG,
                  fg=self.C_TEXT, font=self.font, relief=tk.FLAT, padx=20).pack(side=tk.RIGHT, padx=4)

    # ────────── tools dialogs ──────────
    def _info_window(self, title, text):
        w = tk.Toplevel(self.root); w.title(f"{title} — AC's Hex Editor")
        w.geometry("580x420"); w.configure(bg=self.C_BG)
        t = tk.Text(w, bg=self.C_BG, fg=self.C_TEXT, font=self.font, insertbackground=self.C_TEXT,
                    relief=tk.FLAT, wrap=tk.WORD, selectbackground=self.C_SEL_BG)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        t.insert('1.0', text); t.config(state=tk.DISABLED)
        tk.Button(w, text="Close", command=w.destroy, bg=self.C_SEL_BG,
                  fg=self.C_SEL_FG, font=self.font, relief=tk.FLAT, padx=20).pack(pady=6)

    def show_file_info(self):
        fi = self.file_format_info or {}
        txt  = "══════ AC's Hex Editor — File Info ══════\n\n"
        txt += f"  Path      : {self.file_path or 'Untitled'}\n"
        txt += f"  Size      : {len(self.file_data):,} bytes  (0x{len(self.file_data):X})\n"
        txt += f"  Modified  : {len(self.modified_offsets)} bytes\n\n"
        txt += f"  Format    : {fi.get('name','—')}\n"
        txt += f"  System    : {fi.get('system','—')}\n"
        for k,v in fi.get('details',{}).items():
            txt += f"  {k:14s}: {v}\n"
        self._info_window("File Info", txt)

    def show_checksums(self):
        if not self.file_data: return
        md5 = hashlib.md5(self.file_data).hexdigest()
        sha1 = hashlib.sha1(self.file_data).hexdigest()
        sha256 = hashlib.sha256(self.file_data).hexdigest()
        crc = f"{0xFFFFFFFF & zlib.crc32(self.file_data):08X}"
        txt = "══════ Checksums ══════\n\n"
        txt += f"  MD5    : {md5}\n  SHA1   : {sha1}\n  SHA256 : {sha256}\n  CRC32  : {crc}\n"
        self._info_window("Checksums", txt)

    def show_atari_info(self):
        txt = "══════ Atari Format Support ══════\n\n"
        txt += "  .a78  — Atari 7800 ROM\n  .atr  — Atari 8-bit Disk Image\n"
        txt += "  .car  — Atari 8-bit Cartridge\n  .xex  — Atari 8-bit Executable\n"
        txt += "  .rom  — Generic ROM\n  .bin  — Auto-detect\n\n"
        fi = self.file_format_info or {}
        if "Atari" in fi.get("system",""):
            txt += "Current file:\n"
            for k,v in fi.get('details',{}).items(): txt += f"  {k}: {v}\n"
        else: txt += "Current file is not an Atari format.\n"
        self._info_window("Atari Info", txt)

    def show_ps5_info(self):
        txt = "══════ PlayStation 5 Format Support ══════\n\n"
        txt += "  .elf   — PS5 ELF Executable\n  .self  — PS5 SELF Executable\n"
        txt += "  .sprx  — PS5 SPRX Module\n  .pkg   — PS5 Package\n"
        txt += "  .prc   — PS5 PRC File\n  .eboot — PS5 EBOOT\n\n"
        fi = self.file_format_info or {}
        if "PlayStation" in fi.get("system",""):
            txt += "Current file:\n"
            for k,v in fi.get('details',{}).items(): txt += f"  {k}: {v}\n"
        else: txt += "Current file is not a PS5 format.\n"
        self._info_window("PS5 Info", txt)

    # ────────── export ──────────
    def export_hex_dump(self):
        p = filedialog.asksaveasfilename(title="Export Hex Dump", defaultextension=".txt",
                                         filetypes=[("Text","*.txt")])
        if not p: return
        try:
            with open(p,'w') as f:
                for off in range(0, len(self.file_data), BYTES_PER_ROW):
                    chunk = self.file_data[off:off+BYTES_PER_ROW]
                    hx = ' '.join(f'{b:02X}' for b in chunk)
                    asc = ''.join(chr(b) if 0x20<=b<=0x7e else '.' for b in chunk)
                    f.write(f"{off:08X}  {hx:<48s}  |{asc}|\n")
            messagebox.showinfo("Export","Hex dump saved!")
        except Exception as ex: messagebox.showerror("Error",str(ex))

    def export_c(self):
        p = filedialog.asksaveasfilename(title="Export C", defaultextension=".c",
                                         filetypes=[("C","*.c"),("Header","*.h")])
        if not p: return
        try:
            vn = os.path.splitext(os.path.basename(p))[0].replace('-','_').replace(' ','_')
            with open(p,'w') as f:
                f.write(f"unsigned char {vn}[{len(self.file_data)}] = {{\n")
                for off in range(0, len(self.file_data), BYTES_PER_ROW):
                    chunk = self.file_data[off:off+BYTES_PER_ROW]
                    f.write("    " + ', '.join(f'0x{b:02X}' for b in chunk) + ',\n')
                f.write("};\n")
            messagebox.showinfo("Export","C array saved!")
        except Exception as ex: messagebox.showerror("Error",str(ex))

    def export_py(self):
        p = filedialog.asksaveasfilename(title="Export Python", defaultextension=".py",
                                         filetypes=[("Python","*.py")])
        if not p: return
        try:
            vn = os.path.splitext(os.path.basename(p))[0].replace('-','_').replace(' ','_')
            with open(p,'w') as f:
                f.write(f"{vn} = bytes([\n")
                for off in range(0, len(self.file_data), BYTES_PER_ROW):
                    chunk = self.file_data[off:off+BYTES_PER_ROW]
                    f.write("    " + ', '.join(f'0x{b:02X}' for b in chunk) + ',\n')
                f.write("])\n")
            messagebox.showinfo("Export","Python saved!")
        except Exception as ex: messagebox.showerror("Error",str(ex))

    # ────────── status bar ──────────
    def _update_status(self):
        if 0 <= self.selected_offset < len(self.file_data):
            v = self.file_data[self.selected_offset]
            ch = chr(v) if 0x20<=v<=0x7e else '.'
            self.st_off.config(text=f"Offset: 0x{self.selected_offset:08X} ({self.selected_offset})")
            self.st_val.config(text=f"Value: 0x{v:02X} ({v:3d}) '{ch}'")
        else:
            self.st_off.config(text="Offset: —"); self.st_val.config(text="Value: —")
        self.st_mode.config(text="HEX" if self.editing_hex else "ASCII")
        self.st_size.config(text=f"{len(self.file_data):,} bytes (0x{len(self.file_data):X})")
        self.st_mod.config(text=f"⚠ Modified: {len(self.modified_offsets)}" if self.modified_offsets else "")
        if self.selection_start>=0 and self.selection_end>=0 and self.selection_start!=self.selection_end:
            s,e=sorted((self.selection_start,self.selection_end))
            self.st_sel.config(text=f"Sel: {e-s+1} bytes")
        else:
            self.st_sel.config(text="")

    def _font_resize(self, d):
        self.font_size = max(8, min(24, self.font_size + d))
        self.font = (self.font_family, self.font_size)
        self.char_w = self._measure_char_width()
        self._refresh()


# ─── Entry Point ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.configure(bg="#080810")
    app = ACHexEditor(root)
    root.mainloop()
