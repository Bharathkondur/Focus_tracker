"""
Focus Tracker — polished daily goal tracker for Windows.

Layout:
  Left sidebar  — manage goals (add / delete, color-coded)
  Right panel   — month calendar + daily view
                  · progress bar
                  · tick-off each goal
                  · notes textarea with save

Data (JSON next to the script):
  {
    "goals": [{"id", "title", "desc", "color", "active", "created"}, ...],
    "days":  {"YYYY-MM-DD": {"ticks": {"goal_id": bool}, "note": ""}}
  }
"""

import json, os, sys, uuid, calendar, tkinter.font as tkfont
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox

# ─── paths ────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(BASE_DIR, "focus_tracker_data.json")

# ─── design tokens ────────────────────────────────────────────────────────────
BG      = "#EEF2FF"
CARD    = "#FFFFFF"
ACCENT  = "#4F6BED"
SUCCESS = "#22C55E"
WARN    = "#F59E0B"
ORANGE  = "#FB923C"
DANGER  = "#EF4444"
TEXT    = "#1E293B"
SUBTEXT = "#64748B"
BORDER  = "#CBD5E1"
STRIPE  = "#F8FAFC"

PALETTE = ["#4F6BED","#7C3AED","#EC4899","#F59E0B",
           "#22C55E","#14B8A6","#EF4444","#8B5CF6"]

# ─── data helpers ─────────────────────────────────────────────────────────────

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"goals": [], "days": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("goals", [])
        d.setdefault("days", {})
        return d
    except Exception:
        return {"goals": [], "days": {}}

def save_data(data):
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DATA_FILE)
    except OSError as e:
        messagebox.showerror("Focus Tracker", f"Save failed:\n{e}")

def dkey(d: date) -> str:
    return d.isoformat()

def active_goals(data):
    return [g for g in data["goals"] if g.get("active", True)]

def day_progress(data, d: date):
    goals = active_goals(data)
    if not goals:
        return 0, 0
    ticks = data["days"].get(dkey(d), {}).get("ticks", {})
    done = sum(1 for g in goals if ticks.get(g["id"], False))
    return done, len(goals)

def cell_color(data, d: date):
    if d > date.today():
        return "#DDE3F0"
    done, total = day_progress(data, d)
    if total == 0:
        return "#DDE3F0"
    r = done / total
    if r == 1.0: return SUCCESS
    if r >= 0.5: return WARN
    if r >  0.0: return ORANGE
    return DANGER

def calc_streak(data):
    streak, d = 0, date.today()
    while True:
        done, total = day_progress(data, d)
        if total > 0 and done > 0:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return streak


# ─── tiny custom widgets ──────────────────────────────────────────────────────

class RoundedBar(tk.Canvas):
    """Flat rounded progress bar drawn on canvas."""
    def __init__(self, parent, height=10, **kw):
        super().__init__(parent, height=height, bg=CARD,
                         highlightthickness=0, **kw)
        self._pct = 0.0
        self.bind("<Configure>", lambda _e: self._redraw())

    def set(self, pct: float):
        self._pct = max(0.0, min(1.0, pct))
        self._redraw()

    def _redraw(self):
        self.delete("all")
        W = self.winfo_width()
        H = self.winfo_height()
        if W < 2:
            return
        r = H // 2
        # track
        self._rrect(2, 2, W - 2, H - 2, r, fill="#E2E8F0", outline="")
        # fill
        if self._pct > 0:
            fw = max(H, int((W - 4) * self._pct) + 2)
            clr = (SUCCESS if self._pct == 1.0
                   else WARN if self._pct >= 0.5
                   else ACCENT)
            self._rrect(2, 2, fw, H - 2, r, fill=clr, outline="")

    def _rrect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1,  x2,y1+r,
               x2,y2-r,  x2,y2,  x2-r,y2, x1+r,y2,
               x1,y2,   x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(pts, smooth=True, **kw)


# ─── main application ─────────────────────────────────────────────────────────

