from __future__ import annotations

import os
import re
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import xml.etree.ElementTree as ET

from engine.book_loader import load_book, resolve_image_path
from engine.validate import validate_book, build_link_index, asset_usage, export_dot, Issue

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


DEFAULT_BOOK_PATH = os.path.join(os.path.dirname(__file__), "examples", "sample_book.xml")


class AuthorTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LDW Author Tool (Book Inspector)")
        self.geometry("1200x780")

        self.book = None
        self.book_dir = ""

        # Keep XML tree so we can edit & save
        self._xml_tree: ET.ElementTree | None = None
        self._xml_root: ET.Element | None = None
        self._current_book_path: str | None = None

        self._build_menu()
        self._build_ui()

        # Auto-load sample if present
        if os.path.exists(DEFAULT_BOOK_PATH):
            self.load_book(DEFAULT_BOOK_PATH)

    # -----------------------
    # Menu / UI
    # -----------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        filem = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=filem)
        filem.add_command(label="Open book XML...", command=self.open_book_dialog)
        filem.add_separator()
        filem.add_command(label="Reload", command=self.reload_current)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)

    def _build_ui(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_outline = ttk.Frame(self.nb)
        self.tab_links = ttk.Frame(self.nb)
        self.tab_assets = ttk.Frame(self.nb)
        self.tab_search = ttk.Frame(self.nb)
        self.tab_validation = ttk.Frame(self.nb)

        self.nb.add(self.tab_outline, text="Outline")
        self.nb.add(self.tab_links, text="Links")
        self.nb.add(self.tab_assets, text="Assets")
        self.nb.add(self.tab_search, text="Search")
        self.nb.add(self.tab_validation, text="Validation")

        self._build_outline_tab()
        self._build_links_tab()
        self._build_assets_tab()
        self._build_search_tab()
        self._build_validation_tab()

    # -----------------------
    # Book load
    # -----------------------

    def open_book_dialog(self):
        path = filedialog.askopenfilename(
            title="Open book XML",
            filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")]
        )
        if path:
            self.load_book(path)

    def reload_current(self):
        if self._current_book_path:
            self.load_book(self._current_book_path)

    def load_book(self, xml_path: str):
        try:
            book = load_book(xml_path)
        except Exception as e:
            messagebox.showerror("Load error", str(e))
            return

        # Keep XML tree for editing
        try:
            self._xml_tree = ET.parse(xml_path)
            self._xml_root = self._xml_tree.getroot()
        except Exception as e:
            messagebox.showerror("XML parse error", str(e))
            return

        self._current_book_path = xml_path
        self.book = book
        self.book_dir = os.path.dirname(os.path.abspath(xml_path))
        self.title(f"LDW Author Tool — {book.title} (v{book.version})")

        self._refresh_all()

    def _refresh_all(self):
        self._refresh_outline()
        self._refresh_links()
        self._refresh_assets()
        self._refresh_search()
        self._refresh_validation()

    # -----------------------
    # Helpers: XML save / selections
    # -----------------------

    def _save_xml_with_backup(self) -> str:
        if not self._xml_tree or not self._current_book_path:
            raise RuntimeError("XML tree not loaded")
        xml_path = self._current_book_path
        bak_path = xml_path + ".bak"
        shutil.copy2(xml_path, bak_path)
        self._xml_tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        return bak_path

    def _get_outline_selected_pid(self) -> str | None:
        sel = self.out_list.curselection()
        if not sel:
            return None
        return self.out_list.get(sel[0])

    def _get_selected_asset_id(self) -> str | None:
        sel = self.assets_tree.selection()
        if not sel:
            return None
        values = self.assets_tree.item(sel[0], "values")
        if not values:
            return None
        return str(values[0])

    def _find_paragraph_node(self, pid: str) -> ET.Element | None:
        if not self._xml_root:
            return None
        return self._xml_root.find(f".//paragraph[@id='{pid}']")

    def _ensure_assets_elem(self) -> ET.Element:
        if not self._xml_root:
            raise RuntimeError("XML root not loaded")

        assets_elem = self._xml_root.find("assets")
        if assets_elem is None:
            assets_elem = ET.SubElement(self._xml_root, "assets")
            # keep basePath consistent with loaded book
            if self.book and self.book.assets.base_path:
                assets_elem.set("basePath", self.book.assets.base_path)
        return assets_elem

    # -----------------------
    # Outline tab
    # -----------------------

    def _build_outline_tab(self):
        root = self.tab_outline
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Filter:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.out_filter = tk.StringVar(value="")
        ent = ttk.Entry(root, textvariable=self.out_filter)
        ent.grid(row=0, column=0, sticky="ew", padx=(60, 8), pady=6)
        ent.bind("<KeyRelease>", lambda _e: self._refresh_outline())

        self.out_list = tk.Listbox(root)
        self.out_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.out_list.bind("<<ListboxSelect>>", lambda _e: self._outline_select())

        right = ttk.Frame(root)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=8, pady=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.out_title = ttk.Label(right, text="(no selection)", font=("Segoe UI", 12, "bold"))
        self.out_title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.out_preview = tk.Text(right, wrap="word")
        self.out_preview.grid(row=1, column=0, sticky="nsew")
        self.out_preview.configure(state="disabled")

        btns = ttk.Frame(right)
        btns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        btns.columnconfigure(0, weight=1)

        ttk.Button(btns, text="Copy ID", command=self._copy_selected_id).grid(row=0, column=0, sticky="w")
        ttk.Button(btns, text="Assign Image (import)...", command=self.assign_image_to_selected_paragraph).grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )

    def _refresh_outline(self):
        self.out_list.delete(0, "end")
        if not self.book:
            return

        f = self.out_filter.get().strip().lower()
        ids = sorted(self.book.paragraphs.keys(), key=lambda x: str(x))

        for pid in ids:
            if f and f not in pid.lower():
                t = (self.book.paragraphs[pid].text or "").lower()
                if f not in t:
                    continue
            self.out_list.insert("end", pid)

    def _outline_select(self):
        pid = self._get_outline_selected_pid()
        if not pid or not self.book:
            return

        para = self.book.paragraphs[pid]
        self.out_title.configure(text=f"Paragraph {pid}")

        preview_lines = [para.text.strip(), "", "Choices:"]
        if para.choices:
            for c in para.choices:
                preview_lines.append(f"- {c.label}  ->  {c.target}")
        else:
            preview_lines.append("(none)")

        if para.image_ref:
            preview_lines += ["", f"Image ref: {para.image_ref}"]

        self.out_preview.configure(state="normal")
        self.out_preview.delete("1.0", "end")
        self.out_preview.insert("1.0", "\n".join(preview_lines).strip())
        self.out_preview.configure(state="disabled")

        self._select_links_pid(pid)

    def _copy_selected_id(self):
        pid = self._get_outline_selected_pid()
        if not pid:
            return
        self.clipboard_clear()
        self.clipboard_append(pid)

    # -----------------------
    # Image linking / importing
    # -----------------------

    def assign_image_to_selected_paragraph(self):
        """
        Import an image file, copy it to assets directory, create/update <assets><image .../></assets>,
        and link it to the selected paragraph via <image ref="..."/>.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._get_outline_selected_pid()
        if not pid:
            messagebox.showwarning("No selection", "Select a paragraph first.")
            return

        src = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return

        base_path = (self.book.assets.base_path or "").strip()
        dest_dir = os.path.join(self.book_dir, base_path)
        os.makedirs(dest_dir, exist_ok=True)

        ext = os.path.splitext(src)[1].lower() or ".png"
        safe_pid = re.sub(r"[^a-zA-Z0-9_-]+", "_", pid)
        candidate = f"p{safe_pid}{ext}"
        dest_path = os.path.join(dest_dir, candidate)

        n = 2
        while os.path.exists(dest_path):
            candidate = f"p{safe_pid}_{n}{ext}"
            dest_path = os.path.join(dest_dir, candidate)
            n += 1

        try:
            shutil.copy2(src, dest_path)
        except Exception as e:
            messagebox.showerror("Copy error", str(e))
            return

        asset_id = os.path.splitext(os.path.basename(dest_path))[0]  # p10, p10_2, ...
        rel_file = os.path.basename(dest_path)

        # Update in-memory
        self.book.assets.images[asset_id] = rel_file
        if pid in self.book.paragraphs:
            self.book.paragraphs[pid].image_ref = asset_id

        # Update XML assets
        assets_elem = self._ensure_assets_elem()
        if self.book.assets.base_path and not assets_elem.get("basePath"):
            assets_elem.set("basePath", self.book.assets.base_path)

        img_node = None
        for im in assets_elem.findall("image"):
            if im.get("id") == asset_id:
                img_node = im
                break
        if img_node is None:
            img_node = ET.SubElement(assets_elem, "image")
            img_node.set("id", asset_id)
        img_node.set("file", rel_file)

        # Link to paragraph in XML
        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Could not find paragraph id='{pid}' in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            img_elem = ET.SubElement(p_node, "image")
        img_elem.set("ref", asset_id)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self._refresh_outline()
        self._outline_select()
        self._refresh_assets()

        messagebox.showinfo(
            "Assigned",
            f"Image imported and linked.\n\n"
            f"Paragraph: {pid}\n"
            f"Asset id: {asset_id}\n"
            f"File: {dest_path}\n\n"
            f"Backup: {bak_path}"
        )

    # -----------------------
    # Links tab
    # -----------------------

    def _build_links_tab(self):
        root = self.tab_links
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Paragraph:").grid(row=0, column=0, sticky="w", padx=8, pady=6)

        self.links_pid = tk.StringVar(value="")
        self.links_combo = ttk.Combobox(root, textvariable=self.links_pid, state="readonly")
        self.links_combo.grid(row=0, column=0, sticky="ew", padx=(90, 8), pady=6)
        self.links_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_links_lists())

        export_bar = ttk.Frame(root)
        export_bar.grid(row=0, column=1, sticky="e", padx=8, pady=6)

        ttk.Button(export_bar, text="Export DOT...", command=self.export_dot_dialog).pack(side="right", padx=(0, 5))
        ttk.Button(export_bar, text="Export DOT + SVG", command=self.export_dot_svg_dialog).pack(side="right")

        pan = ttk.Frame(root)
        pan.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        pan.columnconfigure(0, weight=1)
        pan.columnconfigure(1, weight=1)
        pan.rowconfigure(1, weight=1)

        ttk.Label(pan, text="Outgoing").grid(row=0, column=0, sticky="w")
        ttk.Label(pan, text="Incoming").grid(row=0, column=1, sticky="w")

        self.outgoing_list = tk.Listbox(pan)
        self.incoming_list = tk.Listbox(pan)
        self.outgoing_list.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.incoming_list.grid(row=1, column=1, sticky="nsew")

    def _refresh_links(self):
        if not self.book:
            self.links_combo["values"] = []
            self.links_pid.set("")
            self.outgoing_list.delete(0, "end")
            self.incoming_list.delete(0, "end")
            return

        ids = sorted(self.book.paragraphs.keys(), key=lambda x: str(x))
        self.links_combo["values"] = ids

        if not self.links_pid.get():
            self.links_pid.set(self.book.start_paragraph)

        self._refresh_links_lists()

    def _select_links_pid(self, pid: str):
        if not self.book:
            return
        values = set(self.links_combo["values"])
        if pid in values:
            self.links_pid.set(pid)
            self._refresh_links_lists()

    def _refresh_links_lists(self):
        if not self.book:
            return

        pid = self.links_pid.get()
        outgoing, incoming = build_link_index(self.book)

        self.outgoing_list.delete(0, "end")
        self.incoming_list.delete(0, "end")

        for t in outgoing.get(pid, []):
            self.outgoing_list.insert("end", t)

        for s in incoming.get(pid, []):
            self.incoming_list.insert("end", s)

    # -----------------------
    # Assets tab
    # -----------------------

    def _build_assets_tab(self):
        root = self.tab_assets
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(2, weight=1)

        info = ttk.Label(root, text="Assets declared in <assets>. (Select an asset for preview. Use buttons to manage.)")
        info.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        btnbar = ttk.Frame(root)
        btnbar.grid(row=0, column=1, sticky="e", padx=8, pady=6)

        ttk.Button(btnbar, text="Add Asset...", command=self.add_asset_dialog).pack(side="right")
        ttk.Button(btnbar, text="Assign to selected paragraph", command=self.assign_selected_asset_to_selected_paragraph).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(btnbar, text="Remove link from selected paragraph", command=self.remove_image_link_from_selected_paragraph).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(btnbar, text="Delete selected asset...", command=self.delete_selected_asset_dialog).pack(
            side="right", padx=(6, 0)
        )

        cols = ("asset_id", "file", "exists", "used_by")
        self.assets_tree = ttk.Treeview(root, columns=cols, show="headings")
        for c in cols:
            self.assets_tree.heading(c, text=c)
            self.assets_tree.column(c, width=160 if c != "used_by" else 520, anchor="w")
        self.assets_tree.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.assets_tree.bind("<<TreeviewSelect>>", lambda _e: self._assets_preview_selected())

        self.assets_preview = ttk.Label(root, text="(Preview)")
        self.assets_preview.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 10))

        self._asset_photo = None
        self._asset_img_label = ttk.Label(root)
        self._asset_img_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 10))

    def _refresh_assets(self):
        self.assets_tree.delete(*self.assets_tree.get_children())
        self.assets_preview.configure(text="(Preview)")
        self._asset_photo = None
        self._asset_img_label.configure(image="", text="")

        if not self.book:
            self.assets_preview.configure(text="(No book loaded)")
            return

        if not self.book.assets.images:
            base = self.book.assets.base_path or "(empty)"
            self.assets_preview.configure(text=f"No assets declared yet. assets.basePath = {base}")
            return

        usage = asset_usage(self.book)

        for asset_id, rel_file in sorted(self.book.assets.images.items(), key=lambda kv: kv[0]):
            abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)
            exists = "YES" if os.path.exists(abs_path) else "NO"
            used_by = ", ".join(usage.get(asset_id, []))
            self.assets_tree.insert("", "end", values=(asset_id, rel_file, exists, used_by))

    def _assets_preview_selected(self):
        if not self.book:
            return
        asset_id = self._get_selected_asset_id()
        if not asset_id:
            return

        abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)
        self.assets_preview.configure(text=f"{asset_id} -> {abs_path}")

        if not PIL_AVAILABLE or not os.path.exists(abs_path):
            self._asset_img_label.configure(image="", text="(Install Pillow and ensure file exists to preview)")
            return

        img = Image.open(abs_path)
        img.thumbnail((650, 360))
        self._asset_photo = ImageTk.PhotoImage(img)
        self._asset_img_label.configure(image=self._asset_photo, text="")

    def add_asset_dialog(self):
        """
        Import an image into the assets directory and add <assets><image .../></assets>.
        Does NOT link it to a paragraph.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        src = filedialog.askopenfilename(
            title="Import an asset image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return

        base_path = (self.book.assets.base_path or "").strip()
        dest_dir = os.path.join(self.book_dir, base_path)
        os.makedirs(dest_dir, exist_ok=True)

        ext = os.path.splitext(src)[1].lower() or ".png"
        base_name = os.path.splitext(os.path.basename(src))[0]
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", base_name).strip("_") or "asset"

        candidate = f"{safe_name}{ext}"
        dest_path = os.path.join(dest_dir, candidate)

        n = 2
        while os.path.exists(dest_path):
            candidate = f"{safe_name}_{n}{ext}"
            dest_path = os.path.join(dest_dir, candidate)
            n += 1

        try:
            shutil.copy2(src, dest_path)
        except Exception as e:
            messagebox.showerror("Copy error", str(e))
            return

        asset_id = os.path.splitext(os.path.basename(dest_path))[0]
        rel_file = os.path.basename(dest_path)

        # Update in-memory
        self.book.assets.images[asset_id] = rel_file

        # Update XML
        assets_elem = self._ensure_assets_elem()
        if self.book.assets.base_path and not assets_elem.get("basePath"):
            assets_elem.set("basePath", self.book.assets.base_path)

        img_node = None
        for im in assets_elem.findall("image"):
            if im.get("id") == asset_id:
                img_node = im
                break
        if img_node is None:
            img_node = ET.SubElement(assets_elem, "image")
            img_node.set("id", asset_id)
        img_node.set("file", rel_file)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self._refresh_assets()
        messagebox.showinfo(
            "Asset added",
            f"Asset imported:\n{dest_path}\n\nAsset id: {asset_id}\nBackup: {bak_path}"
        )

    def assign_selected_asset_to_selected_paragraph(self):
        """
        Link an already-declared asset (selected in Assets tab) to the paragraph selected in Outline.
        Does NOT copy files; only writes <image ref="..."/> on the paragraph.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._get_outline_selected_pid()
        if not pid:
            messagebox.showwarning("No paragraph selected", "Select a paragraph in the Outline tab.")
            return

        asset_id = self._get_selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset in the Assets tab.")
            return

        if asset_id not in self.book.assets.images:
            messagebox.showerror("Asset error", f"Asset '{asset_id}' is not declared in the book.")
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            img_elem = ET.SubElement(p_node, "image")
        img_elem.set("ref", asset_id)

        # Update in-memory
        if pid in self.book.paragraphs:
            self.book.paragraphs[pid].image_ref = asset_id

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self._refresh_outline()
        self._outline_select()
        self._refresh_assets()

        messagebox.showinfo(
            "Assigned",
            f"Linked asset '{asset_id}' to paragraph {pid}.\nBackup: {bak_path}"
        )

    def remove_image_link_from_selected_paragraph(self):
        """
        Remove <image ref="..."/> from the paragraph selected in Outline.
        Does NOT delete the asset declaration nor the file.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._get_outline_selected_pid()
        if not pid:
            messagebox.showwarning("No paragraph selected", "Select a paragraph in the Outline tab.")
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            messagebox.showinfo("No image", f"Paragraph {pid} has no image linked.")
            return

        p_node.remove(img_elem)

        # Update in-memory
        if pid in self.book.paragraphs:
            self.book.paragraphs[pid].image_ref = None

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self._refresh_outline()
        self._outline_select()
        self._refresh_assets()

        messagebox.showinfo("Link removed", f"Image link removed from paragraph {pid}.\nBackup: {bak_path}")

    def delete_selected_asset_dialog(self):
        """
        Delete the selected asset declaration from <assets> and optionally delete the file.
        If the asset is used by one or more paragraphs, offers to unlink it everywhere first.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        asset_id = self._get_selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset in the Assets tab.")
            return

        if asset_id not in self.book.assets.images:
            messagebox.showerror("Asset error", f"Asset '{asset_id}' is not declared in the book.")
            return

        usage = asset_usage(self.book)
        used_by = usage.get(asset_id, [])

        # If used, ask to unlink everywhere
        if used_by:
            msg = (
                f"Asset '{asset_id}' is used by paragraphs:\n"
                f"{', '.join(used_by)}\n\n"
                f"To delete the asset, it must be unlinked. Unlink it from ALL these paragraphs now?"
            )
            if not messagebox.askyesno("Asset in use", msg):
                return

            # Unlink from every paragraph in XML + in-memory
            for pid in used_by:
                p_node = self._find_paragraph_node(pid)
                if p_node is None:
                    continue
                img_elem = p_node.find("image")
                # Only remove if it matches this asset
                if img_elem is not None and (img_elem.get("ref") == asset_id):
                    p_node.remove(img_elem)
                if pid in self.book.paragraphs and self.book.paragraphs[pid].image_ref == asset_id:
                    self.book.paragraphs[pid].image_ref = None

        # Remove declaration node from XML
        assets_elem = self._xml_root.find("assets")
        if assets_elem is not None:
            for im in list(assets_elem.findall("image")):
                if im.get("id") == asset_id:
                    assets_elem.remove(im)
                    break

        # Determine file path before removing from memory
        abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)

        # Remove from in-memory assets
        self.book.assets.images.pop(asset_id, None)

        # Save XML first (safer)
        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        # Ask about deleting the file
        delete_file = False
        if os.path.exists(abs_path):
            delete_file = messagebox.askyesno(
                "Delete file?",
                f"Asset declaration removed.\n\nDelete the file too?\n{abs_path}"
            )

        if delete_file:
            try:
                os.remove(abs_path)
            except Exception as e:
                messagebox.showwarning("File delete failed", f"Could not delete file:\n{abs_path}\n\n{e}")

        self._refresh_outline()
        self._outline_select()
        self._refresh_assets()

        messagebox.showinfo(
            "Asset deleted",
            f"Asset '{asset_id}' deleted.\nBackup: {bak_path}"
        )

    # -----------------------
    # Search tab
    # -----------------------

    def _build_search_tab(self):
        root = self.tab_search
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Query:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.search_q = tk.StringVar(value="")
        ent = ttk.Entry(root, textvariable=self.search_q)
        ent.grid(row=0, column=0, sticky="ew", padx=(70, 8), pady=6)
        ent.bind("<Return>", lambda _e: self._do_search())
        ttk.Button(root, text="Search", command=self._do_search).grid(row=0, column=1, sticky="w", padx=8, pady=6)

        self.search_results = tk.Listbox(root)
        self.search_results.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.search_results.bind("<<ListboxSelect>>", lambda _e: self._search_select())

        self.search_preview = tk.Text(root, wrap="word")
        self.search_preview.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)
        self.search_preview.configure(state="disabled")

    def _refresh_search(self):
        self.search_results.delete(0, "end")
        self.search_preview.configure(state="normal")
        self.search_preview.delete("1.0", "end")
        self.search_preview.configure(state="disabled")

    def _do_search(self):
        self.search_results.delete(0, "end")
        if not self.book:
            return

        q = self.search_q.get().strip().lower()
        if not q:
            return

        for pid, para in self.book.paragraphs.items():
            text = (para.text or "").lower()
            if q in text:
                self.search_results.insert("end", pid)

    def _search_select(self):
        if not self.book:
            return
        sel = self.search_results.curselection()
        if not sel:
            return
        pid = self.search_results.get(sel[0])
        para = self.book.paragraphs[pid]

        snippet = para.text.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200] + "\n...\n"

        self.search_preview.configure(state="normal")
        self.search_preview.delete("1.0", "end")
        self.search_preview.insert("1.0", f"Paragraph {pid}\n\n{snippet}")
        self.search_preview.configure(state="disabled")

        self._select_outline_pid(pid)
        self._select_links_pid(pid)

    def _select_outline_pid(self, pid: str):
        for i in range(self.out_list.size()):
            if self.out_list.get(i) == pid:
                self.out_list.selection_clear(0, "end")
                self.out_list.selection_set(i)
                self.out_list.see(i)
                self._outline_select()
                break

    # -----------------------
    # Validation tab
    # -----------------------

    def _build_validation_tab(self):
        root = self.tab_validation
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        ttk.Button(top, text="Run validation", command=self._refresh_validation).pack(side="left")
        self.validation_summary = ttk.Label(top, text="(no data)")
        self.validation_summary.pack(side="left", padx=12)

        cols = ("severity", "paragraph", "message")
        self.val_tree = ttk.Treeview(root, columns=cols, show="headings")
        for c in cols:
            self.val_tree.heading(c, text=c)
            self.val_tree.column(c, width=120 if c != "message" else 840, anchor="w")
        self.val_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.val_tree.bind("<<TreeviewSelect>>", lambda _e: self._validation_select())

    def _refresh_validation(self):
        self.val_tree.delete(*self.val_tree.get_children())
        if not self.book:
            self.validation_summary.configure(text="(no book loaded)")
            return

        issues = validate_book(self.book, self.book_dir)
        e = sum(1 for i in issues if i.severity == "ERROR")
        w = sum(1 for i in issues if i.severity == "WARNING")
        n = sum(1 for i in issues if i.severity == "INFO")
        self.validation_summary.configure(text=f"Errors: {e}   Warnings: {w}   Info: {n}")

        for iss in issues:
            self.val_tree.insert("", "end", values=(iss.severity, iss.paragraph_id or "", iss.message))

    def _validation_select(self):
        if not self.book:
            return
        sel = self.val_tree.selection()
        if not sel:
            return
        values = self.val_tree.item(sel[0], "values")
        pid = values[1]
        if pid and pid in self.book.paragraphs:
            self._select_outline_pid(pid)
            self._select_links_pid(pid)

    # -----------------------
    # DOT export
    # -----------------------

    def export_dot_dialog(self):
        if not self.book:
            messagebox.showwarning("No book", "Load a book first.")
            return

        default_name = f"{getattr(self.book, 'book_id', None) or 'book'}.dot"
        path = filedialog.asksaveasfilename(
            title="Export DOT",
            defaultextension=".dot",
            initialfile=default_name,
            filetypes=[("DOT files", "*.dot"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            export_dot(self.book, self.book_dir, path)
        except Exception as e:
            messagebox.showerror("Export error", str(e))
            return

        messagebox.showinfo("Exported", f"DOT exported to:\n{path}")

    def export_dot_svg_dialog(self):
        if not self.book:
            messagebox.showwarning("No book", "Load a book first.")
            return

        dot_path = shutil.which("dot")
        if not dot_path:
            candidates = [
                r"C:\Program Files\Graphviz\bin\dot.exe",
                r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
            ]
            for c in candidates:
                if os.path.exists(c):
                    dot_path = c
                    break

        if not dot_path:
            messagebox.showerror(
                "Graphviz not found",
                "Graphviz (dot) is not available in PATH.\n"
                "Install Graphviz or fix PATH, then restart VS Code/terminal."
            )
            return

        default_name = f"{getattr(self.book, 'book_id', None) or 'book'}"
        path = filedialog.asksaveasfilename(
            title="Export DOT + SVG",
            defaultextension=".svg",
            initialfile=default_name,
            filetypes=[("SVG files", "*.svg")]
        )
        if not path:
            return

        if not path.lower().endswith(".svg"):
            path += ".svg"
        dot_file = path[:-4] + ".dot"

        try:
            export_dot(self.book, self.book_dir, dot_file)
            subprocess.run([dot_path, "-Tsvg", dot_file, "-o", path], check=True)
        except Exception as e:
            messagebox.showerror("Export error", str(e))
            return

        messagebox.showinfo("Exported", f"SVG exported to:\n{path}")

        try:
            os.startfile(path)  # Windows
        except Exception:
            pass


def main():
    app = AuthorTool()
    app.mainloop()


if __name__ == "__main__":
    main()