import tkinter as tk
from tkinter import ttk, messagebox
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
from ttkbootstrap.icons import Icon


class NesineOddsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NESINE Odds Scraper")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        # Style
        tb.Style("cyborg")  # dark modern theme

        # Variables
        self.running = threading.Event()
        self.stop_flag = False
        self.odds_data = []
        self.roi = None
        self.fps = tk.IntVar(value=5)
        self.use_gpu = tk.BooleanVar(value=False)
        self.apply_threshold = tk.BooleanVar(value=False)

        # OCR (default CPU, can re-init with GPU)
        self.ocr = PaddleOCR(use_textline_orientation=True, lang='en', use_gpu=False)

        # ================= Layout =================
        # Row 0 (70% height) → ROI Preview + Controls
        frame_top = ttk.Frame(root)
        frame_top.grid(row=0, column=0, sticky="nsew")

        self.label_image = ttk.Label(frame_top, text="ROI Preview", anchor="center")
        self.label_image.grid(row=0, column=0, sticky="nsew", padx=5, pady=7)

        frame_controls = ttk.Frame(frame_top)
        frame_controls.grid(row=0, column=1, sticky="ns", padx=5, pady=7)

        # Control buttons stacked vertically
        self.btn_select_roi = ttk.Button(frame_controls, text="SELECT ROI", command=self.select_roi)
        self.btn_select_roi.pack(fill="x", pady=3)

        self.btn_start = ttk.Button(frame_controls, text="START", command=self.start_stream)
        self.btn_start.pack(fill="x", pady=3)

        self.btn_pause = ttk.Button(frame_controls, text="PAUSE", command=self.pause_stream, state="disabled")
        self.btn_pause.pack(fill="x", pady=3)

        self.btn_resume = ttk.Button(frame_controls, text="RESUME", command=self.resume_stream, state="disabled")
        self.btn_resume.pack(fill="x", pady=3)

        ttk.Label(frame_controls, text="FPS:").pack(pady=3)
        self.spin_fps = ttk.Spinbox(frame_controls, from_=1, to=30, textvariable=self.fps, width=5)
        self.spin_fps.pack(pady=3)

        ttk.Checkbutton(frame_controls, text="Use GPU", variable=self.use_gpu, command=self.toggle_gpu).pack(pady=3)
        ttk.Checkbutton(frame_controls, text="Apply Threshold", variable=self.apply_threshold).pack(pady=3)

        self.btn_export_csv = ttk.Button(frame_controls, text="Export CSV", command=self.export_csv)
        self.btn_export_csv.pack(fill="x", pady=3)

        self.btn_export_excel = ttk.Button(frame_controls, text="Export Excel", command=self.export_excel)
        self.btn_export_excel.pack(fill="x", pady=3)

        # Row 1 (30% height) → Results table
        frame_bottom = ttk.Frame(root)
        frame_bottom.grid(row=1, column=0, sticky="nsew", padx=5, pady=7)

        self.tree = ttk.Treeview(frame_bottom, columns=("1", "X", "2"), show="headings")
        self.tree.heading("1", text="1")
        self.tree.heading("X", text="X")
        self.tree.heading("2", text="2")
        self.tree.pack(fill="both", expand=True)

        # Configure responsive grid weights
        root.grid_rowconfigure(0, weight=7)   # top row 70%
        root.grid_rowconfigure(1, weight=3)   # bottom row 30%
        root.grid_columnconfigure(0, weight=1)
        frame_top.grid_columnconfigure(0, weight=4)  # preview 80%
        frame_top.grid_columnconfigure(1, weight=1)  # controls 20%
        frame_top.grid_rowconfigure(0, weight=1)
        frame_bottom.grid_rowconfigure(0, weight=1)
        frame_bottom.grid_columnconfigure(0, weight=1)

        # Close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =========================
    # ROI Selection Overlay
    # =========================
    def select_roi(self):
        self.roi = None
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.3)  # semi-transparent
        overlay.config(bg="black")

        start_x = start_y = None
        rect_id = None

        canvas = tk.Canvas(overlay, cursor="cross", bg="black")
        canvas.pack(fill="both", expand=True)

        def on_mouse_down(event):
            nonlocal start_x, start_y, rect_id
            start_x, start_y = event.x, event.y
            rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y,
                                              outline="red", width=3)

        def on_mouse_drag(event):
            nonlocal rect_id
            canvas.coords(rect_id, start_x, start_y, event.x, event.y)

        def on_mouse_up(event):
            nonlocal rect_id
            end_x, end_y = event.x, event.y
            self.roi = {
                "top": min(start_y, end_y),
                "left": min(start_x, end_x),
                "width": abs(end_x - start_x),
                "height": abs(end_y - start_y)
            }
            overlay.destroy()
            messagebox.showinfo("ROI Selected", f"Region: {self.roi}")

        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)

    # =========================
    # OCR & Capture
    # =========================
    def capture_loop(self):
        with mss.mss() as sct:
            while not self.stop_flag:
                if self.running.is_set() and self.roi:
                    screenshot = sct.grab(self.roi)
                    img = np.array(screenshot)
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    if self.apply_threshold.get():
                        gray = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)
                        img_rgb = cv2.adaptiveThreshold(gray, 255,
                                                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                        cv2.THRESH_BINARY, 11, 2)

                    odds_list = self.extract_nesine_odds(img_rgb)
                    if odds_list:
                        self.odds_data = odds_list
                        self.update_ui(img_rgb, odds_list)

                time.sleep(1 / self.fps.get())

    def update_ui(self, img_rgb, odds_list):
        if len(img_rgb.shape) == 2:
            img_rgb = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2RGB)
        img_pil = Image.fromarray(cv2.cvtColor(img_rgb, cv2.COLOR_BGR2RGB))
        img_pil.thumbnail((800, 500))
        imgtk = ImageTk.PhotoImage(img_pil)
        self.label_image.imgtk = imgtk
        self.label_image.configure(image=imgtk)

        self.tree.delete(*self.tree.get_children())
        for odds in odds_list:
            self.tree.insert("", "end", values=odds)

    def extract_nesine_odds(self, img):
        results = self.ocr.ocr(img, cls=True)
        lines = [line[1][0] for res in results for line in res]

        all_odds = []
        for i, text in enumerate(lines):
            if "NESINE" in text.upper():
                odds = []
                for j in range(i + 1, len(lines)):
                    nums = re.findall(r"\d+\.\d+", lines[j])
                    odds.extend(nums)
                    if len(odds) >= 3:
                        all_odds.append(odds[:3])
                        break
        return all_odds if all_odds else None

    # =========================
    # Controls
    # =========================
    def start_stream(self):
        if not self.roi:
            messagebox.showerror("Error", "Please select ROI first.")
            return
        self.running.set()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")
        threading.Thread(target=self.capture_loop, daemon=True).start()

    def pause_stream(self):
        self.running.clear()
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")

    def resume_stream(self):
        self.running.set()
        self.btn_resume.config(state="disabled")
        self.btn_pause.config(state="normal")

    def toggle_gpu(self):
        self.ocr = PaddleOCR(use_textline_orientation=True, lang='en', use_gpu=self.use_gpu.get())
        messagebox.showinfo("OCR", f"OCR restarted with GPU={self.use_gpu.get()}")

    # =========================
    # Export
    # =========================
    def export_csv(self):
        if not self.odds_data:
            messagebox.showerror("Error", "No data to export.")
            return
        df = pd.DataFrame(self.odds_data, columns=["1", "X", "2"])
        df.to_csv("nesine_odds.csv", index=False)
        messagebox.showinfo("Export", "Saved as nesine_odds.csv")

    def export_excel(self):
        if not self.odds_data:
            messagebox.showerror("Error", "No data to export.")
            return
        df = pd.DataFrame(self.odds_data, columns=["1", "X", "2"])
        df.to_excel("nesine_odds.xlsx", index=False)
        messagebox.showinfo("Export", "Saved as nesine_odds.xlsx")

    def on_close(self):
        self.stop_flag = True
        self.running.clear()
        self.root.destroy()


if __name__ == "__main__":
    root = tb.Window(themename="cyborg")
    app = NesineOddsApp(root)
    root.mainloop()