class App:

    DAY_HDR = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Focus Tracker")
        self.root.geometry("960x700")
        self.root.minsize(800, 580)
        self.root.configure(bg=BG)

        self.data = load_data()
        self.today = date.today()
        self.sel   = self.today
        self.view_y = self.today.year
        self.view_m = self.today.month

        self._fonts()
        self._build()
        self._refresh()

    # ── fonts ─────────────────────────────────────────────────────────────────

    def _fonts(self):
        self.f_h1     = tkfont.Font(family="Segoe UI", size=17, weight="bold")
        self.f_h2     = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.f_h3     = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body   = tkfont.Font(family="Segoe UI", size=10)
        self.f_small  = tkfont.Font(family="Segoe UI", size=9)
        self.f_micro  = tkfont.Font(family="Segoe UI", size=8)
        self.f_strike = tkfont.Font(family="Segoe UI", size=10, overstrike=True)
        self.f_mono   = tkfont.Font(family="Consolas",  size=10)

    # ── layout skeleton ───────────────────────────────────────────────────────

    def _build(self):
        # ── header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=ACCENT, padx=20, pady=12)
        hdr.pack(fill="x")

        tk.Label(hdr, text="🎯  Focus Tracker",
                 bg=ACCENT, fg="white", font=self.f_h1).pack(side="left")

        self.streak_lbl = tk.Label(hdr, text="", bg=ACCENT, fg="#C7D2FE",
                                   font=self.f_small)
        self.streak_lbl.pack(side="right", padx=(0, 4))

        # ── body: sidebar | main ─────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        # sidebar (fixed width)
        self._sb = tk.Frame(body, bg=BG, width=220)
        self._sb.pack(side="left", fill="y", padx=(0, 12))
        self._sb.pack_propagate(False)

        # right column
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_sidebar(self._sb)
        self._build_right(right)

    # ── sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        tk.Label(parent, text="MY GOALS", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", pady=(4, 6))

        # goals list — scrollable white card
        list_card = tk.Frame(parent, bg=CARD,
                             highlightthickness=1, highlightbackground=BORDER)
        list_card.pack(fill="both", expand=True)

        self._gl_canvas = tk.Canvas(list_card, bg=CARD,
                                    highlightthickness=0, bd=0)
        gl_sb = ttk.Scrollbar(list_card, orient="vertical",
                              command=self._gl_canvas.yview)
        self._gl_canvas.configure(yscrollcommand=gl_sb.set)
        self._gl_canvas.pack(side="left", fill="both", expand=True)
        gl_sb.pack(side="right", fill="y")

        self._gl_frame = tk.Frame(self._gl_canvas, bg=CARD)
        self._gl_win   = self._gl_canvas.create_window(
            (0, 0), window=self._gl_frame, anchor="nw")
        self._gl_frame.bind("<Configure>", lambda _e: self._gl_canvas.configure(
            scrollregion=self._gl_canvas.bbox("all")))
        self._gl_canvas.bind("<Configure>", lambda e: self._gl_canvas.itemconfigure(
            self._gl_win, width=e.width))

        # add goal button
        add_btn = tk.Button(parent, text="＋  Add Goal",
                            bg=ACCENT, fg="white", bd=0, cursor="hand2",
                            font=self.f_h3, pady=9,
                            activebackground="#3B55D9", activeforeground="white",
                            command=self._add_goal_dialog)
        add_btn.pack(fill="x", pady=(10, 0))

    def _render_sidebar(self):
        for w in self._gl_frame.winfo_children():
            w.destroy()

        goals = active_goals(self.data)
        if not goals:
            tk.Label(self._gl_frame,
                     text="No goals yet.\nClick 'Add Goal' below.",
                     bg=CARD, fg=SUBTEXT, font=self.f_small,
                     justify="center").pack(pady=28)
            return

        for g in goals:
            row = tk.Frame(self._gl_frame, bg=CARD, cursor="hand2")
            row.pack(fill="x")

            # left color accent bar
            tk.Frame(row, width=5, bg=g.get("color", ACCENT)).pack(
                side="left", fill="y")

            inner = tk.Frame(row, bg=CARD, padx=10, pady=9)
            inner.pack(side="left", fill="both", expand=True)

            tk.Label(inner, text=g["title"], bg=CARD, fg=TEXT,
                     font=self.f_h3, anchor="w").pack(fill="x")
            if g.get("desc"):
                tk.Label(inner, text=g["desc"], bg=CARD, fg=SUBTEXT,
                         font=self.f_micro, anchor="w",
                         wraplength=150, justify="left").pack(fill="x")

            tk.Button(row, text="✕", bg=CARD, fg="#CBD5E1",
                      activebackground="#FEE2E2", activeforeground=DANGER,
                      font=self.f_micro, bd=0, cursor="hand2", padx=6,
                      command=lambda gid=g["id"]: self._delete_goal(gid)
                      ).pack(side="right", padx=(0, 6))

            tk.Frame(self._gl_frame, bg=BORDER, height=1).pack(fill="x")

    # ── right panel ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        # calendar card (top, fixed height area)
        cal_card = tk.Frame(parent, bg=CARD,
                            highlightthickness=1, highlightbackground=BORDER)
        cal_card.pack(fill="x", pady=(0, 10))

        self._cal_inner = tk.Frame(cal_card, bg=CARD, padx=16, pady=12)
        self._cal_inner.pack(fill="both", expand=True)
        self._build_cal_shell()

        # day panel (expands to fill remaining space)
        day_card = tk.Frame(parent, bg=CARD,
                            highlightthickness=1, highlightbackground=BORDER)
        day_card.pack(fill="both", expand=True)

        day_wrap = tk.Frame(day_card, bg=CARD, padx=16, pady=14)
        day_wrap.pack(fill="both", expand=True)
        self._build_day_shell(day_wrap)

    # ── calendar shell (static widgets; grid cells rebuilt on month change) ───

    def _build_cal_shell(self):
        p = self._cal_inner

        # nav row
        nav = tk.Frame(p, bg=CARD)
        nav.pack(fill="x", pady=(0, 10))

        tk.Button(nav, text="◀", bg=CARD, fg=SUBTEXT, bd=0,
                  font=("Segoe UI", 12), cursor="hand2",
                  activebackground=BG,
                  command=lambda: self._shift_month(-1)).pack(side="left")

        self._month_lbl = tk.Label(nav, text="", bg=CARD, fg=TEXT,
                                   font=self.f_h2, anchor="center")
        self._month_lbl.pack(side="left", expand=True, fill="x")

        tk.Button(nav, text="▶", bg=CARD, fg=SUBTEXT, bd=0,
                  font=("Segoe UI", 12), cursor="hand2",
                  activebackground=BG,
                  command=lambda: self._shift_month(1)).pack(side="right")

        # grid host
        self._cal_grid = tk.Frame(p, bg=CARD)
        self._cal_grid.pack(fill="x")

        # legend
        leg = tk.Frame(p, bg=CARD)
        leg.pack(anchor="w", pady=(10, 0))
        for clr, lbl in [(SUCCESS,"All done"),(WARN,"Partial"),
                         (ORANGE,"Started"),(DANGER,"None done"),
                         ("#DDE3F0","No goals / future")]:
            self._swatch(leg, clr, lbl)

    def _swatch(self, parent, color, text):
        f = tk.Frame(parent, bg=CARD)
        f.pack(side="left", padx=(0, 14))
        tk.Frame(f, width=11, height=11, bg=color).pack(side="left", padx=(0,4))
        tk.Label(f, text=text, bg=CARD, fg=SUBTEXT, font=self.f_micro).pack(side="left")

    # ── day panel shell ────────────────────────────────────────────────────────

    def _build_day_shell(self, parent):
        parent.rowconfigure(3, weight=1)
        parent.columnconfigure(0, weight=1)

        # row 0: day title + today button
        hdr = tk.Frame(parent, bg=CARD)
        hdr.grid(row=0, column=0, sticky="ew")

        self._day_lbl = tk.Label(hdr, text="", bg=CARD, fg=TEXT,
                                 font=self.f_h2, anchor="w")
        self._day_lbl.pack(side="left")

        tk.Button(hdr, text="Go to Today", bg="#EEF2FF", fg=ACCENT,
                  activebackground="#C7D2FE", activeforeground=ACCENT,
                  bd=0, font=self.f_small, padx=10, pady=4, cursor="hand2",
                  command=self._jump_to_today).pack(side="right")

        # row 1: progress bar
        prog_row = tk.Frame(parent, bg=CARD)
        prog_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        prog_row.columnconfigure(0, weight=1)

        self._prog_bar = RoundedBar(prog_row, height=10)
        self._prog_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self._prog_lbl = tk.Label(prog_row, text="", bg=CARD, fg=SUBTEXT,
                                  font=self.f_small, width=12, anchor="e")
        self._prog_lbl.grid(row=0, column=1)

        # row 2: column headers
        col_hdr = tk.Frame(parent, bg=CARD)
        col_hdr.grid(row=2, column=0, sticky="ew", pady=(12, 4))
        col_hdr.columnconfigure(0, weight=3)
        col_hdr.columnconfigure(1, weight=2)

        tk.Label(col_hdr, text="GOALS", bg=CARD, fg=SUBTEXT,
                 font=self.f_micro).grid(row=0, column=0, sticky="w")
        tk.Label(col_hdr, text="📝  PROGRESS NOTES", bg=CARD, fg=SUBTEXT,
                 font=self.f_micro).grid(row=0, column=1, sticky="w", padx=(16, 0))

        # row 3: ticks + notes side by side (expands)
        cols = tk.Frame(parent, bg=CARD)
        cols.grid(row=3, column=0, sticky="nsew")
        cols.rowconfigure(0, weight=1)
        cols.columnconfigure(0, weight=3)
        cols.columnconfigure(1, weight=2)

        # ticks
        tick_host = tk.Frame(cols, bg=CARD)
        tick_host.grid(row=0, column=0, sticky="nsew")
        tick_host.rowconfigure(0, weight=1)
        tick_host.columnconfigure(0, weight=1)

        self._tick_canvas = tk.Canvas(tick_host, bg=CARD, highlightthickness=0)
        tick_sb = ttk.Scrollbar(tick_host, orient="vertical",
                                command=self._tick_canvas.yview)
        self._tick_canvas.configure(yscrollcommand=tick_sb.set)
        self._tick_canvas.grid(row=0, column=0, sticky="nsew")
        tick_sb.grid(row=0, column=1, sticky="ns")

        self._tick_frame = tk.Frame(self._tick_canvas, bg=CARD)
        self._tf_win = self._tick_canvas.create_window(
            (0, 0), window=self._tick_frame, anchor="nw")
        self._tick_frame.bind("<Configure>", lambda _e: self._tick_canvas.configure(
            scrollregion=self._tick_canvas.bbox("all")))
        self._tick_canvas.bind("<Configure>", lambda e: self._tick_canvas.itemconfigure(
            self._tf_win, width=e.width))

        # notes
        notes_host = tk.Frame(cols, bg=CARD)
        notes_host.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        notes_host.rowconfigure(0, weight=1)
        notes_host.columnconfigure(0, weight=1)

        self._note_text = tk.Text(
            notes_host, bg=STRIPE, fg=TEXT, font=self.f_body,
            relief="flat", padx=10, pady=8, wrap="word",
            highlightthickness=1, highlightbackground=BORDER,
            insertbackground=ACCENT, spacing3=2,
        )
        self._note_text.grid(row=0, column=0, sticky="nsew")

        note_sb = ttk.Scrollbar(notes_host, orient="vertical",
                                command=self._note_text.yview)
        self._note_text.configure(yscrollcommand=note_sb.set)
        note_sb.grid(row=0, column=1, sticky="ns")

        # save note button
        self._save_btn = tk.Button(
            notes_host, text="💾  Save Note",
            bg=ACCENT, fg="white", bd=0, cursor="hand2",
            font=self.f_small, padx=12, pady=5,
            activebackground="#3B55D9", activeforeground="white",
            command=self._save_note,
        )
        self._save_btn.grid(row=1, column=0, sticky="e", pady=(6, 0))

    # ── calendar render ────────────────────────────────────────────────────────

    def _shift_month(self, delta):
        m = self.view_m + delta
        y = self.view_y
        while m < 1:  m += 12; y -= 1
        while m > 12: m -= 12; y += 1
        self.view_y, self.view_m = y, m
        self._render_calendar()

    def _jump_to_today(self):
        self.today = date.today()
        self.view_y = self.today.year
        self.view_m = self.today.month
        self.sel    = self.today
        self._refresh()

    def _render_calendar(self):
        for w in self._cal_grid.winfo_children():
            w.destroy()

        self._month_lbl.config(
            text=f"{calendar.month_name[self.view_m]}   {self.view_y}")

        for ci, d in enumerate(self.DAY_HDR):
            tk.Label(self._cal_grid, text=d, bg=CARD, fg=SUBTEXT,
                     font=self.f_micro, width=4, anchor="center").grid(
                row=0, column=ci, padx=2, pady=(0, 6))
            self._cal_grid.columnconfigure(ci, weight=1)

        cal = calendar.Calendar(firstweekday=0)
        today = date.today()

        for ri, week in enumerate(
                cal.monthdayscalendar(self.view_y, self.view_m), 1):
            for ci, day in enumerate(week):
                if day == 0:
                    tk.Frame(self._cal_grid, bg=BG, width=36,
                             height=32).grid(row=ri, column=ci, padx=2, pady=2)
                    continue

                d = date(self.view_y, self.view_m, day)
                bg  = cell_color(self.data, d)
                is_today = (d == today)
                is_sel   = (d == self.sel)

                if is_today or is_sel:
                    outer = tk.Frame(self._cal_grid, bg=ACCENT,
                                     padx=2, pady=2)
                else:
                    outer = tk.Frame(self._cal_grid, bg=BG)
                outer.grid(row=ri, column=ci, padx=2, pady=2, sticky="nsew")

                # text colour based on background
                fg = TEXT
                if bg in (SUCCESS, DANGER, ORANGE):
                    fg = "white"

                lbl = tk.Label(outer, text=str(day), bg=bg, fg=fg,
                               font=self.f_h3 if is_today else self.f_small,
                               width=3, anchor="center",
                               cursor="hand2", pady=5)
                lbl.pack(fill="both", expand=True)
                lbl.bind("<Button-1>", lambda _e, dd=d: self._on_day(dd))
                outer.bind("<Button-1>", lambda _e, dd=d: self._on_day(dd))

    def _on_day(self, d: date):
        self.sel = d
        self._render_calendar()
        self._render_day()

    # ── day panel render ──────────────────────────────────────────────────────

    def _render_day(self):
        d = self.sel
        prefix = "Today" if d == date.today() else d.strftime("%A")
        self._day_lbl.config(text=f"{prefix}  ·  {d.strftime('%B %d, %Y')}")

        done, total = day_progress(self.data, d)
        pct = done / total if total else 0.0
        self._prog_bar.set(pct)
        if total:
            pct_str = f"{int(pct*100)}%  ({done}/{total})"
        else:
            pct_str = "no goals"
        self._prog_lbl.config(text=pct_str)

        # ── ticks ──────────────────────────────────────────────────────────
        for w in self._tick_frame.winfo_children():
            w.destroy()

        goals = active_goals(self.data)
        k     = dkey(d)
        ticks = self.data["days"].get(k, {}).get("ticks", {})
        is_future = d > date.today()

        if not goals:
            tk.Label(self._tick_frame,
                     text="Add goals\nin the sidebar →",
                     bg=CARD, fg=SUBTEXT, font=self.f_body,
                     justify="center").pack(pady=24)
        else:
            for g in goals:
                checked = ticks.get(g["id"], False)
                gcolor  = g.get("color", ACCENT)

                row = tk.Frame(self._tick_frame, bg=CARD)
                row.pack(fill="x", pady=1)

                # checkbox canvas
                box = tk.Canvas(row, width=22, height=22, bg=CARD,
                                highlightthickness=0,
                                cursor="hand2" if not is_future else "")
                box.pack(side="left", padx=(4, 8), pady=6)

                def _draw(c=box, chk=checked, col=gcolor):
                    c.delete("all")
                    if chk:
                        c.create_rectangle(2, 2, 20, 20,
                                           fill=col, outline=col, width=0)
                        c.create_text(11, 11, text="✓",
                                      fill="white", font=self.f_h3)
                    else:
                        c.create_rectangle(2, 2, 20, 20,
                                           fill=CARD, outline=BORDER, width=2)
                _draw()

                # title label
                lbl_font = self.f_strike if checked else self.f_body
                lbl_fg   = SUBTEXT      if checked else TEXT
                lbl = tk.Label(row, text=g["title"], bg=CARD,
                               fg=lbl_fg, font=lbl_font, anchor="w")
                lbl.pack(side="left", fill="x", expand=True)

                # color pip at right
                tk.Frame(row, width=6, height=22,
                         bg=gcolor).pack(side="right", padx=(0, 6))

                # divider
                tk.Frame(self._tick_frame, bg=BORDER, height=1).pack(fill="x")

                # toggle logic
                if not is_future:
                    def _make_toggle(gid, canvas, title_lbl, color):
                        state = [ticks.get(gid, False)]

                        def toggle(_e=None):
                            state[0] = not state[0]
                            self.data["days"].setdefault(k, {"ticks": {}, "note": ""})
                            self.data["days"][k].setdefault("ticks", {})
                            self.data["days"][k]["ticks"][gid] = state[0]
                            save_data(self.data)
                            # redraw checkbox
                            canvas.delete("all")
                            if state[0]:
                                canvas.create_rectangle(2,2,20,20,
                                    fill=color, outline=color, width=0)
                                canvas.create_text(11,11, text="✓",
                                    fill="white", font=self.f_h3)
                            else:
                                canvas.create_rectangle(2,2,20,20,
                                    fill=CARD, outline=BORDER, width=2)
                            title_lbl.config(
                                font=self.f_strike if state[0] else self.f_body,
                                fg=SUBTEXT if state[0] else TEXT)
                            # update progress
                            dn, tot = day_progress(self.data, self.sel)
                            p = dn/tot if tot else 0
                            self._prog_bar.set(p)
                            self._prog_lbl.config(
                                text=f"{int(p*100)}%  ({dn}/{tot})" if tot else "no goals")
                            self._update_streak()
                            self._render_calendar()

                        return toggle

                    fn = _make_toggle(g["id"], box, lbl, gcolor)
                    box.bind("<Button-1>", fn)
                    lbl.bind("<Button-1>", fn)
                    row.bind("<Button-1>", fn)

        # ── notes ─────────────────────────────────────────────────────────
        self._note_text.configure(state="normal")
        self._note_text.delete("1.0", "end")
        note = self.data["days"].get(k, {}).get("note", "")
        if note:
            self._note_text.insert("1.0", note)

        if is_future:
            self._note_text.configure(state="disabled", bg="#F1F5F9")
            self._save_btn.configure(state="disabled", bg="#94A3B8")
        else:
            self._note_text.configure(state="normal", bg=STRIPE)
            self._save_btn.configure(state="normal", bg=ACCENT)

    def _save_note(self):
        k = dkey(self.sel)
        self.data["days"].setdefault(k, {"ticks": {}, "note": ""})
        self.data["days"][k]["note"] = self._note_text.get("1.0", "end").rstrip()
        save_data(self.data)
        self._save_btn.config(text="✓  Saved!", bg=SUCCESS)
        self.root.after(1400, lambda: self._save_btn.config(
            text="💾  Save Note", bg=ACCENT))

    # ── goal management ────────────────────────────────────────────────────────

    def _add_goal_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("New Goal")
        dlg.geometry("400x290")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.grab_set()

        # center on parent
        self.root.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 400) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 290) // 2
        dlg.geometry(f"400x290+{px}+{py}")

        tk.Label(dlg, text="Add a New Goal", bg=BG, fg=TEXT,
                 font=self.f_h2).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(dlg, text="Track this goal every day on the calendar.",
                 bg=BG, fg=SUBTEXT, font=self.f_small).pack(anchor="w", padx=24)

        tk.Label(dlg, text="Title *", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", padx=24, pady=(14, 2))
        title_var = tk.StringVar()
        title_e = tk.Entry(dlg, textvariable=title_var, bg=CARD, fg=TEXT,
                           font=self.f_body, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER,
                           insertbackground=ACCENT)
        title_e.pack(fill="x", padx=24, ipady=7)
        title_e.focus_set()

        tk.Label(dlg, text="Short description (optional)", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", padx=24, pady=(10, 2))
        desc_var = tk.StringVar()
        desc_e = tk.Entry(dlg, textvariable=desc_var, bg=CARD, fg=TEXT,
                          font=self.f_body, relief="flat", bd=0,
                          highlightthickness=1, highlightbackground=BORDER,
                          insertbackground=ACCENT)
        desc_e.pack(fill="x", padx=24, ipady=6)

        # colour swatches
        swatch_row = tk.Frame(dlg, bg=BG)
        swatch_row.pack(anchor="w", padx=24, pady=(12, 0))
        tk.Label(swatch_row, text="Colour:", bg=BG, fg=SUBTEXT,
                 font=self.f_small).pack(side="left", padx=(0, 10))

        default_idx = len(self.data["goals"]) % len(PALETTE)
        chosen = [PALETTE[default_idx]]
        frames = []

        def pick(c, idx):
            chosen[0] = c
            for j, fr in enumerate(frames):
                fr.config(bd=3 if j == idx else 1,
                          relief="solid" if j == idx else "flat",
                          highlightthickness=2 if j == idx else 0,
                          highlightbackground=TEXT if j == idx else BORDER)

        for i, c in enumerate(PALETTE):
            fr = tk.Frame(swatch_row, width=20, height=20, bg=c,
                          cursor="hand2",
                          bd=3 if i == default_idx else 1,
                          relief="solid" if i == default_idx else "flat",
                          highlightthickness=2 if i == default_idx else 0,
                          highlightbackground=TEXT if i == default_idx else BORDER)
            fr.pack(side="left", padx=3)
            fr.bind("<Button-1>", lambda _e, cc=c, ii=i: pick(cc, ii))
            frames.append(fr)

        # buttons
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(fill="x", padx=24, pady=(16, 0))

        def confirm(_e=None):
            t = title_var.get().strip()
            if not t:
                title_e.configure(highlightbackground=DANGER,
                                  highlightthickness=2)
                return
            self.data["goals"].append({
                "id":      str(uuid.uuid4()),
                "title":   t,
                "desc":    desc_var.get().strip(),
                "color":   chosen[0],
                "active":  True,
                "created": dkey(date.today()),
            })
            save_data(self.data)
            dlg.destroy()
            self._refresh()

        title_e.bind("<Return>", confirm)
        desc_e.bind("<Return>", confirm)

        tk.Button(btn_row, text="Cancel", bg=BG, fg=SUBTEXT, bd=0,
                  font=self.f_body, cursor="hand2",
                  activebackground="#E2E8F0",
                  command=dlg.destroy).pack(side="left")
        tk.Button(btn_row, text="Add Goal →", bg=ACCENT, fg="white",
                  bd=0, font=self.f_h3, padx=18, pady=8, cursor="hand2",
                  activebackground="#3B55D9", activeforeground="white",
                  command=confirm).pack(side="right")

    def _delete_goal(self, gid):
        name = next((g["title"] for g in self.data["goals"]
                     if g["id"] == gid), "goal")
        if not messagebox.askyesno(
                "Delete Goal",
                f"Delete '{name}'?\n\nIt will be removed from all days.",
                parent=self.root):
            return
        self.data["goals"] = [g for g in self.data["goals"] if g["id"] != gid]
        save_data(self.data)
        self._refresh()

    # ── streak + full refresh ─────────────────────────────────────────────────

    def _update_streak(self):
        s = calc_streak(self.data)
        self.streak_lbl.config(
            text=f"🔥  {s}-day streak" if s > 1
            else ("🔥  1-day streak" if s == 1 else ""))

    def _refresh(self):
        self.today = date.today()
        self._update_streak()
        self._render_sidebar()
        self._render_calendar()
        self._render_day()


# ─── entry ────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.resizable(True, True)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
