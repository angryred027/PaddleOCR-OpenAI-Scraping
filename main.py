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
import hashlib
from collections import deque

# -------------------------
# Utility helpers
# -------------------------
def normalize_odds_text(text):
    """
    Normalize OCR raw text into a consistent float-like string.
    - replace comma with dot
    - keep only number + single dot + decimals
    """
    if not text:
        return ""
    text = text.strip()
    text = text.replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return m.group(1) if m else ""

def odds_fingerprint(bookmaker, match_text, market_text, odds_triplet):
    """
    Create a stable fingerprint (hash) for deduplication.
    """
    payload = f"{bookmaker}|{match_text}|{market_text}|{'|'.join(map(str, odds_triplet))}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def mse(a, b):
    """
    Mean squared error between two uint8 images of same shape.
    Used to detect scrolling/changes.
    """
    if a is None or b is None:
        return 1e9
    diff = a.astype("float32") - b.astype("float32")
    return float(np.mean(diff * diff))

# -------------------------
# Main App
# -------------------------
class NesineOddsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NESINE Odds Scraper — Optimized")
        self.root.geometry("1100x740")
        self.root.minsize(900, 640)

        # Theme
        tb.Style("cyborg")

        # ---------- State ----------
        self.running = threading.Event()
        self.stop_flag = False
        self.odds_rows = []               # structured rows for table/export
        self.roi = None
        self.fps = tk.IntVar(value=24)     # requested preview FPS (capped internally)
        self.ocr_every_n = tk.IntVar(value=10)  # run OCR every N frames
        self.use_gpu = tk.BooleanVar(value=False)
        self.apply_threshold = tk.BooleanVar(value=False)  # kept but not used for preview
        self.left_col_ratio = tk.DoubleVar(value=0.3)  # left fraction to scan for "NESINE"

        # PaddleOCR (det + rec + cls). Restarted when GPU toggles
        self.ocr = PaddleOCR(use_textline_orientation=True, lang="en", use_gpu=False)

        # frame counters & buffers
        self.preview_lock = threading.Lock()
        self.frame_count = 0
        self.prev_small = None
        self.change_threshold = 25_000.0  # if MSE between frames > threshold, consider "scrolling"
        self.last_seen_hashes = deque(maxlen=500)  # rolling memory of fingerprints to dedup

        # For storing PhotoImage to avoid GC
        self._latest_preview_imgtk = None

        # ================= Layout =================
        root.grid_rowconfigure(0, weight=7)
        root.grid_rowconfigure(1, weight=3)
        root.grid_columnconfigure(0, weight=1)

        # Top: Preview + Controls
        frame_top = ttk.Frame(root)
        frame_top.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        frame_top.grid_columnconfigure(0, weight=4)  # preview
        frame_top.grid_columnconfigure(1, weight=1)  # controls
        frame_top.grid_rowconfigure(0, weight=1)

        # Preview
        preview_wrapper = ttk.Frame(frame_top)
        preview_wrapper.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        preview_wrapper.grid_rowconfigure(0, weight=1)
        preview_wrapper.grid_columnconfigure(0, weight=1)

        self.label_image = ttk.Label(preview_wrapper, text="ROI Preview", anchor="center")
        self.label_image.grid(row=0, column=0, sticky="nsew")

        # Controls (center-aligned column)
        controls_outer = ttk.Frame(frame_top)
        controls_outer.grid(row=0, column=1, sticky="nsew")

        # center column trick: add stretch rows; center inner frame
        controls_outer.grid_rowconfigure(0, weight=1)
        controls_outer.grid_rowconfigure(2, weight=1)
        controls_outer.grid_columnconfigure(0, weight=1)

        controls = ttk.Frame(controls_outer)
        controls.grid(row=1, column=0)  # centered
        for i in range(2):
            controls.grid_columnconfigure(i, weight=1)

        r = 0
        ttk.Label(controls, text="Controls", font=("", 12, "bold")).grid(row=r, column=0, columnspan=2, pady=(0, 8))
        r += 1

        btn = ttk.Button(controls, text="SELECT ROI", command=self.select_roi, style="success.TButton")
        btn.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self.btn_start = ttk.Button(controls, text="START", command=self.start_stream, style="primary.TButton")
        self.btn_start.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self.btn_pause = ttk.Button(controls, text="PAUSE", command=self.pause_stream, state="disabled")
        self.btn_pause.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self.btn_resume = ttk.Button(controls, text="RESUME", command=self.resume_stream, state="disabled")
        self.btn_resume.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        # FPS
        ttk.Label(controls, text="Capture FPS").grid(row=r, column=0, sticky="e", pady=7, padx=(0, 6))
        self.spin_fps = ttk.Spinbox(controls, from_=1, to=60, textvariable=self.fps, width=6)
        self.spin_fps.grid(row=r, column=1, sticky="w", pady=7)
        r += 1

        # OCR every N
        ttk.Label(controls, text="OCR every N frames").grid(row=r, column=0, sticky="e", pady=7, padx=(0, 6))
        self.spin_skip = ttk.Spinbox(controls, from_=1, to=30, textvariable=self.ocr_every_n, width=6)
        self.spin_skip.grid(row=r, column=1, sticky="w", pady=7)
        r += 1

        # left column ratio
        ttk.Label(controls, text="Left scan ratio (0–0.6)").grid(row=r, column=0, sticky="e", pady=7, padx=(0, 6))
        self.spin_left = ttk.Spinbox(controls, from_=0.10, to=0.60, increment=0.02, textvariable=self.left_col_ratio, width=6)
        self.spin_left.grid(row=r, column=1, sticky="w", pady=7)
        r += 1

        # toggles (left-aligned)
        ttk.Checkbutton(controls, text="Use GPU", variable=self.use_gpu, command=self.toggle_gpu).grid(row=r, column=0, columnspan=2, pady=7, sticky="w")
        r += 1
        ttk.Checkbutton(controls, text="Apply Threshold", variable=self.apply_threshold).grid(row=r, column=0, columnspan=2, pady=7, sticky="w")
        r += 1

        # export
        self.btn_export_csv = ttk.Button(controls, text="Export CSV", command=self.export_csv)
        self.btn_export_csv.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self.btn_export_excel = ttk.Button(controls, text="Export Excel", command=self.export_excel)
        self.btn_export_excel.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        # Bottom: results table
        frame_bottom = ttk.Frame(root)
        frame_bottom.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        frame_bottom.grid_rowconfigure(0, weight=1)
        frame_bottom.grid_columnconfigure(0, weight=1)

        cols = ("bookmaker", "match", "market", "1", "X", "2", "timestamp")
        self.tree = ttk.Treeview(frame_bottom, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Close handling
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

        canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
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
            end_x, end_y = event.x, event.y
            # Convert to absolute screen coords (Tk coordinates are screen coords here)
            left = min(start_x, end_x)
            top = min(start_y, end_y)
            width = abs(end_x - start_x)
            height = abs(end_y - start_y)
            self.roi = {"left": left, "top": top, "width": width, "height": height}
            overlay.destroy()
            messagebox.showinfo("ROI Selected", f"Region: {self.roi}")

        canvas.bind("<ButtonPress-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)

    # =========================
    # Preview loop (raw ROI only) - thread-safe UI updates
    # =========================
    def preview_loop(self):
        # cap preview fps to reasonable value for Tkinter
        max_preview_fps = 30.0
        with mss.mss() as sct:
            while not self.stop_flag:
                if self.running.is_set() and self.roi:
                    start = time.time()
                    try:
                        sshot = sct.grab(self.roi)
                    except Exception:
                        # ROI might be invalid momentarily
                        time.sleep(0.05)
                        continue
                    frame = np.array(sshot)  # BGRA
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    # Prepare image for Tk (do this minimal conversion quickly)
                    img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    img_pil = Image.fromarray(img_rgb)
                    img_pil.thumbnail((880, 540))
                    imgtk = ImageTk.PhotoImage(img_pil)
                    # schedule UI update on main thread
                    self.root.after(0, self._set_preview_image, imgtk)

                    # throttle
                    elapsed = time.time() - start
                    target = 1.0 / min(max_preview_fps, max(1, int(self.fps.get())))
                    sleep_for = max(0.0, target - elapsed)
                    time.sleep(sleep_for)
                else:
                    time.sleep(0.05)

    def _set_preview_image(self, imgtk):
        # Keep a reference or Tk will GC the image
        self._latest_preview_imgtk = imgtk
        self.label_image.configure(image=imgtk)

    # =========================
    # OCR worker loop (separate thread)
    # =========================
    def ocr_loop(self):
        # This loop captures at a lower rate for OCR processing; it still uses mss separately.
        frame_counter = 0
        small_w, small_h = 480, 300  # for change detection
        with mss.mss() as sct:
            while not self.stop_flag:
                if self.running.is_set() and self.roi:
                    frame_counter += 1
                    should_capture = (frame_counter % max(1, int(self.ocr_every_n.get())) == 0)

                    # Grab frame for OCR checks (we capture even when not OCRing to compute change)
                    try:
                        sshot = sct.grab(self.roi)
                    except Exception:
                        time.sleep(0.05)
                        continue
                    frame = np.array(sshot)
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    # optional preproc for change detection only
                    proc_for_change = frame_bgr.copy()
                    if self.apply_threshold.get():
                        gray = cv2.cvtColor(proc_for_change, cv2.COLOR_BGR2GRAY)
                        proc_for_change = cv2.adaptiveThreshold(
                            gray, 255,
                            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                            cv2.THRESH_BINARY, 11, 2
                        )
                        proc_for_change = cv2.cvtColor(proc_for_change, cv2.COLOR_GRAY2BGR)

                    small = cv2.resize(proc_for_change, (small_w, small_h), interpolation=cv2.INTER_AREA)
                    change = mse(self.prev_small, small)
                    self.prev_small = small

                    dynamic_every = max(1, int(self.ocr_every_n.get()))
                    if change >= self.change_threshold:
                        # rapid changes (scroll) → OCR more often
                        dynamic_every = 1

                    if frame_counter % dynamic_every != 0:
                        # skip OCR this cycle
                        time.sleep(0.01)
                        continue

                    # Light-weight check: only scan left column for NESINE
                    h, w = proc_for_change.shape[:2]
                    left_w = int(w * float(self.left_col_ratio.get()))
                    left_col = proc_for_change[:, :max(10, left_w)]

                    nesine_present, nesine_boxes = self.contains_nesine(left_col)
                    if nesine_present:
                        # extract rows with full-row OCR on original full-color image
                        rows = self.extract_rows_from_boxes(frame_bgr, nesine_boxes)
                        if rows:
                            # schedule tree & storage update on main thread
                            self.root.after(0, self.update_table_and_store, rows)
                    else:
                        # no nesine: continue
                        pass

                else:
                    time.sleep(0.05)

    # -------------------------
    # Light "NESINE" detector
    # -------------------------
    def contains_nesine(self, img_bgr):
        """
        Returns (present: bool, boxes: list of (x1,y1,x2,y2)) for NESINE detections in img.
        Uses OCR detections but scans a narrow area only.
        """
        try:
            results = self.ocr.ocr(img_bgr, cls=True)
        except Exception:
            return False, []
        boxes = []
        for res in results:
            for line in res:
                text = line[1][0]
                if not text:
                    continue
                # Turkish dotted I handling
                if "NESINE" in text.upper().replace("İ", "I"):
                    # bbox format [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                    box = line[0]
                    xs = [int(p[0]) for p in box]
                    ys = [int(p[1]) for p in box]
                    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                    boxes.append((x1, y1, x2, y2))
        return (len(boxes) > 0), boxes

    # -------------------------
    # Row extraction around NESINE
    # -------------------------
    def extract_rows_from_boxes(self, full_img_bgr, nesine_boxes):
        """
        For each NESINE detection box, expand to full-row crop and OCR that region only.
        Returns a list of structured dicts for unique rows.
        """
        h, w = full_img_bgr.shape[:2]
        rows_out = []

        for (x1, y1, x2, y2) in nesine_boxes:
            # expand vertically to include the full row height band
            row_pad_y = int(0.8 * (y2 - y1)) + 6
            ry1 = max(0, y1 - row_pad_y)
            ry2 = min(h, y2 + row_pad_y)
            # expand horizontally to entire table width within ROI
            rx1 = 0
            rx2 = w

            row_crop = full_img_bgr[ry1:ry2, rx1:rx2]
            if row_crop.size == 0:
                continue

            try:
                res = self.ocr.ocr(row_crop, cls=True)
            except Exception:
                continue

            # collect all text lines for parsing
            lines = [line[1][0] for r in res for line in r]

            bookmaker = "NESINE"
            odds = []
            match_text = ""
            market_text = ""

            # Build a flattened list of (text, bbox_center_x, bbox_center_y)
            flattened = []
            for r in res:
                for line in r:
                    text = line[1][0]
                    box = line[0]
                    xs = [int(p[0]) for p in box]
                    ys = [int(p[1]) for p in box]
                    cx = (min(xs) + max(xs)) // 2
                    cy = (min(ys) + max(ys)) // 2
                    flattened.append((text, cx, cy))

            # sort by y (rows) then x to approximate left→right reading
            flattened.sort(key=lambda t: (t[2] // 50, t[1]))

            # Simple heuristics: collect numbers that look like odds
            for t, _, _ in flattened:
                if not t:
                    continue
                # skip the bookmaker token itself
                if "NESINE" in t.upper().replace("İ", "I"):
                    continue
                nums = re.findall(r"\d+[.,]\d+", t)
                for n in nums:
                    n_norm = normalize_odds_text(n)
                    if n_norm:
                        odds.append(n_norm)
                if len(odds) >= 3:
                    break

            # Fallback: if not enough odds, try entire row aggregated text
            if len(odds) < 3:
                blob = " ".join(lines)
                nums = re.findall(r"\d+[.,]\d+", blob)
                odds = [normalize_odds_text(n) for n in nums][:3]

            if len(odds) >= 3:
                # infer match/market from non-numeric tokens
                nonnums = [t for t, _, _ in flattened if t and not re.search(r"\d", t)]
                if nonnums:
                    match_text = nonnums[0][:60]
                    if len(nonnums) > 1:
                        market_text = nonnums[1][:60]

                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                triplet = odds[:3]
                fp = odds_fingerprint(bookmaker, match_text, market_text, triplet)
                if fp in self.last_seen_hashes:
                    continue
                self.last_seen_hashes.append(fp)

                row = {
                    "bookmaker": bookmaker,
                    "match": match_text,
                    "market": market_text,
                    "1": triplet[0],
                    "X": triplet[1],
                    "2": triplet[2],
                    "timestamp": ts
                }
                rows_out.append(row)

        return rows_out

    # =========================
    # UI updates & storage (main-thread safe)
    # =========================
    def update_table_and_store(self, rows):
        for row in rows:
            self.odds_rows.append(row)
            self.tree.insert("", "end", values=(
                row["bookmaker"], row["match"], row["market"], row["1"], row["X"], row["2"], row["timestamp"]
            ))

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

        # Start preview and OCR threads (daemon)
        t_preview = threading.Thread(target=self.preview_loop, daemon=True)
        t_ocr = threading.Thread(target=self.ocr_loop, daemon=True)
        t_preview.start()
        t_ocr.start()

    def pause_stream(self):
        self.running.clear()
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")

    def resume_stream(self):
        self.running.set()
        self.btn_resume.config(state="disabled")
        self.btn_pause.config(state="normal")

    def toggle_gpu(self):
        # Reinitialize OCR engine with/without GPU
        try:
            use_gpu_flag = self.use_gpu.get()
            self.ocr = PaddleOCR(use_textline_orientation=True, lang="en", use_gpu=use_gpu_flag)
            messagebox.showinfo("OCR", f"OCR restarted with GPU={use_gpu_flag}")
        except Exception as e:
            messagebox.showerror("OCR", f"Failed to init OCR with GPU={self.use_gpu.get()}:\n{e}")
            self.use_gpu.set(False)

    # =========================
    # Exporters
    # =========================
    def export_csv(self):
        if not self.odds_rows:
            messagebox.showerror("Error", "No data to export.")
            return
        df = pd.DataFrame(self.odds_rows)
        df.to_csv("nesine_odds.csv", index=False, encoding="utf-8-sig")
        messagebox.showinfo("Export", "Saved as nesine_odds.csv")

    def export_excel(self):
        if not self.odds_rows:
            messagebox.showerror("Error", "No data to export.")
            return
        df = pd.DataFrame(self.odds_rows)
        df.to_excel("nesine_odds.xlsx", index=False)
        messagebox.showinfo("Export", "Saved as nesine_odds.xlsx")

    def on_close(self):
        self.stop_flag = True
        self.running.clear()
        # Allow threads a moment to stop gracefully
        time.sleep(0.1)
        self.root.destroy()


if __name__ == "__main__":
    root = tb.Window(themename="cyborg")
    app = NesineOddsApp(root)
    root.mainloop()
