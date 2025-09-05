import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, colorchooser
import ttkbootstrap as tb
import cv2
import re
import pandas as pd
from paddleocr import PaddleOCR
from PIL import Image, ImageTk
import mss
import numpy as np
import threading
import time
import hashlib
from collections import deque
from datetime import datetime
import json

class NESINEOddsScraper:
    def __init__(self, root):
        self.root = root
        self.root.title("NESINE Odds Scraper - Divider-First Block Detection")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        tb.Style("darkly")
        
        # ========== Core State ==========
        self.running = threading.Event()
        self.stop_flag = False
        self.odds_data = []
        self.roi = None
        self.team_roi = None
        self.nesine_logo_roi = None
        self.divider_color = None
        self.detected_hashes = deque(maxlen=1000)
        
        # ========== Block Detection State ==========
        self.partial_blocks = {}  # Store partial blocks across frames
        self.frame_sequence = 0
        self.divider_tolerance = 15  # Color tolerance for divider detection
        self.min_divider_length = 50  # Minimum divider line length
        
        # ========== UI Variables ==========
        self.status_text = tk.StringVar(value="Ready - Configure ROIs and divider color")
        self.fps = tk.IntVar(value=10)
        self.use_gpu = tk.BooleanVar(value=False)
        self.apply_threshold = tk.BooleanVar(value=True)
        self.detection_sensitivity = tk.DoubleVar(value=0.75)
        self.manual_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        
        # ========== OCR Setup ==========
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='tr',
            use_gpu=False,
            show_log=False,
            rec_algorithm='CRNN',
            det_algorithm='DB'
        )
        
        # ========== Preview State ==========
        self.current_frame = None
        self.preview_frame = None
        self.detected_blocks_visual = []
        self.frame_counter = 0
        self.processing_times = deque(maxlen=10)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup compact UI with large tree view as main panel"""
        # Configure grid weights - main focus on tree view
        self.root.grid_rowconfigure(0, weight=2)  # Top row with controls/preview
        self.root.grid_rowconfigure(1, weight=3)  # Bottom row with tree view (main)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        # ========== Top Left: Preview Panel ==========
        self.setup_preview_panel()
        
        # ========== Top Right: Controls Panel ==========
        self.setup_control_panel()
        
        # ========== Bottom: Main Data Table (Full Width) ==========
        self.setup_data_panel()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_preview_panel(self):
        """Setup compact preview panel - Samsung Flow A55 aspect ratio"""
        preview_frame = ttk.LabelFrame(self.root, text="Live Preview", padding=3)
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        
        # Samsung Flow A55 aspect ratio (roughly 9:19.5, but we'll use 9:18 for better fit)
        # Width: 270px, Height: 540px (keeping under 300px width as requested)
        self.preview_canvas = tk.Canvas(preview_frame, bg="black", width=270, height=540)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Preview label
        self.preview_label = ttk.Label(self.preview_canvas, text="Configure ROIs to start", 
                                     anchor="center", background="black", foreground="white")
        self.canvas_window = self.preview_canvas.create_window(135, 270, window=self.preview_label)
        
    def setup_control_panel(self):
        """Setup compact control panel"""
        control_main = ttk.Frame(self.root)
        control_main.grid(row=0, column=1, sticky="nsew", padx=3, pady=3)
        control_main.grid_rowconfigure(6, weight=1)  # Make last frame expandable
        control_main.grid_columnconfigure(0, weight=1)
        
        # ========== ROI Configuration ==========
        roi_frame = ttk.LabelFrame(control_main, text="ROI Configuration", padding=3)
        roi_frame.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        roi_frame.grid_columnconfigure((0, 1), weight=1)
        
        ttk.Button(roi_frame, text="Data ROI", command=self.select_roi, 
                  style="primary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 1))
        ttk.Button(roi_frame, text="Team ROI", command=self.select_team_roi).grid(
            row=0, column=1, sticky="ew", padx=(1, 0))
        
        ttk.Button(roi_frame, text="Logo ROI", command=self.select_logo_roi).grid(
            row=1, column=0, sticky="ew", padx=(0, 1), pady=1)
        ttk.Button(roi_frame, text="Divider Color", command=self.pick_divider_color).grid(
            row=1, column=1, sticky="ew", padx=(1, 0), pady=1)
        
        self.config_status = ttk.Label(roi_frame, text="ROIs: 0/4 configured", foreground="red")
        self.config_status.grid(row=2, column=0, columnspan=2, pady=1)
        
        # ========== Controls ==========
        control_frame = ttk.LabelFrame(control_main, text="Controls", padding=3)
        control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        control_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.start_btn = ttk.Button(control_frame, text="START", command=self.start_capture, 
                                   style="success.TButton")
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=1)
        
        self.pause_btn = ttk.Button(control_frame, text="PAUSE", command=self.pause_capture, 
                                   state="disabled")
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=1)
        
        self.stop_btn = ttk.Button(control_frame, text="STOP", command=self.stop_capture, 
                                  state="disabled")
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=1)
        
        ttk.Button(control_frame, text="CLEAR DATA", command=self.clear_data).grid(
            row=1, column=0, columnspan=3, pady=2, sticky="ew")
        
        # ========== Date Input ==========
        date_frame = ttk.LabelFrame(control_main, text="Date/Time", padding=3)
        date_frame.grid(row=2, column=0, sticky="ew", pady=(0, 2))
        
        ttk.Entry(date_frame, textvariable=self.manual_date, font=("Arial", 9)).pack(fill="x")
        
        # ========== Status ==========
        status_frame = ttk.LabelFrame(control_main, text="Status", padding=3)
        status_frame.grid(row=3, column=0, sticky="ew", pady=(0, 2))
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_text, 
                                    font=("Arial", 8), wraplength=200)
        self.status_label.pack(anchor="w")
        
        self.performance_label = ttk.Label(status_frame, text="Performance: --", font=("Arial", 8))
        self.performance_label.pack(anchor="w")
        
        self.blocks_label = ttk.Label(status_frame, text="Blocks: 0 | Partial: 0", font=("Arial", 8))
        self.blocks_label.pack(anchor="w")
        
        # ========== Settings ==========
        settings_frame = ttk.LabelFrame(control_main, text="Detection Settings", padding=3)
        settings_frame.grid(row=4, column=0, sticky="ew", pady=(0, 2))
        settings_frame.grid_columnconfigure(1, weight=1)
        
        # FPS
        ttk.Label(settings_frame, text="FPS:", font=("Arial", 8)).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(settings_frame, from_=5, to=30, textvariable=self.fps, width=8).grid(
            row=0, column=1, sticky="ew", padx=(5, 0))
        
        # OCR Interval
        ttk.Label(settings_frame, text="OCR Every:", font=("Arial", 8)).grid(row=1, column=0, sticky="w")
        ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=self.ocr_interval, width=8).grid(
            row=1, column=1, sticky="ew", padx=(5, 0))
        
        # Detection Sensitivity
        ttk.Label(settings_frame, text="Sensitivity:", font=("Arial", 8)).grid(row=2, column=0, sticky="w")
        ttk.Scale(settings_frame, from_=0.5, to=1.0, variable=self.detection_sensitivity, 
                 orient="horizontal").grid(row=2, column=1, sticky="ew", padx=(5, 0))
        
        # Checkboxes
        ttk.Checkbutton(settings_frame, text="GPU", variable=self.use_gpu, 
                       command=self.toggle_gpu).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(settings_frame, text="Threshold", 
                       variable=self.apply_threshold).grid(row=3, column=1, sticky="w")
        
        # ========== Export ==========
        export_frame = ttk.LabelFrame(control_main, text="Export", padding=3)
        export_frame.grid(row=5, column=0, sticky="ew", pady=(0, 2))
        export_frame.grid_columnconfigure((0, 1), weight=1)
        
        ttk.Button(export_frame, text="CSV", command=self.export_csv).grid(
            row=0, column=0, padx=(0, 1), sticky="ew")
        ttk.Button(export_frame, text="Excel", command=self.export_excel).grid(
            row=0, column=1, padx=(1, 0), sticky="ew")
        
    def setup_data_panel(self):
        """Setup main data table panel - this is the primary interface"""
        data_frame = ttk.LabelFrame(self.root, text="Detected NESINE Blocks (Main Panel)", padding=5)
        data_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=3, pady=3)
        data_frame.grid_rowconfigure(0, weight=1)
        data_frame.grid_columnconfigure(0, weight=1)
        
        # Create Treeview with larger display
        columns = ("timestamp", "team_names", "block_id", "confidence", "extracted_odds")
        self.tree = ttk.Treeview(data_frame, columns=columns, show="headings", height=12)
        
        # Define headings and column widths
        self.tree.heading("timestamp", text="Date/Time")
        self.tree.heading("team_names", text="Team Names")
        self.tree.heading("block_id", text="Block ID")
        self.tree.heading("confidence", text="Confidence")
        self.tree.heading("extracted_odds", text="Extracted Odds Data")
        
        self.tree.column("timestamp", width=120, anchor="center")
        self.tree.column("team_names", width=160, anchor="center")
        self.tree.column("block_id", width=80, anchor="center")
        self.tree.column("confidence", width=80, anchor="center")
        self.tree.column("extracted_odds", width=400, anchor="w")
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(data_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(data_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
    def select_roi(self):
        """Select main data ROI for capture"""
        self.roi = self.create_roi_selector("Select Main Data Region")
        self.update_config_status()
        
    def select_team_roi(self):
        """Select team names ROI"""
        self.team_roi = self.create_roi_selector("Select Team Names Region")
        self.update_config_status()
    
    def select_logo_roi(self):
        """Select NESINE logo ROI for pattern matching"""
        self.nesine_logo_roi = self.create_roi_selector("Select NESINE Logo Region")
        self.update_config_status()
    
    def pick_divider_color(self):
        """Pick divider background color for block separation"""
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.3)
        overlay.configure(bg="black")
        overlay.attributes("-topmost", True)
        
        canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        instruction = tk.Label(overlay, text="Click on divider/background color to sample", 
                             bg="yellow", fg="black", font=("Arial", 12))
        instruction.pack(pady=10)
        
        def on_click(event):
            x, y = event.x, event.y
            try:
                with mss.mss() as sct:
                    # Sample 5x5 area for better color average
                    sample = sct.grab({"left": x-2, "top": y-2, "width": 5, "height": 5})
                    img = np.array(sample)
                    # Get average color (BGR format)
                    avg_color = img[:, :, :3].mean(axis=(0,1)).astype(int)
                    self.divider_color = tuple(avg_color.tolist())
                overlay.destroy()
                self.update_config_status()
            except Exception as e:
                print(f"Color picker error: {e}")
                overlay.destroy()
        
        canvas.bind("<Button-1>", on_click)
        overlay.bind("<Escape>", lambda e: overlay.destroy())
        overlay.focus_set()
    
    def update_config_status(self):
        """Update configuration status display"""
        config_count = sum([
            self.roi is not None,
            self.team_roi is not None,
            self.nesine_logo_roi is not None,
            self.divider_color is not None
        ])
        
        status_text = f"ROIs: {config_count}/4 configured"
        color = "green" if config_count >= 3 else "orange" if config_count >= 2 else "red"
        
        self.config_status.configure(text=status_text, foreground=color)
        
        if config_count >= 3:  # Minimum: data ROI, logo ROI, divider color
            self.status_text.set("Ready to start detection")
        else:
            self.status_text.set("Configure ROIs and divider color")
    
    def create_roi_selector(self, title="Select Region"):
        """Create ROI selection overlay"""
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
        instruction.pack(pady=10)
        
        start_x = start_y = None
        rect_id = None
        
        def on_mouse_down(event):
            nonlocal start_x, start_y, rect_id
            start_x, start_y = event.x, event.y
            if rect_id:
                canvas.delete(rect_id)
            rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y, 
                                           outline="red", width=3)
        
        def on_mouse_drag(event):
            if rect_id:
                canvas.coords(rect_id, start_x, start_y, event.x, event.y)
        
        def on_mouse_up(event):
            nonlocal roi
            if start_x is not None and start_y is not None:
                end_x, end_y = event.x, event.y
                roi = {
                    "left": min(start_x, end_x),
                    "top": min(start_y, end_y),
                    "width": abs(end_x - start_x),
                    "height": abs(end_y - start_y)
                }
            overlay.destroy()
        
        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        overlay.bind("<Escape>", lambda e: overlay.destroy())
        overlay.focus_set()
        
        self.root.wait_window(overlay)
        return roi
    
    def start_capture(self):
        """Start capture and detection"""
        if not self.roi or not self.divider_color:
            messagebox.showwarning("Configuration Incomplete", 
                                 "Please configure at least Data ROI and Divider Color!")
            return
        
        self.stop_flag = False
        self.running.set()
        self.frame_sequence = 0
        self.partial_blocks.clear()
        
        # Update UI
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        
        # Start worker threads
        threading.Thread(target=self.capture_and_detect_loop, daemon=True).start()
        
        self.status_text.set("Running divider-first block detection...")
    
    def pause_capture(self):
        """Pause capture"""
        self.running.clear()
        self.pause_btn.configure(state="disabled")
        self.start_btn.configure(state="normal")
        self.status_text.set("Paused")
    
    def stop_capture(self):
        """Stop capture completely"""
        self.stop_flag = True
        self.running.clear()
        
        # Reset UI
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        
        self.status_text.set("Stopped")
    
    def toggle_gpu(self):
        """Toggle GPU usage for OCR"""
        try:
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                lang='tr',
                use_gpu=self.use_gpu.get(),
                show_log=False,
                rec_algorithm='CRNN',
                det_algorithm='DB'
            )
            status = "enabled" if self.use_gpu.get() else "disabled"
            self.status_text.set(f"GPU {status}")
        except Exception as e:
            self.use_gpu.set(False)
            messagebox.showerror("GPU Error", f"Failed to enable GPU: {str(e)}")
    
    def capture_and_detect_loop(self):
        """Main capture and detection loop - divider-first approach"""
        with mss.mss() as sct:
            while not self.stop_flag:
                if self.running.is_set() and self.roi:
                    start_time = time.time()
                    
                    try:
                        # Capture screenshot
                        screenshot = sct.grab(self.roi)
                        screenshot_array = np.array(screenshot)
                        frame = cv2.cvtColor(screenshot_array, cv2.COLOR_BGRA2BGR)
                        
                        # Apply threshold if enabled
                        if self.apply_threshold.get():
                            frame = self.apply_image_threshold(frame)
                        
                        self.frame_sequence += 1
                        self.current_frame = frame.copy()
                        
                        # DIVIDER-FIRST APPROACH
                        blocks = self.detect_blocks_by_dividers(frame)
                        
                        # Process detected blocks
                        if blocks:
                            self.process_detected_blocks(frame, blocks)
                        
                        # Update preview every few frames
                        if self.frame_sequence % max(1, self.fps.get() // 5) == 0:
                            self.update_preview_with_detections(frame, blocks)
                        
                        # Performance tracking
                        process_time = time.time() - start_time
                        self.processing_times.append(process_time)
                        self.root.after(0, self.update_performance_display, process_time)
                        
                        # Control FPS
                        target_delay = 1.0 / max(1, self.fps.get())
                        remaining_time = target_delay - process_time
                        if remaining_time > 0:
                            time.sleep(remaining_time)
                            
                    except Exception as e:
                        print(f"Capture/Detection error: {e}")
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)
    
    def detect_blocks_by_dividers(self, frame):
        """CORE: Divider-first block detection approach"""
        try:
            h, w = frame.shape[:2]
            blocks = []
            
            # Convert divider color to numpy array for comparison
            divider_bgr = np.array(self.divider_color, dtype=np.uint8)
            
            # Create mask for divider color
            lower_bound = np.clip(divider_bgr - self.divider_tolerance, 0, 255)
            upper_bound = np.clip(divider_bgr + self.divider_tolerance, 0, 255)
            
            divider_mask = cv2.inRange(frame, lower_bound, upper_bound)
            
            # Find horizontal divider lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (self.min_divider_length, 1))
            horizontal_lines = cv2.morphologyEx(divider_mask, cv2.MORPH_OPEN, horizontal_kernel)
            
            # Find contours of divider lines
            contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Extract Y positions of dividers
            divider_y_positions = []
            for contour in contours:
                if cv2.contourArea(contour) > self.min_divider_length:
                    y = int(np.mean([point[0][1] for point in contour]))
                    divider_y_positions.append(y)
            
            # Sort divider positions
            divider_y_positions.sort()
            
            # Create blocks between consecutive dividers
            for i in range(len(divider_y_positions) - 1):
                y1 = divider_y_positions[i]
                y2 = divider_y_positions[i + 1]
                
                # Skip if block is too small
                if (y2 - y1) < 30:
                    continue
                
                block = {
                    'x1': 0,
                    'y1': y1 + 2,  # Slight offset from divider
                    'x2': w,
                    'y2': y2 - 2,  # Slight offset from divider
                    'type': 'complete',
                    'frame_id': self.frame_sequence
                }
                blocks.append(block)
            
            # Handle partial blocks at top and bottom
            if divider_y_positions:
                # Partial block at top
                if divider_y_positions[0] > 30:
                    top_block = {
                        'x1': 0,
                        'y1': 0,
                        'x2': w,
                        'y2': divider_y_positions[0] - 2,
                        'type': 'partial_top',
                        'frame_id': self.frame_sequence
                    }
                    blocks.append(top_block)
                
                # Partial block at bottom
                if (h - divider_y_positions[-1]) > 30:
                    bottom_block = {
                        'x1': 0,
                        'y1': divider_y_positions[-1] + 2,
                        'x2': w,
                        'y2': h,
                        'type': 'partial_bottom',
                        'frame_id': self.frame_sequence
                    }
                    blocks.append(bottom_block)
            
            return blocks
            
        except Exception as e:
            print(f"Divider detection error: {e}")
            return []
    
    def process_detected_blocks(self, frame, blocks):
        """Process detected blocks - handle complete and partial blocks"""
        for block in blocks:
            try:
                # Extract block region
                x1, y1, x2, y2 = block['x1'], block['y1'], block['x2'], block['y2']
                block_image = frame[y1:y2, x1:x2]
                
                if block_image.size == 0:
                    continue
                
                # Generate block hash
                block_hash = hashlib.md5(block_image.tobytes()).hexdigest()
                
                # Handle different block types
                if block['type'] == 'complete':
                    # Process complete block immediately
                    self.process_complete_block(frame, block, block_image, block_hash)
                    
                elif block['type'] in ['partial_top', 'partial_bottom']:
                    # Handle partial blocks - buffer and try to reconstruct
                    self.handle_partial_block(frame, block, block_image, block_hash)
                    
            except Exception as e:
                print(f"Block processing error: {e}")
    
    def process_complete_block(self, frame, block, block_image, block_hash):
        """Process a complete block"""
        try:
            # Skip if already processed
            if block_hash in self.detected_hashes:
                return
            
            # Verify this is a NESINE block
            if not self.verify_nesine_block(block_image):
                return
            
            # Add to processed hashes
            self.detected_hashes.append(block_hash)
            
            # Extract betting data via OCR
            self.extract_and_store_block_data(frame, block, block_image, block_hash)
            
        except Exception as e:
            print(f"Complete block processing error: {e}")
    
    def handle_partial_block(self, frame, block, block_image, block_hash):
        """Handle partial blocks - buffer and reconstruct when possible"""
        try:
            block_key = f"{block['type']}_{block_hash[:8]}"
            
            # Store partial block
            self.partial_blocks[block_key] = {
                'frame_id': block['frame_id'],
                'block': block,
                'image': block_image.copy(),
                'hash': block_hash,
                'timestamp': time.time()
            }
            
            # Try to reconstruct with buffered blocks
            self.try_reconstruct_partial_blocks()
            
            # Clean old partial blocks (older than 2 seconds)
            current_time = time.time()
            keys_to_remove = []
            for key, partial in self.partial_blocks.items():
                if (current_time - partial['timestamp']) > 2.0:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.partial_blocks[key]
                
        except Exception as e:
            print(f"Partial block handling error: {e}")
    
    def try_reconstruct_partial_blocks(self):
        """Try to reconstruct complete blocks from partial blocks"""
        try:
            # Look for top and bottom parts that can be combined
            top_blocks = {k: v for k, v in self.partial_blocks.items() if 'partial_top' in k}
            bottom_blocks = {k: v for k, v in self.partial_blocks.items() if 'partial_bottom' in k}
            
            # Try to match top and bottom blocks
            for top_key, top_data in top_blocks.items():
                for bottom_key, bottom_data in bottom_blocks.items():
                    # Check if frames are consecutive or close
                    frame_diff = abs(top_data['frame_id'] - bottom_data['frame_id'])
                    if frame_diff <= 2:  # Allow small frame gaps
                        # Try to reconstruct full block
                        reconstructed = self.reconstruct_full_block(top_data, bottom_data)
                        if reconstructed:
                            # Remove used partial blocks
                            if top_key in self.partial_blocks:
                                del self.partial_blocks[top_key]
                            if bottom_key in self.partial_blocks:
                                del self.partial_blocks[bottom_key]
                            break
                            
        except Exception as e:
            print(f"Block reconstruction error: {e}")
    
    def reconstruct_full_block(self, top_data, bottom_data):
        """Reconstruct a complete block from top and bottom parts"""
        try:
            top_image = top_data['image']
            bottom_image = bottom_data['image']
            
            # Check if images have compatible widths
            if abs(top_image.shape[1] - bottom_image.shape[1]) > 10:
                return False
            
            # Combine images vertically
            combined_height = top_image.shape[0] + bottom_image.shape[0]
            combined_width = max(top_image.shape[1], bottom_image.shape[1])
            
            combined_image = np.zeros((combined_height, combined_width, 3), dtype=np.uint8)
            combined_image[:top_image.shape[0], :top_image.shape[1]] = top_image
            combined_image[top_image.shape[0]:, :bottom_image.shape[1]] = bottom_image
            
            # Generate new hash for combined block
            combined_hash = hashlib.md5(combined_image.tobytes()).hexdigest()
            
            # Skip if already processed
            if combined_hash in self.detected_hashes:
                return True
            
            # Verify this is a NESINE block
            if not self.verify_nesine_block(combined_image):
                return False
            
            # Add to processed hashes
            self.detected_hashes.append(combined_hash)
            
            # Create combined block info
            combined_block = {
                'x1': 0,
                'y1': 0,
                'x2': combined_width,
                'y2': combined_height,
                'type': 'reconstructed',
                'frame_id': max(top_data['frame_id'], bottom_data['frame_id'])
            }
            
            # Extract and store data
            self.extract_and_store_block_data(None, combined_block, combined_image, combined_hash, is_reconstructed=True)
            
            return True
            
        except Exception as e:
            print(f"Full block reconstruction error: {e}")
            return False
    
    def verify_nesine_block(self, block_image):
        """Verify if block contains NESINE logo/branding"""
        try:
            # If we have a logo ROI template, use template matching
            if self.nesine_logo_roi and hasattr(self, 'logo_template'):
                result = cv2.matchTemplate(block_image, self.logo_template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val > self.detection_sensitivity.get():
                    return True
            
            # Fallback: OCR-based verification
            results = self.ocr.ocr(block_image, cls=True)
            if not results or not results[0]:
                return False
            
            for line in results[0]:
                text = line[1][0].upper().replace('İ', 'I').replace('Ş', 'S')
                confidence = line[1][1]
                
                if 'NESINE' in text and confidence > (self.detection_sensitivity.get() - 0.1):
                    return True
            
            return False
            
        except Exception as e:
            print(f"NESINE verification error: {e}")
            return False
    
    def extract_and_store_block_data(self, frame, block, block_image, block_hash, is_reconstructed=False):
        """Extract betting data and store in results"""
        try:
            # Run OCR on the block
            if self.frame_counter % self.ocr_interval.get() != 0 and not is_reconstructed:
                return  # Skip OCR for performance unless it's a reconstructed block
            
            results = self.ocr.ocr(block_image, cls=True)
            if not results or not results[0]:
                return
            
            # Extract betting odds data
            betting_data = self.extract_betting_odds(results[0])
            if not betting_data['odds_text']:
                return
            
            # Get team names from team ROI if available and main frame exists
            team_names = "Reconstructed Block"
            if frame is not None and self.team_roi:
                team_names = self.extract_team_names(frame)
            elif not is_reconstructed:
                team_names = "No Team ROI"
            
            # Create final data entry
            block_data = {
                'timestamp': self.manual_date.get(),
                'team_names': team_names[:100],
                'block_id': block_hash[:8],
                'confidence': f"{betting_data['avg_confidence']:.2f}",
                'extracted_odds': betting_data['odds_text']
            }
            
            # Store and update UI
            self.odds_data.append(block_data)
            self.root.after(0, self.update_data_table, block_data)
            
        except Exception as e:
            print(f"Data extraction error: {e}")
    
    def extract_betting_odds(self, ocr_results):
        """Extract and format betting odds - Turkish format with improved parsing"""
        betting_items = []
        confidences = []
        
        try:
            for line in ocr_results:
                text = line[1][0].strip()
                confidence = line[1][1]
                
                if confidence < 0.5 or 'NESINE' in text.upper():
                    continue
                
                confidences.append(confidence)
                
                # Look for odds patterns (Turkish format: 1,85 or 1.85)
                odds_matches = re.findall(r'(\d+[.,]\d+)', text)
                
                if odds_matches:
                    # Clean text (remove odds numbers)
                    clean_text = text
                    for odds in odds_matches:
                        clean_text = re.sub(re.escape(odds), '', clean_text).strip()
                    
                    # Format each odds found
                    for odds in odds_matches:
                        odds_normalized = odds.replace(',', '.')
                        try:
                            # Validate odds value
                            odds_float = float(odds_normalized)
                            if 1.0 <= odds_float <= 1000.0:  # Reasonable odds range
                                if clean_text and len(clean_text) > 1:
                                    betting_items.append(f"{clean_text}({odds_normalized})")
                                else:
                                    betting_items.append(f"({odds_normalized})")
                        except ValueError:
                            continue
                else:
                    # Pure text without odds - could be market name or team name
                    if len(text) > 2 and not re.search(r'^\d+', text):
                        # Clean up common OCR artifacts
                        text = re.sub(r'[^\w\sğüşıöçĞÜŞİÖÇ.-]', '', text).strip()
                        if len(text) > 1:
                            betting_items.append(text)
            
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            odds_text = " | ".join(betting_items[:15])  # Limit to prevent UI overflow
            
            return {
                'odds_text': odds_text,
                'avg_confidence': avg_confidence
            }
        
        except Exception as e:
            print(f"Odds extraction error: {e}")
            return {'odds_text': '', 'avg_confidence': 0}
    
    def extract_team_names(self, frame):
        """Extract team names from dedicated team ROI"""
        try:
            if not self.team_roi:
                return "No Team ROI"
            
            # Extract team region
            x = self.team_roi["left"] - (self.roi["left"] if self.roi else 0)
            y = self.team_roi["top"] - (self.roi["top"] if self.roi else 0)
            w = self.team_roi["width"]
            h = self.team_roi["height"]
            
            # Ensure coordinates are within frame bounds
            frame_h, frame_w = frame.shape[:2]
            if x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
                return "Team ROI Out of Bounds"
            
            team_region = frame[y:y+h, x:x+w]
            if team_region.size == 0:
                return "Empty Team ROI"
            
            # OCR on team region
            team_results = self.ocr.ocr(team_region, cls=True)
            if not team_results or not team_results[0]:
                return "No Team Text"
            
            # Extract team names
            team_texts = []
            for line in team_results[0]:
                text = line[1][0].strip()
                confidence = line[1][1]
                
                if confidence > 0.6 and len(text) > 2:
                    # Clean team name
                    text = re.sub(r'[^\w\sğüşıöçĞÜŞİÖÇ.-]', '', text).strip()
                    if len(text) > 2:
                        team_texts.append(text)
            
            return " vs ".join(team_texts[:2]) if team_texts else "Unknown Teams"
            
        except Exception as e:
            print(f"Team extraction error: {e}")
            return f"Team Error: {str(e)[:20]}"
    
    def apply_image_threshold(self, frame):
        """Apply image processing for better OCR and detection"""
        try:
            # Convert to grayscale for processing
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # Apply adaptive threshold
            thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            
            # Convert back to BGR
            return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            
        except Exception as e:
            print(f"Image threshold error: {e}")
            return frame
    
    def update_preview_with_detections(self, frame, detected_blocks):
        """Update preview with visual detection indicators"""
        try:
            preview_frame = frame.copy()
            
            # Draw detected blocks with red rectangles
            for block in detected_blocks:
                x1, y1, x2, y2 = block['x1'], block['y1'], block['x2'], block['y2']
                
                # Different colors for different block types
                if block['type'] == 'complete':
                    color = (0, 255, 0)  # Green for complete
                elif block['type'] == 'reconstructed':
                    color = (255, 0, 255)  # Magenta for reconstructed
                else:
                    color = (0, 0, 255)  # Red for partial
                
                # Draw rectangle
                cv2.rectangle(preview_frame, (x1, y1), (x2, y2), color, 2)
                
                # Add block type label
                label = f"{block['type'][:4]}#{block.get('frame_id', '?')}"
                cv2.putText(preview_frame, label, (x1, y1-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            
            # Add frame counter
            cv2.putText(preview_frame, f"Frame: {self.frame_sequence}", (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Add partial blocks counter
            partial_count = len(self.partial_blocks)
            cv2.putText(preview_frame, f"Partial: {partial_count}", (10, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
            # Update preview display
            self.update_preview(preview_frame)
            
        except Exception as e:
            print(f"Preview update with detections error: {e}")
            # Fallback to regular preview
            self.update_preview(frame)
    
    def update_preview(self, frame):
        """Update preview display - Samsung A55 aspect ratio (9:18)"""
        try:
            h, w = frame.shape[:2]
            
            # Samsung A55-like aspect ratio: 270x540 (9:18)
            target_width, target_height = 270, 540
            
            # Calculate scaling to fit within target size while maintaining aspect ratio
            scale_w = target_width / w
            scale_h = target_height / h
            scale = min(scale_w, scale_h)
            
            new_width = int(w * scale)
            new_height = int(h * scale)
            
            # Resize frame
            resized_frame = cv2.resize(frame, (new_width, new_height))
            
            # Convert to RGB for tkinter
            rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            photo = ImageTk.PhotoImage(pil_image)
            
            # Update in main thread
            self.root.after(0, self._update_preview_image, photo)
            
        except Exception as e:
            print(f"Preview update error: {e}")
    
    def _update_preview_image(self, photo):
        """Update preview image in main thread"""
        try:
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo  # Keep reference
            
        except Exception as e:
            print(f"Preview image update error: {e}")
    
    def update_data_table(self, block_data):
        """Update main data table with new block"""
        try:
            self.tree.insert("", "end", values=(
                block_data['timestamp'],
                block_data['team_names'],
                block_data['block_id'],
                block_data['confidence'],
                block_data['extracted_odds']
            ))
            
            # Auto-scroll to bottom
            children = self.tree.get_children()
            if children:
                self.tree.see(children[-1])
            
            # Update counter
            partial_count = len(self.partial_blocks)
            self.blocks_label.configure(text=f"Blocks: {len(self.odds_data)} | Partial: {partial_count}")
            
        except Exception as e:
            print(f"Table update error: {e}")
    
    def update_performance_display(self, process_time):
        """Update performance metrics display"""
        try:
            if self.processing_times:
                avg_time = sum(self.processing_times) / len(self.processing_times)
                fps = 1.0 / avg_time if avg_time > 0 else 0
                
                self.performance_label.configure(
                    text=f"Performance: {fps:.1f} FPS | Process: {process_time*1000:.0f}ms"
                )
        except Exception as e:
            print(f"Performance update error: {e}")
    
    def clear_data(self):
        """Clear all collected data and reset state"""
        if messagebox.askyesno("Clear Data", "Clear all data and reset detection state?"):
            self.odds_data.clear()
            self.detected_hashes.clear()
            self.partial_blocks.clear()
            self.tree.delete(*self.tree.get_children())
            self.frame_sequence = 0
            self.blocks_label.configure(text="Blocks: 0 | Partial: 0")
            self.status_text.set("Data cleared - Ready to restart")
    
    def export_csv(self):
        """Export data to CSV file"""
        if not self.odds_data:
            messagebox.showinfo("No Data", "No data to export!")
            return
        
        try:
            df = pd.DataFrame(self.odds_data)
            filename = f"nesine_odds_divider_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            messagebox.showinfo("Export Success", f"Data exported to {filename}\n{len(self.odds_data)} records saved")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {str(e)}")
    
    def export_excel(self):
        """Export data to Excel file"""
        if not self.odds_data:
            messagebox.showinfo("No Data", "No data to export!")
            return
        
        try:
            df = pd.DataFrame(self.odds_data)
            filename = f"nesine_odds_divider_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            df.to_excel(filename, index=False, engine='openpyxl')
            messagebox.showinfo("Export Success", f"Data exported to {filename}\n{len(self.odds_data)} records saved")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export Excel: {str(e)}")
    
    def on_close(self):
        """Handle application close"""
        self.stop_flag = True
        self.running.clear()
        
        # Clean up resources
        if hasattr(self, 'current_frame'):
            del self.current_frame
        if hasattr(self, 'preview_frame'):
            del self.preview_frame
        
        self.root.destroy()

def main():
    """Main application entry point"""
    root = tb.Window()
    app = NESINEOddsScraper(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_close()

if __name__ == "__main__":
    main()