import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as tb
from datetime import datetime
from PIL import Image, ImageTk, ImageGrab, ImageDraw
import pyautogui
import threading
from tkinter import scrolledtext
from tkinter import Menu
import cv2
import numpy as np
import time
from PIL import Image, ImageTk
import mss
import queue
from detect_block import BlockDetector
import extract_text
import hashlib
from collections import deque

class MainUI:
    def __init__(self, root):
        """Initialize the main application window"""
        self.root = root
        self.root.title("NESINE Odds Scraper v1.0")
        # Set window size to about half of 15.1 inch screen width (approx 900-950px wide)
        self.root.geometry("1050x700")
        self.root.minsize(1050, 700)
        # Queues to keep leftovers across calls
        self.header_queue = deque()
        self.block_queue  = deque()
        self.hash_values = []

        # Initialize MSS and preview variables
        self.mss_sct = None
        self.roi_preview_running = False
        self.preview_thread = None
        self.image_queue = queue.Queue(maxsize=2)  # Limit queue size to prevent memory buildup

        # Image references - keep strong references to prevent garbage collection
        self.original_photo = None
        self.detected_photo = None
        self.original_canvas_image = None
        self.detected_canvas_image = None
        
        # ROI coordinates
        self.roi_monitor = None  # dict: {'top','left','width','height'}
        self.roi_coordinates = None
        self.logo_coordinates = None
        self.team_coordinates = None

        # Scrolling detection variables
        self.scroll_detection_running = False
        self.scroll_thread = None
        self.prev_frame = None
        self.current_scroll_state = "Unknown"
        self.scroll_threshold = 5000  # Fixed scroll sensitivity
        self.scroll_text_id = None
        
        # Block detection thread variables
        self.block_detection_thread = None
        self.frame_processed = False
        self.block_detection_lock = threading.Lock()
        self.ocr_lock = threading.Lock()  # Add this line


        # Logo
        self.logo = None
        self.logo_monitor = None
        self.logo_hist = None
        
        # Apply dark theme
        tb.Style("darkly")
        
        # ========== State Variables ==========
        # These variables store the state of buttons and inputs
        self.is_running = False
        self.is_paused = False
        self.roi_count = 0
        self.data_counter = 0  # Counter for table ID

         # ========== ROI Selection Variables ==========
        self.selecting_roi = False
        self.current_selection_type = None  # 'roi', 'logo', or 'team'

        # ========== Image Variables ==========
        self.original_image = None
        self.detected_image = None
        
        # ========== UI Variables ==========
        # StringVar and IntVar are special tkinter variables that automatically update UI
        self.api_key = tk.StringVar()
        self.scroll_value = tk.IntVar(value=5000)  # Default scroll value
        self.date_time = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.team_name = tk.StringVar()  # New variable for team name
        self.status_text = tk.StringVar(value="Status: 0/3 ROI selected, ready to configure.")
        
        # Build the UI
        self.setup_ui()
        
        # Start the image update loop
        self.update_preview_images()
        
    def setup_ui(self):
        """Setup the main UI layout"""
        # Configure grid weights for responsive design
        # weight=1 means the row/column will expand when window is resized
        self.root.grid_rowconfigure(0, weight=4)  # Main content row (increased weight)
        self.root.grid_rowconfigure(1, weight=0)  # Export buttons row (fixed height)
        self.root.grid_columnconfigure(0, weight=1)  # Left column
        self.root.grid_columnconfigure(1, weight=1)  # Right column
        
        # Create all UI sections
        self.setup_left_panel()
        self.setup_right_panel()
        self.setup_bottom_panel()
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_left_panel(self):
        """Setup the left panel with previews and controls"""
        # Create main left frame
        left_frame = ttk.Frame(self.root)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        left_frame.grid_rowconfigure(0, weight=1)  # Preview row
        left_frame.grid_rowconfigure(1, weight=0)  # Controls row
        left_frame.grid_columnconfigure(0, weight=1)
        
        # ========== Preview Section ==========
        self.setup_preview_section(left_frame)
        
        # ========== Control Section ==========
        self.setup_control_section(left_frame)
        
    def setup_preview_section(self, parent):
        """Setup the preview section with two preview windows"""
        # Create preview container
        preview_container = ttk.Frame(parent)
        preview_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_columnconfigure(1, weight=1)
        preview_container.grid_rowconfigure(0, weight=1)
        
        # ========== Original Preview ==========
        # Frame with border and label
        original_frame = ttk.LabelFrame(preview_container, text="Original", padding=10)
        original_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        original_frame.grid_rowconfigure(0, weight=1)
        original_frame.grid_columnconfigure(0, weight=1)
        
        # Canvas for original preview (phone-like aspect ratio)
        self.original_canvas = tk.Canvas(original_frame, bg="black", width=270, height=540)
        self.original_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Create the image item once - this prevents flickering
        self.original_canvas_image = self.original_canvas.create_image(135, 200, anchor="center")
        self.scroll_text_id = self.original_canvas.create_text(0, 0, 
                                                      text="", 
                                                      anchor="nw", 
                                                      fill="yellow",
                                                      font=("Arial", 10, "bold"))
        # Placeholder text for original preview
        self.original_placeholder = self.original_canvas.create_text(135, 200, 
                                                                   text="ROI Preview\nWill Show Here", 
                                                                   fill="gray", 
                                                                   font=("Arial", 12),
                                                                   anchor="center")
        
        # ========== Detected Preview ==========
        # Frame with border and label
        detected_frame = ttk.LabelFrame(preview_container, text="Detected", padding=10)
        detected_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        detected_frame.grid_rowconfigure(0, weight=1)
        detected_frame.grid_columnconfigure(0, weight=1)
        
        # Canvas for detected preview
        self.detected_canvas = tk.Canvas(detected_frame, bg="black", width=270, height=540)
        self.detected_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Create the image item once
        self.detected_canvas_image = self.detected_canvas.create_image(135, 200, anchor="center")
        
        # Placeholder text for detected preview
        self.detected_placeholder = self.detected_canvas.create_text(135, 200,
                                                                   text="Detected Results\nWill Show Here", 
                                                                   fill="gray",
                                                                   font=("Arial", 12),
                                                                   anchor="center")

    def setup_control_section(self, parent):
        """Setup the control section with buttons and inputs"""
        # Create control container with fixed height
        control_container = ttk.Frame(parent)
        control_container.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        # ========== ROI Selection Buttons ==========
        # Create frame for ROI buttons
        roi_frame = ttk.Frame(control_container)
        roi_frame.pack(fill="x", pady=(0, 8))
        
        # Create three ROI buttons in a row
        ttk.Button(roi_frame, text="Select ROI", 
                  command=self.select_roi,
                  style="primary.TButton").pack(side="left", padx=2, fill="x", expand=True)
        
        ttk.Button(roi_frame, text="Select Logo", 
                  command=self.select_logo).pack(side="left", padx=2, fill="x", expand=True)
        
        ttk.Button(roi_frame, text="Team ROI", 
                  command=self.select_team_roi).pack(side="left", padx=2, fill="x", expand=True)
        
        # ========== API Key Input (No Label, Only Placeholder) ==========
        # Create frame for API key
        api_frame = ttk.Frame(control_container)
        api_frame.pack(fill="x", pady=(0, 8))
        
        # Entry widget for API key input with placeholder
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_key)
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Set placeholder text for API key
        self.set_placeholder(self.api_entry, "API KEY = sk-proj-***")
        
        # OK button for API key
        ttk.Button(api_frame, text="OK", 
                  command=self.submit_api_key,
                  width=5).pack(side="left")
        
        # ========== Date/Time and Team Name Inputs ==========
        # Create frame for date/time and team name
        input_frame = ttk.Frame(control_container)
        input_frame.pack(fill="x", pady=(0, 8))
        
        # Date/Time entry (editable) - left side
        self.datetime_entry = ttk.Entry(input_frame, 
                                       textvariable=self.date_time,
                                       font=("Arial", 9))
        self.datetime_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Team name entry - right side
        style = ttk.Style()
        style.configure("Normal.TEntry", foreground="white", font=("Arial", 9))
        self.team_entry = ttk.Entry(input_frame,
                                   textvariable=self.team_name,
                                   font=("Arial", 9))
        self.team_entry.pack(side="left", fill="x", expand=True)
        self.team_entry.configure(style="Normal.TEntry")
        
        # Set placeholder for team name
        self.set_placeholder(self.team_entry, "Team Name")
        
        # ========== Scroll Value and Start Button ==========
        # Create frame for scroll and start button
        action_frame = ttk.Frame(control_container)
        action_frame.pack(fill="x", pady=(0, 8))
        
        # Spinbox for scroll value (number input with step)
        self.scroll_spinbox = ttk.Spinbox(action_frame, 
                                         from_=1000, 
                                         to=30000, 
                                         increment=500,  # Step by 500
                                         textvariable=self.scroll_value,
                                         width=10)
        self.scroll_spinbox.pack(side="left", padx=(0, 10))
        
        # Start/Pause/Resume button with dynamic color
        self.start_button = ttk.Button(action_frame, 
                                      text="Start", 
                                      command=self.toggle_start,
                                      style="success.TButton",  # Green for Start
                                      width=15)
        self.start_button.pack(side="left", fill="x", expand=True)
        # Disable until config is ready
        self.start_button.state(["disabled"])

        # ========== Status Label ==========
        # Status label at the bottom of controls
        status_frame = ttk.LabelFrame(control_container, text="Status", padding=5)
        status_frame.pack(fill="x")
        
        self.status_label = ttk.Label(status_frame, 
                                     textvariable=self.status_text,
                                     font=("Arial", 9))
        self.status_label.pack(anchor="w")

    def update_config_status(self):
        """Update ROI/Config status and control Start button"""
        config_count = sum([
            self.roi_coordinates is not None,
            self.logo_coordinates is not None,
            self.team_coordinates is not None
        ])

        status_text = f"ROIs: {config_count}/3 configured."
        color = "green" if config_count == 3 else "orange" if config_count == 2 else "red"

        # Update label
        self.status_text.set(status_text)

        # Enable Start button only when all 3 are set
        if config_count == 3:
            self.start_button.state(["!disabled"])
            self.status_label.configure(foreground="green")
        else:
            self.start_button.state(["disabled"])
            self.status_label.configure(foreground=color)
    
    def setup_right_panel(self):
        """Setup the right panel with data table"""
        # Create main right frame
        right_frame = ttk.LabelFrame(self.root, text="Extracted Data", padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        # ========== Create Treeview Table ==========
        # Define columns for the table
        columns = ("id", "hash", "extracted_data", "header")
        
        # Create the treeview widget (table)
        self.tree = ttk.Treeview(right_frame, columns=columns, show="headings")
        
        # Configure column headings
        self.tree.heading("id", text="ID")
        self.tree.heading("hash", text="Hash")
        self.tree.heading("extracted_data", text="Extracted Data")
        self.tree.heading("header", text="Header")
        
        # Configure column widths (adjusted for smaller window)
        self.tree.column("id", width=30, anchor="center")
        self.tree.column("hash", width=50, anchor="center")
        self.tree.column("extracted_data", width=200, anchor="w")
        self.tree.column("header", width=100, anchor="w")
        
        # Create scrollbars for the table
        v_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(right_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid layout for table and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Bind double-click event for editing cells
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # Bind right-click for context menu
        self.tree.bind("<Button-3>", self.show_context_menu)  # Right-click
         # Create context menu
        self.create_context_menu()

        # Add some placeholder data for demonstration
        self.add_placeholder_data()
    
    def show_context_menu(self, event):
        """Show context menu on right-click"""
        # Select the item under cursor
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
            
    def delete_selected_row(self):
        """Delete the currently selected row"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a row to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected row?"):
            for item in selected_items:
                self.tree.delete(item)
            messagebox.showinfo("Success", "Row deleted successfully")

    def clear_selected_row(self):
        """Clear data from selected row (keep row structure)"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a row to clear")
            return
        
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear the selected row data?"):
            for item in selected_items:
                # Clear all cells except ID
                current_values = list(self.tree.item(item, 'values'))
                # Keep ID, clear other fields
                new_values = [current_values[0], "", "", ""]
                self.tree.item(item, values=new_values)
            messagebox.showinfo("Success", "Row cleared successfully")

    def add_new_row(self):
        """Add a new empty row to the table"""
        self.data_counter += 1
        new_row = (str(self.data_counter), "", "", "")
        self.tree.insert("", "end", values=new_row)
        
        # Scroll to the new row
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])
        
        messagebox.showinfo("Success", "New row added successfully")

    def clear_all_rows(self):
        """Clear all rows from the table"""
        if not self.tree.get_children():
            messagebox.showwarning("Warning", "Table is already empty")
            return
        
        if messagebox.askyesno("Confirm Clear All", 
                            "Are you sure you want to clear ALL rows?\nThis cannot be undone!"):
            # Delete all rows
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Reset counter
            self.data_counter = 0
            messagebox.showinfo("Success", "All rows cleared successfully")

    def create_context_menu(self):
        """Create right-click context menu for table"""
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Delete Row", command=self.delete_selected_row)
        self.context_menu.add_command(label="Clear Row", command=self.clear_selected_row)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Add New Row", command=self.add_new_row)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Clear All Rows", command=self.clear_all_rows)

    def setup_bottom_panel(self):
        """Setup the bottom panel with export buttons"""
        # Create bottom frame with fixed height
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        
        # Create export buttons frame
        export_frame = ttk.Frame(bottom_frame)
        export_frame.pack(side="right")
        
        # Export CSV button
        ttk.Button(export_frame, 
                  text="Export CSV", 
                  command=self.export_csv,
                  style="info.TButton").pack(side="left", padx=5)
        
        # Export Excel button
        ttk.Button(export_frame, 
                  text="Export EXCEL", 
                  command=self.export_excel,
                  style="info.TButton").pack(side="left", padx=5)
    
    def set_placeholder(self, entry_widget, placeholder_text):
        """Add placeholder text functionality to an entry widget"""
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
        
    # ========== Button Click Handlers ==========
    
    def select_roi(self):
        """Handle Select ROI button click"""
        self.roi_coordinates = self.create_roi_selector("Select Main ROI")
        if self.roi_coordinates and self.roi_coordinates['width'] != 0 and self.roi_coordinates['height'] != 0:
            self.roi_count += 1
            self.update_config_status()
        
    def select_logo(self):
        """Handle Select Logo button click"""
        self.logo_coordinates = self.create_roi_selector("Select Logo Region")
        if self.logo_coordinates and self.logo_coordinates['width'] != 0 and self.logo_coordinates['height'] != 0:
            self.roi_count += 1
            
            coords = self.logo_coordinates
            self.logo_monitor = {
                "top": int(coords["y1"]),
                "left": int(coords["x1"]),
                "width": int(coords["x2"] - coords["x1"]),
                "height": int(coords["y2"] - coords["y1"])
            }
            with mss.mss() as sct:
                # Capture ROI
                sct_img = sct.grab(self.logo_monitor)
                
                # Convert to numpy array and process
                logo = np.array(sct_img)
                
                # Convert BGRA -> RGB
                self.logo = cv2.cvtColor(logo, cv2.COLOR_BGRA2BGR)
                h, w = logo.shape[:2]

                self.logo_hist = self.calculate_hist(self.logo)

                # Initialize detector with logo hist & size
                self.detector = BlockDetector(min_area=20000, logo_hist=self.logo_hist, logo_size=(h, w))

            self.update_config_status()
            
            status_text = self.status_text.get()
            self.status_text.set(status_text + " " + "Logo has selected.")
            self.frame_processed = False       
        
    def select_team_roi(self):
        """Handle Team ROI button click"""
        self.team_coordinates = self.create_roi_selector("Select Team Region")
        if self.extract_team_names():
            self.roi_count += 1
            self.update_config_status()
        
    def extract_team_names(self):
        if self.team_coordinates  and self.team_coordinates['width'] != 0 and self.team_coordinates['height'] != 0:
            coords = self.team_coordinates
            self.team_roi_monitor = {
                "top": int(coords["y1"]),
                "left": int(coords["x1"]),
                "width": int(coords["x2"] - coords["x1"]),
                "height": int(coords["y2"] - coords["y1"])
            }
            team_name = ""
            with mss.mss() as sct:
                # Capture ROI
                sct_img = sct.grab(self.team_roi_monitor)
                
                # Convert to numpy array and process
                team_name_image = np.array(sct_img)
                
                # Convert BGRA -> RGB
                self.team_name_image = cv2.cvtColor(team_name_image, cv2.COLOR_BGRA2RGB)

                with self.ocr_lock:
                    texts, team_name = extract_text.extract_team_name(self.team_name_image)
                    if team_name and len(texts) == 3:  # check if not empty
                        # Later, when setting the real team name:
                        self.team_name.set(texts[0] + " vs " + texts[2])

                        print("aaaaaaaa")
                        self.team_entry.configure(style="Normal.TEntry") 
                        return True
                    else: return False

    def create_roi_selector(self, title="Select Region"):
        """Create ROI selection overlay with proper red outline"""
        roi = None
        
        # Create overlay window
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.3)
        overlay.configure(bg="black")
        overlay.attributes("-topmost", True)
        
        # Create canvas with cross cursor
        canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        # Instruction label
        instruction = tk.Label(overlay, text=f"{title} - Drag to select, ESC to cancel", 
                            bg="yellow", fg="black", font=("Arial", 12))
        instruction.place(relx=0.5, rely=0.02, anchor="center")
        
        # Initialize variables
        start_x = 0
        start_y = 0
        rect_id = None
        
        def on_mouse_down(event):
            nonlocal start_x, start_y, rect_id
            start_x = event.x
            start_y = event.y
            if rect_id:
                canvas.delete(rect_id)
            # Create rectangle with red outline
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
                    # Ensure positive width/height
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
    
        # Bind events
        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        overlay.bind("<Escape>", on_escape)
        
        # Focus and wait for the window
        overlay.focus_set()
        overlay.grab_set()
        
        self.root.wait_window(overlay)
        return roi
        
    def submit_api_key(self):
        """Handle API Key OK button click"""
        api_value = self.api_key.get()
        # Check if it's not the placeholder text
        if api_value and api_value != "API KEY = sk-proj-***":
            print(f"API Key submitted: {api_value}")
            messagebox.showinfo("API Key", f"API Key saved: {api_value[:10]}...")
        else:
            messagebox.showwarning("API Key", "Please enter a valid API key")
            
    def toggle_start(self):
        """Handle Start/Pause/Resume button click with color changes"""
        if not self.is_running:
            # Start the process - Green button
            self.stop_roi_preview()         # stop old preview if running
            self.stop_scroll_detection()
            # Give old thread time to stop, then start new preview
            self.root.after(500, lambda: self.start_roi_preview())
            self.root.after(500, lambda: self.start_scroll_detection())
            self.is_running = True
            self.is_paused = False
            self.start_button.configure(text="Pause", style="warning.TButton")  # Yellow for Pause
            self.status_text.set("Status: Running - Scrolling detection...")
            print("Started processing")
            self.extract_team_names()
        
        elif self.is_running and not self.is_paused:
            # Pause the process - Gray button
            self.stop_scroll_detection()
            self.is_paused = True
            self.start_button.configure(text="Resume", style="success.TButton")  # Green for Resume
            self.status_text.set("Status: Paused - Click Resume to continue...")
            print("Processing paused")
        
        elif self.is_running and self.is_paused:
            # Resume the process - Yellow button
            self.start_scroll_detection()
            self.is_paused = False
            self.start_button.configure(text="Pause", style="warning.TButton")  # Yellow for Pause
            self.status_text.set("Status: Running - Scrolling detection...")
            print("Processing resumed")
            self.extract_team_names()
            
        elif self.is_running and not self.is_paused:
            # Pause the process - Yellow button
            self.is_paused = True
            self.start_button.configure(text="Resume", style="info.TButton")  # Blue for Resume
            self.status_text.set("Status: Paused")
            print("Paused processing")
            
        elif self.is_running and self.is_paused:
            # Resume the process - Blue button back to Yellow
            self.is_paused = False
            self.start_button.configure(text="Pause", style="warning.TButton")  # Yellow for Pause
            self.status_text.set("Status: Resumed - Processing blocks...")
            print("Resumed processing")
            
    def export_csv(self):
        """Handle Export CSV button click"""
        print("Export to CSV clicked")
        messagebox.showinfo("Export", "Data would be exported to CSV file")
        
    def export_excel(self):
        """Handle Export Excel button click"""
        print("Export to Excel clicked")
        messagebox.showinfo("Export", "Data would be exported to Excel file")
        
    def on_double_click(self, event):
        """Handle double-click on table cell for editing"""
        # Get the clicked item
        selection = self.tree.selection()
        if not selection:
            return
            
        item = selection[0]
        column = self.tree.identify_column(event.x)
        
        # Get column index (remove the '#' from column string)
        col_index = int(column.replace('#', '')) - 1
        
        # Get current values
        values = self.tree.item(item, 'values')
        
        # Create edit dialog
        self.edit_cell(item, col_index, values)
        
    def edit_cell(self, item, col_index, values):
        """Create an edit dialog for table cell with multi-line support"""
        # Create a simple dialog for editing
        edit_window = tk.Toplevel(self.root)
        edit_window.title("Edit Cell")
        edit_window.geometry("400x300")  # Larger window for multi-line text
        
        # Center the edit window on screen
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # Position window in center of parent
        self.root.update_idletasks()
        x = (self.root.winfo_x() + (self.root.winfo_width() // 2)) - 200
        y = (self.root.winfo_y() + (self.root.winfo_height() // 2)) - 150
        edit_window.geometry(f"+{x}+{y}")
        
        # Get column name
        columns = ("id", "hash", "extracted_data", "header")
        col_name = columns[col_index]
        
        # Label
        ttk.Label(edit_window, text=f"Edit {col_name}:").pack(pady=5)
        
        # Use Text widget instead of Entry for multi-line support
        text_widget = tk.Text(edit_window, width=40, height=10, wrap=tk.WORD)
        text_widget.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        
        # Insert current value
        text_widget.insert("1.0", values[col_index])
        text_widget.focus()
        text_widget.tag_add("sel", "1.0", "end")  # Select all text
        
        # Create a frame for buttons
        button_frame = ttk.Frame(edit_window)
        button_frame.pack(pady=10)
        
        # Save function
        def save_edit():
            new_value = text_widget.get("1.0", "end-1c")  # Get all text without trailing newline
            new_values = list(values)
            new_values[col_index] = new_value
            self.tree.item(item, values=new_values)
            edit_window.destroy()
        
        # Buttons
        ttk.Button(button_frame, text="Save", command=save_edit, 
                style="success.TButton").pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=edit_window.destroy,
                style="danger.TButton").pack(side="left", padx=5)
        
        # Bind key events
        def on_ctrl_enter(event):
            save_edit()
            return "break"
        
        def on_escape(event):
            edit_window.destroy()
            return "break"
        
        # Key bindings
        text_widget.bind("<Control-Return>", on_ctrl_enter)  # Ctrl+Enter = save
        text_widget.bind("<Command-Return>", on_ctrl_enter)  # Cmd+Enter (for macOS)
        edit_window.bind("<Escape>", on_escape)
        
        # Add instructions
        instruction_frame = ttk.Frame(edit_window)
        instruction_frame.pack(pady=5)
        
        ttk.Label(instruction_frame, 
                text="Ctrl+Enter: Save | Esc: Cancel",
                font=("Arial", 9),
                foreground="gray").pack()
        
    def add_placeholder_data(self):
        """Add some placeholder data to the table for demonstration"""
        # Sample data to show how the table works
        sample_data = []
        
        for data in sample_data:
            self.tree.insert("", "end", values=data)
            self.data_counter += 1
            
    def add_new_data(self):
        """Add new data to the table (called when new block is detected)"""
        # This would be called when actual data is detected
        self.data_counter += 1
        new_data = (
            str(self.data_counter),
            "hash_example",
            "extracted_data_here",
            "header_here"
        )
        self.tree.insert("", "end", values=new_data)
        
        # Auto-scroll to the latest entry
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    # ========== ROI Preview Functions - Fixed for No Flickering ==========
    
    def start_roi_preview(self):
        """Start smooth ROI preview using mss in a background thread - Fixed version"""
        if not self.roi_coordinates:
            messagebox.showwarning("Warning", "Please select an ROI first")
            return

        if self.roi_preview_running:
            return
        
        # Initialize monitor coordinates
        coords = self.roi_coordinates
        self.roi_monitor = {
            "top": int(coords["y1"]),
            "left": int(coords["x1"]),
            "width": int(coords["x2"] - coords["x1"]),
            "height": int(coords["y2"] - coords["y1"])
        }

        # Remove placeholder text if it exists
        if hasattr(self, 'original_placeholder') and self.original_placeholder:
            self.original_canvas.delete(self.original_placeholder)
            self.original_placeholder = None

        # Start the preview
        self.roi_preview_running = True
        
        self.preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self.preview_thread.start()

    def _preview_loop(self):
        """Background thread capture loop - optimized to prevent flickering"""
        try:
            with mss.mss() as sct:
                while self.roi_preview_running:
                    try:
                        # Capture ROI
                        sct_img = sct.grab(self.roi_monitor)
                        
                        # Convert to numpy array and process
                        frame = np.array(sct_img)
                        
                        # Convert BGRA -> RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                        
                        # Convert to PIL Image
                        pil_img = Image.fromarray(frame)
                        
                        # Resize to fit canvas (maintain aspect ratio)
                        canvas_width = 270
                        canvas_height = 540
                        
                        # Calculate aspect ratio preserving resize
                        img_width, img_height = pil_img.size
                        aspect_ratio = img_width / img_height
                        
                        if aspect_ratio > (canvas_width / canvas_height):
                            # Image is wider - fit to width
                            new_width = canvas_width
                            new_height = int(canvas_width / aspect_ratio)
                        else:
                            # Image is taller - fit to height
                            new_height = canvas_height
                            new_width = int(canvas_height * aspect_ratio)
                        
                        # Resize with high quality
                        pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        
                        # Add to queue (non-blocking)
                        try:
                            self.image_queue.put_nowait(pil_img)
                        except queue.Full:
                            # If queue is full, remove old image and add new one
                            try:
                                self.image_queue.get_nowait()
                                self.image_queue.put_nowait(pil_img)
                            except queue.Empty:
                                pass
                        
                        # Control frame rate (15 FPS)
                        time.sleep(1.0 / 15)
                        
                    except Exception as e:
                        print(f"Capture error: {e}")
                        time.sleep(0.1)  # Brief pause on error
                        
        except Exception as e:
            print(f"Capture thread error: {e}")
        finally:
            print("Capture thread stopped")

    def update_preview_images(self):
        """Update preview images from queue - runs on main thread"""
        try:
            # Check for new images in queue
            while True:
                try:
                    pil_img = self.image_queue.get_nowait()
                    
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(pil_img)
                    
                    # Keep strong reference to prevent garbage collection
                    self.original_photo = photo
                    
                    # Update canvas image
                    if self.original_canvas_image and self.original_canvas.winfo_exists():
                        self.original_canvas.itemconfig(self.original_canvas_image, image=photo)
                    
                except queue.Empty:
                    break
                    
        except Exception as e:
            print(f"Preview update error: {e}")
        
        # Schedule next update (50ms = ~20 FPS)
        if self.root.winfo_exists():
            self.root.after(50, self.update_preview_images)
    
    def stop_roi_preview(self):
        """Stop ROI preview cleanly"""
        if self.roi_preview_running:
            print("Stopping ROI preview...")
            self.roi_preview_running = False
            
            # Wait for thread to finish (with timeout)
            if self.preview_thread and self.preview_thread.is_alive():
                self.preview_thread.join(timeout=1.0)
            
            # Clear the queue
            while not self.image_queue.empty():
                try:
                    self.image_queue.get_nowait()
                except queue.Empty:
                    break
            
            print("ROI preview stopped")

    # ========== Logo selection and pre-compute its histogram.

    def get_hash(self, text: str) -> str:
        """Return stable hash for a string."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def check_processed(self, hash):
        return self.hash_values.index(hash) != -1
    
    def pair_headers_blocks(self, new_headers, new_blocks):
        # Add new unique headers to queue
        for h_text, h_data in new_headers:
            h_key = self.get_hash(h_text)
            if h_key not in [self.get_hash(ht) for ht, _ in self.header_queue]:
                self.header_queue.append((h_text, h_data))

         # Add new unique blocks to queue
        for b_text, b_data in new_blocks:
            b_key = self.get_hash(b_text)
            if b_key not in [self.get_hash(bt) for bt, _ in self.block_queue]:
                self.block_queue.append((b_text, b_data))

        # Pairing
        pairs = []
        h_index = 0
        while h_index < len(self.header_queue):
            header_text, header_obj = self.header_queue[h_index]
            paired = False
            for b_index, (block_text, block_obj) in enumerate(self.block_queue):
                if block_obj.y > header_obj.y:
                    # Pair and remove from queues
                    pairs.append((header_obj, block_obj))
                    self.header_queue.remove((header_text, header_obj))
                    self.block_queue.remove((block_text, block_obj))
                    paired = True
                    break
            if not paired:
                h_index += 1

        return pairs
    
    def calculate_hist(self, logo):
        # Compute histogram of selected logo ROI
        logo_hsv = cv2.cvtColor(logo, cv2.COLOR_BGR2HSV)
        logo_hist = cv2.calcHist([logo_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        logo_hist = cv2.normalize(logo_hist, logo_hist, 0, 1, cv2.NORM_MINMAX)

        return logo_hist
    
    # ========== Detect the scrolling and trigger capture & detect blocks ==========
    def start_scroll_detection(self):
        """Start scroll detection in background thread"""

        if not self.roi_coordinates:
            return
            
        # if not self.scroll_detection_running:
        #     return
            
        print("Starting scroll detection...")
        self.scroll_detection_running = True
        self.scroll_thread = threading.Thread(target=self._scroll_detection_loop, daemon=True)
        self.scroll_thread.start()
    
    def detect_scroll_change(self, prev_frame, curr_frame, threshold=5000):
        threshold = self.scroll_value.get()
        """Detect if scrolling is occurring based on frame differences"""
        try:
            # Convert BGRA to BGR first (mss returns BGRA format)
            if prev_frame.shape[2] == 4:  # BGRA
                prev_frame = cv2.cvtColor(prev_frame, cv2.COLOR_BGRA2BGR)
            if curr_frame.shape[2] == 4:  # BGRA
                curr_frame = cv2.cvtColor(curr_frame, cv2.COLOR_BGRA2BGR)
            
            # Calculate absolute difference directly on BGR frames
            diff = cv2.absdiff(prev_frame, curr_frame)
            
            # Convert difference to grayscale
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Count non-zero pixels
            non_zero_count = cv2.countNonZero(gray_diff)
            
            is_scrolling = non_zero_count > threshold
            
            return is_scrolling, non_zero_count
            
        except Exception as e:
            print(f"Scroll detection error: {e}")
            return False, 0
    
    def _scroll_detection_loop(self):
        """Background thread for scroll detection"""
        try:
            with mss.mss() as sct:
                # Initialize
                self.prev_frame = None
                
                while self.scroll_detection_running:
                    try:
                        if not self.roi_monitor:
                            break
                            
                        # Capture current frame - keep as numpy array from mss
                        sct_img = sct.grab(self.roi_monitor)
                        curr_frame = np.array(sct_img)  # This is BGRA format
                        
                        if self.prev_frame is not None:
                            # Detect scroll change
                            is_scrolling, diff_count = self.detect_scroll_change(
                                self.prev_frame, curr_frame, self.scroll_threshold
                            )
                            
                            # Immediate status update (no debouncing for testing)
                            new_status = "Scrolling" if is_scrolling else "Captured"

                            if self.current_scroll_state != new_status:
                                self.current_scroll_state = new_status
                                
                                # Update canvas text overlay on main thread
                                text_color = "orange" if new_status == "Scrolling" else "lime"
                                
                                self.root.after(0, lambda s=new_status, c=text_color: 
                                            self.update_scroll_canvas_text(s, c))
                            
                            if is_scrolling:
                                # Reset processed flag when scrolling occurs
                                self.frame_processed = False

                            else:
                                # Trigger block detection once scrolling stops
                                if not self.frame_processed and self.logo is not None and self.logo_hist is not None:
                                    self._trigger_block_detection(curr_frame.copy())
                                    self.frame_processed = True
                                else: 
                                    continue

                        
                        # Store current frame for next comparison
                        self.prev_frame = curr_frame.copy()
                        
                        # Control detection rate (same as your working code - 10 FPS)
                        time.sleep(0.1)  
                        
                    except Exception as e:
                        time.sleep(0.1)
                        
        except Exception as e:
            print(f"Scroll detection thread error: {e}")
        finally:
            print("Scroll detection thread stopped")

    def _trigger_block_detection(self, frame):
        """Trigger block detection in a separate thread (non-blocking)"""
        with self.block_detection_lock:
            # Only start a new thread if the previous is done
            if self.block_detection_thread is None or not self.block_detection_thread.is_alive():
                self.block_detection_thread = threading.Thread(
                    target=self._detect_and_show_result, args=(frame.copy(),), daemon=True
                )
                self.block_detection_thread.start()

    def _detect_and_show_result(self, frame):
        """
        Detect blocks and safely update the preview canvas
        """
        try:
            # Convert MSS BGRA -> BGR
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            if frame_bgr is not None and self.logo is not None and self.logo_hist is not None:
                # Detect rectangles
                blocks, headers, original_image = self.detector.detect_rectangles(frame_bgr)
                # Get top N blocks
                top_10_rectangles = self.detector.get_top_n(blocks, 10)

                # Visualize
                result_image, detected_blocks = self.detector.visualize_results(original_image, top_10_rectangles, headers)
                # print(self.detector.logo_hist)

                # Schedule UI update on main thread
                self.root.after(0, lambda: self.update_result_images(result_image))
                  
                # pairs = self._process_pairing(headers, detected_blocks)

                # print(pairs)

                
        except Exception as e:
            print(f"Block detection error: {e}")
            import traceback
            traceback.print_exc()  # This will show the full traceback

    def _process_pairing(self, headers, blocks):
        # Add headers to queue if unique
        for header in headers:
            h_text = extract_text.extract_block_data(header)
            h_hash = self.get_hash(h_text)
            if not self.check_processed(h_hash):
                self.hash_values.append(h_hash)
                self.header_queue.append((header, h_text))  # keep text for Treeview

        # Add blocks to queue if unique
        for block in blocks:
            b_text = extract_text.extract_block_data(block)
            b_hash = self.get_hash(b_text)
            if not self.check_processed(b_hash):
                self.hash_values.append(b_hash)
                self.block_queue.append((block, b_text))

        pairs = []

        # Try pairing headers with nearest block below
        h_index = 0
        while h_index < len(self.header_queue):
            header, h_text = self.header_queue[h_index]
            paired = False
            for b_index, (block, b_text) in enumerate(self.block_queue):
                if block.y > header.y:
                    # ✅ Found a pair
                    pairs.append((h_text, b_text))

                    # Push into Treeview
                    self.tree.insert("", "end", values=(h_text, b_text))

                    # Remove from queues
                    self.header_queue.pop(h_index)
                    self.block_queue.pop(b_index)
                    paired = True
                    break
            if not paired:
                h_index += 1  # move to next header

        return pairs

    def update_result_images(self, frame_bgr):
        """Update the detected_canvas with the latest processed frame without freezing UI."""
        # Remove placeholder text if it exists
        if hasattr(self, 'detected_placeholder') and self.detected_placeholder:
            self.detected_canvas.delete(self.detected_placeholder)
            self.detected_placeholder = None

        def task():
            try:
                # Convert frame (numpy array) to RGB
                rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                # Convert to PIL image
                pil_image = Image.fromarray(rgb_frame)

                # Resize to fit canvas (maintain aspect ratio)
                canvas_width = 270
                canvas_height = 540
                
                # Calculate aspect ratio preserving resize
                img_width, img_height = pil_image.size
                aspect_ratio = img_width / img_height
                
                if aspect_ratio > (canvas_width / canvas_height):
                    # Image is wider - fit to width
                    new_width = canvas_width
                    new_height = int(canvas_width / aspect_ratio)
                else:
                    # Image is taller - fit to height
                    new_height = canvas_height
                    new_width = int(canvas_height * aspect_ratio)
                
                # Resize with high quality
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Convert to Tkinter-compatible image
                self.detected_photo = ImageTk.PhotoImage(pil_image)

                # Thread-safe update on UI
                self.detected_canvas.after(0, lambda: self.detected_canvas.itemconfig(self.detected_canvas_image, image=self.detected_photo))
                
            except Exception as e:
                print(f"update_result_images error: {e}")

        threading.Thread(target=task, daemon=True).start()

    # ========== Add this new method ==========
    def update_scroll_canvas_text(self, status, color):
        """Update scroll status text on canvas overlay"""
        try:
            if self.scroll_text_id and self.original_canvas.winfo_exists():
                self.original_canvas.itemconfig(self.scroll_text_id, 
                                            text=status, 
                                            fill=color)
        except Exception as e:
            print(f"Canvas text update error: {e}")

    def stop_scroll_detection(self):
        """Stop scroll detection cleanly"""
        if self.scroll_detection_running:
            print("Stopping scroll detection...")
            self.scroll_detection_running = False
            
            # Wait for thread to finish
            if self.scroll_thread and self.scroll_thread.is_alive():
                self.scroll_thread.join(timeout=1.0)
            
            # Reset status
            self.current_scroll_state = "Unknown"
            print("Scroll detection stopped")

    # ========== Window Management ==========
            
    def on_close(self):
        """Handle window close event"""
        
        # Stop preview cleanly
        self.stop_roi_preview()
        self.stop_scroll_detection()
        
        # Ask for confirmation
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            # Clean up any remaining threads
            self.roi_preview_running = False
            self.scroll_detection_running = False
            
            # Small delay to let threads finish
            self.root.after(200, self.root.destroy)
        else:
            # If user cancels, restart preview if ROI was selected
            if self.roi_coordinates and self.roi_coordinates['width'] != 0 and self.roi_coordinates['height'] != 0:
                self.root.after(300, lambda: self.start_roi_preview())
                self.root.after(300, lambda: self.start_scroll_detection())


def main():
    """Main function to run the application"""
    print("Starting NESINE Odds Scraper...")
    
    # Create the main window with ttkbootstrap
    root = tb.Window()
    
    # Create the application instance
    app = MainUI(root)
    
    # Start the main event loop
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