import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as tb
from datetime import datetime
from PIL import Image, ImageTk
import threading
from tkinter import Menu
import numpy as np
import cv2
import time
import mss
import queue
from detect_block import BlockDetector
import extract_text
import hashlib
from collections import deque
import gc
import re
import csv
from openpyxl import Workbook
from difflib import SequenceMatcher

class ThreadSafeImage:
    def __init__(self):
        self._lock = threading.Lock()
        self._image = None
    
    def set(self, image):
        with self._lock:
            self._image = image
    
    def get(self):
        with self._lock:
            return self._image

class MainUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MAKCOLIK SCRAPER v1.0")
        self.root.geometry("1050x700")
        self.root.minsize(1050, 700)

        self.current_id = 1
        self.current_team_names = ""
        self.hash_values = set()

        self.mss_sct = None
        self.roi_preview_running = False
        self.preview_thread = None
        self.image_queue = queue.Queue(maxsize=2)
        self.result_image_queue = queue.Queue(maxsize=2)
        
        self.original_photo = None
        self.detected_photo = None
        self.original_canvas_image = None
        self.detected_canvas_image = None
        
        self.roi_monitor = None
        self.roi_coordinates = None
        self.logo_coordinates = None
        self.team_coordinates = None

        self.scroll_detection_running = False
        self.scroll_thread = None
        self.prev_frame = None
        self.current_scroll_state = "Unknown"
        self.scroll_threshold = 5000
        self.scroll_text_id = None
        
        self.block_detection_thread = None
        self.frame_processed = False
        self.block_detection_lock = threading.Lock()
        self.ocr_lock = threading.Lock()
        self.ui_lock = threading.Lock()

        self.logo = None
        self.logo_monitor = None
        self.logo_hist = None
        
        self.detector = None
        
        self.safe_original_image = ThreadSafeImage()
        self.safe_detected_image = ThreadSafeImage()
        
        tb.Style("darkly")
        
        self.is_running = False
        self.is_paused = False
        self.roi_count = 0
        self.data_counter = 0

        self.selecting_roi = False
        self.current_selection_type = None

        self.original_image = None
        self.detected_image = None

        self.orphan_blocks = deque(maxlen=2)
        
        self.api_key = tk.StringVar()
        self.scroll_value = tk.IntVar(value=5000)
        self.date_time = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.team_name = tk.StringVar()
        self.status_text = tk.StringVar(value="Status: 0/3 ROI selected, ready to configure.")
        
        self._shutdown = False
        
        self.setup_ui()
        self.update_preview_images()
        self.update_result_images_from_queue()
        
    def setup_ui(self):
        self.root.grid_rowconfigure(0, weight=4)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        self.setup_left_panel()
        self.setup_right_panel()
        self.setup_bottom_panel()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_left_panel(self):
        left_frame = ttk.Frame(self.root)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=0)
        left_frame.grid_columnconfigure(0, weight=1)
        
        self.setup_preview_section(left_frame)
        self.setup_control_section(left_frame)
        
    def setup_preview_section(self, parent):
        preview_container = ttk.Frame(parent)
        preview_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_columnconfigure(1, weight=1)
        preview_container.grid_rowconfigure(0, weight=1)
        
        original_frame = ttk.LabelFrame(preview_container, text="Original", padding=10)
        original_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        original_frame.grid_rowconfigure(0, weight=1)
        original_frame.grid_columnconfigure(0, weight=1)
        
        self.original_canvas = tk.Canvas(original_frame, bg="black", width=270, height=540)
        self.original_canvas.grid(row=0, column=0, sticky="nsew")
        
        self.original_canvas_image = self.original_canvas.create_image(135, 200, anchor="center")
        self.scroll_text_id = self.original_canvas.create_text(0, 0, 
                                                      text="", 
                                                      anchor="nw", 
                                                      fill="yellow",
                                                      font=("Arial", 10, "bold"))
        self.original_placeholder = self.original_canvas.create_text(135, 200, 
                                                                   text="ROI Preview\nWill Show Here", 
                                                                   fill="gray", 
                                                                   font=("Arial", 12),
                                                                   anchor="center")
        
        detected_frame = ttk.LabelFrame(preview_container, text="Detected", padding=10)
        detected_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        detected_frame.grid_rowconfigure(0, weight=1)
        detected_frame.grid_columnconfigure(0, weight=1)
        
        self.detected_canvas = tk.Canvas(detected_frame, bg="black", width=270, height=540)
        self.detected_canvas.grid(row=0, column=0, sticky="nsew")
        
        self.detected_canvas_image = self.detected_canvas.create_image(135, 200, anchor="center")
        
        self.detected_placeholder = self.detected_canvas.create_text(135, 200,
                                                                   text="Detected Results\nWill Show Here", 
                                                                   fill="gray",
                                                                   font=("Arial", 12),
                                                                   anchor="center")

    def setup_control_section(self, parent):
        control_container = ttk.Frame(parent)
        control_container.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        roi_frame = ttk.Frame(control_container)
        roi_frame.pack(fill="x", pady=(0, 8))
        
        ttk.Button(roi_frame, text="Select ROI", 
                  command=self.select_roi,
                  style="primary.TButton").pack(side="left", padx=2, fill="x", expand=True)
        
        ttk.Button(roi_frame, text="Select Logo", 
                  command=self.select_logo).pack(side="left", padx=2, fill="x", expand=True)
        
        ttk.Button(roi_frame, text="Team ROI", 
                  command=self.select_team_roi).pack(side="left", padx=2, fill="x", expand=True)
        
        api_frame = ttk.Frame(control_container)
        api_frame.pack(fill="x", pady=(0, 8))
        
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_key)
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.set_placeholder(self.api_entry, "API KEY = sk-proj-***")
        
        ttk.Button(api_frame, text="OK", 
                  command=self.submit_api_key,
                  width=5).pack(side="left")
        
        input_frame = ttk.Frame(control_container)
        input_frame.pack(fill="x", pady=(0, 8))
        
        self.datetime_entry = ttk.Entry(input_frame, 
                                       textvariable=self.date_time,
                                       font=("Arial", 9))
        self.datetime_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        style = ttk.Style()
        style.configure("Normal.TEntry", foreground="white", font=("Arial", 9))
        self.team_entry = ttk.Entry(input_frame,
                                   textvariable=self.team_name,
                                   font=("Arial", 9))
        self.team_entry.pack(side="left", fill="x", expand=True)
        self.team_entry.configure(style="Normal.TEntry")
        
        self.set_placeholder(self.team_entry, "Team Name")
        
        action_frame = ttk.Frame(control_container)
        action_frame.pack(fill="x", pady=(0, 8))
        
        self.scroll_spinbox = ttk.Spinbox(action_frame, 
                                         from_=1000, 
                                         to=30000, 
                                         increment=500,
                                         textvariable=self.scroll_value,
                                         width=10)
        self.scroll_spinbox.pack(side="left", padx=(0, 10))
        
        self.start_button = ttk.Button(action_frame, 
                                      text="Start", 
                                      command=self.toggle_start,
                                      style="success.TButton",
                                      width=15)
        self.start_button.pack(side="left", fill="x", expand=True)
        self.start_button.state(["disabled"])

        status_frame = ttk.LabelFrame(control_container, text="Status", padding=5)
        status_frame.pack(fill="x")
        
        self.status_label = ttk.Label(status_frame, 
                                     textvariable=self.status_text,
                                     font=("Arial", 9))
        self.status_label.pack(anchor="w")

    def update_config_status(self):
        config_count = sum([
            self.roi_coordinates is not None,
            self.logo_coordinates is not None,
            self.team_coordinates is not None
        ])

        status_text = f"ROIs: {config_count}/3 configured."
        color = "green" if config_count == 3 else "orange" if config_count == 2 else "red"

        self.status_text.set(status_text)

        if config_count == 3:
            self.start_button.state(["!disabled"])
            self.status_label.configure(foreground="green")
        else:
            self.start_button.state(["disabled"])
            self.status_label.configure(foreground=color)
    
    def setup_right_panel(self):
        right_frame = ttk.LabelFrame(self.root, text="Extracted Data", padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        columns = ("id", "header", "odds")
        
        self.tree = ttk.Treeview(right_frame, columns=columns, show="headings")
        
        self.tree.heading("id", text="ID")
        self.tree.heading("header", text="Header")
        self.tree.heading("odds", text="Odds")
        
        self.tree.column("id", width=10, anchor="center")
        self.tree.column("header", width=100, anchor="w")
        self.tree.column("odds", width=200, anchor="w")
        
        v_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(right_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        self.create_context_menu()
        self.add_placeholder_data()
    
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
            
    def delete_selected_row(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a row to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected row?"):
            for item in selected_items:
                self.tree.delete(item)
            messagebox.showinfo("Success", "Row deleted successfully")

    def clear_selected_row(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a row to clear")
            return
        
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear the selected row data?"):
            for item in selected_items:
                current_values = list(self.tree.item(item, 'values'))
                new_values = [current_values[0], "", ""]
                self.tree.item(item, values=new_values)
            messagebox.showinfo("Success", "Row cleared successfully")

    def add_new_row(self):
        self.data_counter += 1
        new_row = (str(self.data_counter), "", "")
        self.tree.insert("", "end", values=new_row)
        
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])
        
        messagebox.showinfo("Success", "New row added successfully")

    def clear_all_rows(self):
        if not self.tree.get_children():
            messagebox.showwarning("Warning", "Table is already empty")
            return
        
        if messagebox.askyesno("Confirm Clear All", 
                            "Are you sure you want to clear ALL rows?\nThis cannot be undone!"):
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            self.data_counter = 0
            self.current_id = 1
            self.hash_values.clear()
            messagebox.showinfo("Success", "All rows cleared successfully")

    def create_context_menu(self):
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Delete Row", command=self.delete_selected_row)
        self.context_menu.add_command(label="Clear Row", command=self.clear_selected_row)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Add New Row", command=self.add_new_row)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Clear All Rows", command=self.clear_all_rows)

    def setup_bottom_panel(self):
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        
        export_frame = ttk.Frame(bottom_frame)
        export_frame.pack(side="right")
        
        ttk.Button(export_frame, 
                  text="Export CSV", 
                  command=self.export_csv,
                  style="info.TButton").pack(side="left", padx=5)
        
        ttk.Button(export_frame, 
                  text="Export EXCEL", 
                  command=self.export_excel,
                  style="info.TButton").pack(side="left", padx=5)
    
    def set_placeholder(self, entry_widget, placeholder_text):
        entry_widget.insert(0, placeholder_text)
        entry_widget.configure(foreground='gray')
        
        def on_focus_in(event):
            if entry_widget.get() == placeholder_text:
                entry_widget.delete(0, tk.END)
                entry_widget.configure(foreground='white')
        
        def on_focus_out(event):
            if entry_widget.get() == '':
                entry_widget.insert(0, placeholder_text)
                entry_widget.configure(foreground='gray')
        
        entry_widget.bind('<FocusIn>', on_focus_in)
        entry_widget.bind('<FocusOut>', on_focus_out)
        
    def select_roi(self):
        self.roi_coordinates = self.create_roi_selector("Select Main ROI")
        if self.roi_coordinates and self.roi_coordinates['width'] > 0 and self.roi_coordinates['height'] > 0:
            self.roi_count += 1
            self.update_config_status()
            self.stop_roi_preview()       
            self.root.after(500, self.start_roi_preview)
        
    def select_logo(self):
        self.logo_coordinates = self.create_roi_selector("Select Logo Region")
        if self.logo_coordinates and self.logo_coordinates['width'] > 0 and self.logo_coordinates['height'] > 0:
            self.roi_count += 1
            
            coords = self.logo_coordinates
            self.logo_monitor = {
                "top": int(coords["y1"]),
                "left": int(coords["x1"]),
                "width": int(coords["x2"] - coords["x1"]),
                "height": int(coords["y2"] - coords["y1"])
            }
            
            try:
                with mss.mss() as sct:
                    sct_img = sct.grab(self.logo_monitor)
                    logo = np.array(sct_img)
                    self.logo = cv2.cvtColor(logo, cv2.COLOR_BGRA2BGR)
                    h, w = self.logo.shape[:2]
                    self.logo_hist = self.calculate_hist(self.logo)
                    self.detector = BlockDetector(min_area=20000, logo_hist=self.logo_hist, logo_size=(h, w))
            except Exception as e:
                print(f"Logo selection error: {e}")
                return

            self.update_config_status()
            status_text = self.status_text.get()
            self.status_text.set(status_text + " Logo selected.")
            self.frame_processed = False       
        
    def select_team_roi(self):
        self.team_coordinates = self.create_roi_selector("Select Team Region")
        if self.extract_team_names():
            self.roi_count += 1
            self.update_config_status()
        
    def extract_team_names(self):
        if not (self.team_coordinates and self.team_coordinates['width'] > 0 and self.team_coordinates['height'] > 0):
            return False
            
        coords = self.team_coordinates
        self.team_roi_monitor = {
            "top": int(coords["y1"]),
            "left": int(coords["x1"]),
            "width": int(coords["x2"] - coords["x1"]),
            "height": int(coords["y2"] - coords["y1"])
        }
        
        try:
            with mss.mss() as sct:
                sct_img = sct.grab(self.team_roi_monitor)
                team_name_image = np.array(sct_img)
                self.team_name_image = cv2.cvtColor(team_name_image, cv2.COLOR_BGRA2RGB)

                with self.ocr_lock:
                    texts, team_name = extract_text.extract_team_name(self.team_name_image)
                    if team_name and len(texts) >= 3:
                        team_name = f"{texts[0]} vs {texts[2]}"
                        if self.current_team_names != team_name:
                            self.team_name.set(team_name)
                            self.current_team_names = team_name
                            self.data_counter = 0
                            self.current_id = 1
                            self.hash_values.clear()
                            for item in self.tree.get_children():
                                self.tree.delete(item)
                            self.team_entry.configure(style="Normal.TEntry") 
                        return True
        except Exception as e:
            print(f"Team name extraction error: {e}")
        return False

    def create_roi_selector(self, title="Select Region"):
        roi = None
        
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.3)
        overlay.configure(bg="black")
        overlay.attributes("-topmost", True)
        
        canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        instruction = tk.Label(overlay, text=f"{title} - Drag to select, ESC to cancel", 
                            bg="yellow", fg="black", font=("Arial", 12))
        instruction.place(relx=0.5, rely=0.02, anchor="center")
        
        start_x = 0
        start_y = 0
        rect_id = None
        
        def on_mouse_down(event):
            nonlocal start_x, start_y, rect_id
            start_x = event.x
            start_y = event.y
            if rect_id:
                canvas.delete(rect_id)
            rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y, 
                                        outline="red", width=3, fill="")
        
        def on_mouse_drag(event):
            nonlocal rect_id
            if rect_id:
                canvas.coords(rect_id, start_x, start_y, event.x, event.y)
        
        def on_mouse_up(event):
            nonlocal roi
            if rect_id:
                coords = canvas.coords(rect_id)
                if len(coords) == 4:
                    x1, y1, x2, y2 = coords
                    left = min(x1, x2)
                    top = min(y1, y2)
                    right = max(x1, x2)
                    bottom = max(y1, y2)
                    
                    roi = {
                        "left": int(left),
                        "top": int(top),
                        "width": int(right - left),
                        "height": int(bottom - top),
                        "x1": int(left),
                        "y1": int(top),
                        "x2": int(right),
                        "y2": int(bottom)
                    }
            overlay.destroy()
        
        def on_escape(event):
            overlay.destroy()
    
        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        overlay.bind("<Escape>", on_escape)
        
        overlay.focus_set()
        overlay.grab_set()
        
        self.root.wait_window(overlay)
        return roi
        
    def submit_api_key(self):
        api_value = self.api_key.get()
        if api_value and api_value != "API KEY = sk-proj-***":
            print(f"API Key submitted: {api_value}")
            messagebox.showinfo("API Key", f"API Key saved: {api_value[:10]}...")
        else:
            messagebox.showwarning("API Key", "Please enter a valid API key")
            
    def toggle_start(self):
        if not self.is_running:
            self.stop_scroll_detection()
            self.root.after(500, self.start_scroll_detection)
            self.is_running = True
            self.is_paused = False
            self.start_button.configure(text="Pause", style="warning.TButton")
            self.status_text.set("Status: Running - Scrolling detection...")
            self.extract_team_names()
            self.current_id = 1
            self.hash_values.clear()
            self.orphan_blocks.clear()
        
        elif self.is_running and not self.is_paused:
            self.stop_scroll_detection()
            self.is_paused = True
            self.start_button.configure(text="Resume", style="success.TButton")
            self.status_text.set("Status: Paused - Click Resume to continue...")
        
        elif self.is_running and self.is_paused:
            self.start_scroll_detection()
            self.is_paused = False
            self.start_button.configure(text="Pause", style="warning.TButton")
            self.status_text.set("Status: Running - Scrolling detection...")
            self.extract_team_names()
            self.current_id = 1
            self.hash_values.clear()
            
    def export_csv(self):
        columns = list(self.tree['columns'])
        if columns and columns[0].lower() in ("id", "index", "#0"):
            columns = columns[1:]
        data_rows = []
        for item_id in self.tree.get_children():
            row = self.tree.item(item_id)['values']
            if row:  
                data_rows.append(row[1:])
        transposed = list(zip(*data_rows))
        filename = self.current_team_names + "_" + self.date_time.get() + ".csv"
        safe_name = re.sub(r'[\\/:"*?<>|]+', '_', filename)
        with open(safe_name, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in zip(*transposed):
                writer.writerow(row)

        messagebox.showinfo("Export", f"Data has been exported to CSV file: {safe_name}")

    def export_excel(self):
        columns = list(self.tree['columns'])
        if columns and columns[0].lower() in ("id", "index", "#0"):
            columns = columns[1:]
        data_rows = []
        for item_id in self.tree.get_children():
            row = self.tree.item(item_id)['values']
            if row:
                data_rows.append(row[1:])
        transposed = list(zip(*data_rows))
        filename = self.current_team_names + "_" + self.date_time.get() + ".xlsx"
        safe_name = re.sub(r'[\\/:"*?<>|]+', '_', filename)

        wb = Workbook()
        ws = wb.active
        ws.append(columns)
        for row in zip(*transposed):
            ws.append(row)

        wb.save(safe_name)
        messagebox.showinfo("Export", f"Data has been exported to Excel file: {safe_name}")
        
    def on_double_click(self, event):
        selection = self.tree.selection()
        if not selection:
            return
            
        item = selection[0]
        column = self.tree.identify_column(event.x)
        
        col_index = int(column.replace('#', '')) - 1
        values = self.tree.item(item, 'values')
        self.edit_cell(item, col_index, values)
        
    def edit_cell(self, item, col_index, values):
        edit_window = tk.Toplevel(self.root)
        edit_window.title("Edit Cell")
        edit_window.geometry("400x300")
        
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        self.root.update_idletasks()
        x = (self.root.winfo_x() + (self.root.winfo_width() // 2)) - 200
        y = (self.root.winfo_y() + (self.root.winfo_height() // 2)) - 150
        edit_window.geometry(f"+{x}+{y}")
        
        columns = ("id", "header", "odds")
        col_name = columns[col_index]
        
        ttk.Label(edit_window, text=f"Edit {col_name}:").pack(pady=5)
        
        text_widget = tk.Text(edit_window, width=40, height=10, wrap=tk.WORD)
        text_widget.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        
        text_widget.insert("1.0", values[col_index])
        text_widget.focus()
        text_widget.tag_add("sel", "1.0", "end")
        
        button_frame = ttk.Frame(edit_window)
        button_frame.pack(pady=10)
        
        def save_edit():
            new_value = text_widget.get("1.0", "end-1c")
            new_values = list(values)
            new_values[col_index] = new_value
            self.tree.item(item, values=new_values)
            edit_window.destroy()
        
        ttk.Button(button_frame, text="Save", command=save_edit, 
                style="success.TButton").pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=edit_window.destroy,
                style="danger.TButton").pack(side="left", padx=5)
        
        def on_ctrl_enter(event):
            save_edit()
            return "break"
        
        def on_escape(event):
            edit_window.destroy()
            return "break"
        
        text_widget.bind("<Control-Return>", on_ctrl_enter)
        text_widget.bind("<Command-Return>", on_ctrl_enter)
        edit_window.bind("<Escape>", on_escape)
        
        instruction_frame = ttk.Frame(edit_window)
        instruction_frame.pack(pady=5)
        
        ttk.Label(instruction_frame, 
                text="Ctrl+Enter: Save | Esc: Cancel",
                font=("Arial", 9),
                foreground="gray").pack()
        
    def add_placeholder_data(self):
        sample_data = []
        for data in sample_data:
            self.tree.insert("", "end", values=data)
            self.data_counter += 1
            
    def add_new_data(self):
        self.data_counter += 1
        new_data = (
            str(self.data_counter),
            "extracted_data_here",
            "header_here"
        )
        self.tree.insert("", "end", values=new_data)
        
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    def start_roi_preview(self):
        if not self.roi_coordinates or self.roi_preview_running:
            return

        coords = self.roi_coordinates
        self.roi_monitor = {
            "top": int(coords["y1"]),
            "left": int(coords["x1"]),
            "width": int(coords["x2"] - coords["x1"]),
            "height": int(coords["y2"] - coords["y1"])
        }

        if hasattr(self, 'original_placeholder') and self.original_placeholder:
            self.original_canvas.delete(self.original_placeholder)
            self.original_placeholder = None

        self.roi_preview_running = True
        self.preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self.preview_thread.start()

    def _preview_loop(self):
        try:
            with mss.mss() as sct:
                while self.roi_preview_running and not self._shutdown:
                    try:
                        if not self.roi_monitor:
                            break
                            
                        sct_img = sct.grab(self.roi_monitor)
                        frame = np.array(sct_img)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                        
                        pil_img = Image.fromarray(frame)
                        
                        canvas_width = 270
                        canvas_height = 540
                        
                        img_width, img_height = pil_img.size
                        aspect_ratio = img_width / img_height
                        
                        if aspect_ratio > (canvas_width / canvas_height):
                            new_width = canvas_width
                            new_height = int(canvas_width / aspect_ratio)
                        else:
                            new_height = canvas_height
                            new_width = int(canvas_height * aspect_ratio)
                        
                        pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        
                        try:
                            self.image_queue.put_nowait(pil_img)
                        except queue.Full:
                            try:
                                self.image_queue.get_nowait()
                                self.image_queue.put_nowait(pil_img)
                            except queue.Empty:
                                pass
                        
                        time.sleep(1.0 / 15)
                        
                    except Exception as e:
                        print(f"Capture error: {e}")
                        time.sleep(0.1)
                        
        except Exception as e:
            print(f"Capture thread error: {e}")

    def update_preview_images(self):
        if self._shutdown:
            return
            
        try:
            images_to_process = []
            while True:
                try:
                    pil_img = self.image_queue.get_nowait()
                    images_to_process.append(pil_img)
                    
                except queue.Empty:
                    break
            
            if images_to_process:
                pil_img = images_to_process[-1] 
                
                photo = ImageTk.PhotoImage(pil_img)
                self.original_photo = photo
                
                if self.original_canvas_image and self.original_canvas.winfo_exists():
                    self.original_canvas.itemconfig(self.original_canvas_image, image=photo)
                    
        except Exception as e:
            print(f"Preview update error: {e}")
        
        if self.root.winfo_exists() and not self._shutdown:
            self.root.after(100, self.update_preview_images)
    
    def stop_roi_preview(self):
        if self.roi_preview_running:
            self.roi_preview_running = False
            
            if self.preview_thread and self.preview_thread.is_alive():
                self.preview_thread.join(timeout=1.0)
            
            while not self.image_queue.empty():
                try:
                    self.image_queue.get_nowait()
                except queue.Empty:
                    break
    
    def get_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def check_processed(self, hash_value):
        return hash_value in self.hash_values
    
    def calculate_hist(self, logo):
        try:
            logo_hsv = cv2.cvtColor(logo, cv2.COLOR_BGR2HSV)
            logo_hist = cv2.calcHist([logo_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
            logo_hist = cv2.normalize(logo_hist, logo_hist, 0, 1, cv2.NORM_MINMAX)
            return logo_hist
        except Exception as e:
            print(f"Histogram calculation error: {e}")
            return None
    
    def start_scroll_detection(self):
        if not self.roi_coordinates or self.scroll_detection_running:
            return
            
        self.scroll_detection_running = True
        self.scroll_thread = threading.Thread(target=self._scroll_detection_loop, daemon=True)
        self.scroll_thread.start()
    
    def detect_scroll_change(self, prev_frame, curr_frame):
        threshold = self.scroll_value.get()
        try:
            if prev_frame.shape[2] == 4:
                prev_frame = cv2.cvtColor(prev_frame, cv2.COLOR_BGRA2BGR)
            if curr_frame.shape[2] == 4:
                curr_frame = cv2.cvtColor(curr_frame, cv2.COLOR_BGRA2BGR)
            
            diff = cv2.absdiff(prev_frame, curr_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            non_zero_count = cv2.countNonZero(gray_diff)
            
            is_scrolling = non_zero_count > threshold
            return is_scrolling, non_zero_count
            
        except Exception as e:
            print(f"Scroll detection error: {e}")
            return False, 0
    
    def _scroll_detection_loop(self):
        try:
            with mss.mss() as sct:
                self.prev_frame = None
                
                while self.scroll_detection_running and not self._shutdown:
                    try:
                        if not self.roi_monitor:
                            break
                            
                        sct_img = sct.grab(self.roi_monitor)
                        curr_frame = np.array(sct_img)
                        
                        if self.prev_frame is not None:
                            is_scrolling, diff_count = self.detect_scroll_change(
                                self.prev_frame, curr_frame
                            )
                            
                            new_status = "Scrolling" if is_scrolling else "Captured"

                            if self.current_scroll_state != new_status:
                                self.current_scroll_state = new_status
                                text_color = "orange" if new_status == "Scrolling" else "lime"
                                
                                self.root.after(0, lambda s=new_status, c=text_color: 
                                            self.update_scroll_canvas_text(s, c))
                            
                            if is_scrolling:
                                self.frame_processed = False
                            else:
                                if not self.frame_processed and self.logo is not None and self.logo_hist is not None:
                                    self._trigger_block_detection(curr_frame.copy())
                                    self.frame_processed = True

                        self.prev_frame = curr_frame.copy()
                        time.sleep(0.1)
                        
                    except Exception as e:
                        time.sleep(0.1)
                        
        except Exception as e:
            print(f"Scroll detection thread error: {e}")

    def _trigger_block_detection(self, frame):
        with self.block_detection_lock:
            if self.block_detection_thread is None or not self.block_detection_thread.is_alive():
                self.block_detection_thread = threading.Thread(
                    target=self._detect_and_show_result, args=(frame.copy(),), daemon=True
                )
                self.block_detection_thread.start()

    def _detect_and_show_result(self, frame):
        try:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            if frame_bgr is not None and self.logo is not None and self.logo_hist is not None and self.detector is not None:
                blocks, headers, original_image = self.detector.detect_rectangles(frame_bgr)
                top_10_rectangles = self.detector.get_top_n(blocks, 10)
                
                height = 0
                if len(top_10_rectangles) >= 1:
                    x, y, w, height = top_10_rectangles[0]['coordinates']

                result_image, detected_blocks = self.detector.visualize_results(original_image, top_10_rectangles, headers)

                try:
                    self.result_image_queue.put_nowait(result_image)
                except queue.Full:
                    try:
                        self.result_image_queue.get_nowait()
                        self.result_image_queue.put_nowait(result_image)
                    except queue.Empty:
                        pass
                
                self.root.after(50, self.extract_team_names)
                
                self._process_pairing(original_image, headers, detected_blocks, height)

        except Exception as e:
            print(f"Block detection error: {e}")
            import traceback
            traceback.print_exc() 

    def update_result_images_from_queue(self):
        if self._shutdown:
            return
            
        try:
            result_image = None
            try:
                result_image = self.result_image_queue.get_nowait()
            except queue.Empty:
                pass
                
            if result_image is not None:
                rgb_frame = cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_frame)

                canvas_width = 270
                canvas_height = 540
                
                img_width, img_height = pil_image.size
                aspect_ratio = img_width / img_height
                
                if aspect_ratio > (canvas_width / canvas_height):
                    new_width = canvas_width
                    new_height = int(canvas_width / aspect_ratio)
                else:
                    new_height = canvas_height
                    new_width = int(canvas_height * aspect_ratio)
                
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                detected_photo = ImageTk.PhotoImage(pil_image)
                
                if hasattr(self, 'detected_placeholder') and self.detected_placeholder:
                    self.detected_canvas.delete(self.detected_placeholder)
                    self.detected_placeholder = None
                
                self.detected_canvas.itemconfig(self.detected_canvas_image, image=detected_photo)
                self.detected_photo = detected_photo 
                
        except Exception as e:
            print(f"Result image update error: {e}")
        
        if self.root.winfo_exists() and not self._shutdown:
            self.root.after(50, self.update_result_images_from_queue)

    def _crop_image(self, image, region):
        if image is None or image.size == 0:
            return None
            
        x, y, w, h = region['coordinates']
        h_img, w_img = image.shape[:2]
        
        x = max(0, min(x, w_img - 1))
        y = max(0, min(y, h_img - 1))
        w = max(1, min(w, w_img - x))
        h = max(1, min(h, h_img - y))
        
        return image[y:y+h, x:x+w]
    
    def normalize_text(self, text):
        if not text:
            return ""
        text = text.upper()
        text = re.sub(r'\s+', '', text)
        return text
    
    def _preprocess_odds_block_image(self, odds_block_image):
        if odds_block_image is None or odds_block_image.size == 0:
            return None
            
        try:
            gray = cv2.cvtColor(odds_block_image, cv2.COLOR_BGR2GRAY)
            scale_factor = 2
            height, width = gray.shape[:2]
            image_resized = cv2.resize(gray, (width*scale_factor, height*scale_factor), interpolation=cv2.INTER_CUBIC)
            kernel = np.array([[0, -1,  0],
                               [-1,  5, -1],
                               [0, -1,  0]])
            sharpened = cv2.filter2D(image_resized, -1, kernel)
            return sharpened
        except Exception as e:
            print(f"Preprocessing error: {e}")
            return odds_block_image

    def _get_block_odds_text(self, original_image, block):
        x, y, w, h = block['coordinates']
                
        block_image = self._crop_image(original_image, block)
        if block_image is None or block_image.size == 0:
            return ""
            
        odds_blocks = self.detector.detect_odds_blocks(block_image) if self.detector else []

        text_concat = ""
        odds = ""
        count = 0
        num_odds_blocks = len(odds_blocks)
        
        for odds_block in odds_blocks:
            odds_block_image = self._crop_image(block_image, odds_block)
            if odds_block_image is None or odds_block_image.size == 0:
                continue
                
            preprocessed = self._preprocess_odds_block_image(odds_block_image)
            if preprocessed is None:
                continue
                
            with self.ocr_lock:
                odds_texts = extract_text.get_odds_data(preprocessed)

            odds += f"({odds_texts[0]}, {odds_texts[1]})"

            count += 1
            if count < num_odds_blocks:
                odds += ", "
            
            if num_odds_blocks > 2:
                chunk_size = 2 if num_odds_blocks % 2 == 0 and num_odds_blocks % 6 != 0 else 3
                if count % chunk_size == 0:
                    odds += "\n"

            text_concat += odds_texts[1]

        return odds, text_concat

    def _get_header_text(self, original_image, region):
            try:
                x, y, w, h = region['coordinates']
                h_img, w_img = original_image.shape[:2]
                w = int(w * 0.5)

                x = max(0, min(x, w_img - 1))
                y = max(0, min(y, h_img - 1))
                w = max(1, min(w, w_img - x))
                h = max(1, min(h, h_img - y))

                crop_image = original_image[y:y+h, x:x+w]
                if crop_image.size == 0:
                    return ""
                    
                pre = self._preprocess_odds_block_image(crop_image)
                if pre is None:
                    return ""
                    
                text = extract_text.extract_block_data(pre)
                return text
            except Exception as e:
                print(f"Error during text extraction: {e}")
                return ""

    def _process_pairing(self, original_image, headers, blocks, block_height):
        num_headers = len(headers)
        num_blocks = len(blocks)

        if num_blocks >= 1:
            block_height = blocks[0]['coordinates'][3]
        else:
            return
        
        if 150 < block_height < 200:
            if num_blocks >= 1: # medium block
                b_text, b_odds = self._get_block_odds_text(original_image, blocks[0])
                h_text = "Unknown"
                if num_headers == 1:
                    h_text = self._get_header_text(original_image, headers[0])
                normalized = self.normalize_text(b_odds)
                hash_val = self.get_hash(normalized)

                if not self.check_processed(hash_val):
                    self.hash_values.add(hash_val)
                    self.insert_pair_to_treeview(h_text, b_text)
                    return
        
        if 400 < block_height:
            if num_blocks == 1: # large block
                block = blocks[0]
                bx, by, bw, bh = block['coordinates']
                h_text = "Unknown"
                if num_headers >= 1: 
                    header = headers[num_headers - 1]
                    hy = header['coordinates'][1]

                    if hy < by:
                        h_text = self._get_header_text(original_image, header)
                
                if by > 10 and by + bh > self.roi_coordinates['height'] - 10:
                    self.orphan_blocks.append(block)
                    print(f"first block has been added. {by}, {by + bh}, {self.roi_coordinates['height']}")
                    return
                elif by < 10 and by + bh < self.roi_coordinates['height'] - 10:
                    print(f"last block has been added. {len(self.orphan_blocks)} {by}, {by + bh}, {self.roi_coordinates['height']}")
                    num = len(self.orphan_blocks)
                    if num >= 1:

                        first_block = self.orphan_blocks[num - 1]
                        last_block = block
                        print(f"2 blocks are merged.")
                        str1, _ = self._get_block_odds_text(original_image, first_block)
                        str2, _ = self._get_block_odds_text(original_image, last_block)

                        combined_str = f"{str1}, {str2}"
                        normalized = self.normalize_2blocks_odds_string(combined_str)

                        self.insert_pair_to_treeview(h_text, combined_str)
                        self.orphan_blocks.clear()
                        return            
                        
        used_blocks = set()
        for header in headers:
            hy = header['coordinates'][1]
            for i, block in enumerate(blocks):
                if i in blocks:
                    continue
                    
                by = block['coordinates'][1]
                if by > hy:
                    h_text = self._get_header_text(original_image, header)
                    b_text, b_odds = self._get_block_odds_text(original_image, block)
                    normalized = self.normalize_text(b_odds)
                    hash_val = self.get_hash(normalized)
                    
                    if not self.check_processed(hash_val):
                        self.hash_values.add(hash_val)
                        self.insert_pair_to_treeview(h_text, b_text)
                    
                    used_blocks.add(i)
                    break
            
    def normalize_2blocks_odds_string(self, data): 
        if not data:
            return ""
        data_clean = re.sub(r'\s+', '', data)
        entries = data_clean.split('),(')
        entries[0] = entries[0].lstrip('(')
        entries[-1] = entries[-1].rstrip(')')
        seen_entries = []
        normalized = []
        
        for entry in entries:
            parts = entry.split(',', 1)
            if len(parts) != 2:
                continue
            header = parts[0].strip()
            odds_str = parts[1].strip()
            try:
                odds_val = float(odds_str)
            except ValueError:
                odds_val = odds_str
            
            is_duplicate = False
            for seen_header, seen_odds in seen_entries:
                header_similarity = SequenceMatcher(None, header, seen_header).ratio()
                if isinstance(odds_val, float) and isinstance(seen_odds, float):
                    odds_similar = abs(odds_val - seen_odds) < 0.01
                else:
                    odds_similar = odds_val == seen_odds
                if header_similarity > 0.9 and odds_similar:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_entries.append((header, odds_val))
                normalized.append(entry)
        
        result = ', '.join(f'({e})' for e in normalized)
        return result

    def insert_pair_to_treeview(self, header_text, odds_text):
        if not self._shutdown:
            self.root.after(0, lambda: self._insert_pair(header_text, odds_text))

    def _insert_pair(self, header_text, odds_text):
        try:
            self.tree.insert(
                "",
                "end",
                values=(self.current_id, header_text, odds_text)
            )
            self.current_id += 1
        except Exception as e:
            print(f"Insert pair error: {e}")

    def update_scroll_canvas_text(self, status, color):
        try:
            if self.scroll_text_id and self.original_canvas.winfo_exists() and not self._shutdown:
                self.original_canvas.itemconfig(self.scroll_text_id, 
                                            text=status, 
                                            fill=color)
        except Exception as e:
            print(f"Canvas text update error: {e}")

    def stop_scroll_detection(self):
        if self.scroll_detection_running:
            self.scroll_detection_running = False
            
            if self.scroll_thread and self.scroll_thread.is_alive():
                self.scroll_thread.join(timeout=1.0)
            
            self.current_scroll_state = "Unknown"

    def on_close(self):
        self._shutdown = True
        self.stop_roi_preview()
        self.stop_scroll_detection()
        
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.roi_preview_running = False
            self.scroll_detection_running = False
            
            gc.collect()
            self.root.after(200, self.root.destroy)
        else:
            self._shutdown = False
            if self.roi_coordinates and self.roi_coordinates['width'] > 0:
                self.root.after(300, self.start_roi_preview)
                self.root.after(300, self.start_scroll_detection)

    def filter_headers(self):
        

def main():
    print("Starting Makcolik Odds Scraper...")
    
    root = tb.Window()
    app = MainUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Application interrupted")
    except Exception as e:
        print(f"Application error: {e}")
    finally:
        print("Application closed")

if __name__ == "__main__":
    main()