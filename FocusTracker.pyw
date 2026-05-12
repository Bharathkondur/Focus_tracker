"""
Focus Tracker — daily goal tracker for Windows.

Left sidebar  : goal list (click any goal → detail view)
Right panel   : [Main]   calendar + daily ticks + day notes
              : [Detail] per-goal analytics, heatmap, charts, notes
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
PALETTE = ["#4F6BED","#7C3AED","#EC4899","#F59E0B","#22C55E","#14B8A6","#EF4444","#8B5CF6"]

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
    if total == 0: return "#DDE3F0"
    r = done / total
    if r == 1.0: return SUCCESS
    if r >= 0.5: return WARN
    if r > 0.0:  return ORANGE
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

# ─── analytics ────────────────────────────────────────────────────────────────

def hex_lighten(c, f=0.78):
    c = c.lstrip("#")
    r, g, b = int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r+(255-r)*f), int(g+(255-g)*f), int(b+(255-b)*f))

def goal_analytics(data, gid):
    g_obj = next((g for g in data["goals"] if g["id"] == gid), None)
    if not g_obj:
        return None
    try:
        created = date.fromisoformat(g_obj.get("created", dkey(date.today())))
    except ValueError:
        created = date.today()
    today = date.today()

    all_days = []
    d = created
    while d <= today:
        all_days.append(d)
        d += timedelta(days=1)

    ticked = set()
    for day in all_days:
        if data["days"].get(dkey(day), {}).get("ticks", {}).get(gid, False):
            ticked.add(day)

    total = len(all_days)
    done  = len(ticked)
    rate  = done / total if total else 0.0

    streak, d = 0, today
    while d >= created:
        if d in ticked:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    best = cur = 0
    for day in all_days:
        if day in ticked:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0

    m_start = today.replace(day=1)
    m_days  = [d for d in all_days if d >= m_start]
    m_done  = sum(1 for d in m_days if d in ticked)

    monthly = {}
    for i in range(5, -1, -1):
        mo = today.month - i
        yr = today.year
        while mo <= 0:
            mo += 12
            yr -= 1
        key = f"{yr}-{mo:02d}"
        monthly[key] = {"total": 0, "done": 0, "label": date(yr, mo, 1).strftime("%b")}
    for day in all_days:
        key = day.strftime("%Y-%m")
        if key in monthly:
            monthly[key]["total"] += 1
            if day in ticked:
                monthly[key]["done"] += 1

    dow = {i: {"total": 0, "done": 0} for i in range(7)}
    for day in all_days:
        dow[day.weekday()]["total"] += 1
        if day in ticked:
            dow[day.weekday()]["done"] += 1

    notes = []
    for k, v in sorted(data["days"].items(), reverse=True):
        note = v.get("note", "").strip()
        if note:
            try:
                d2 = date.fromisoformat(k)
                if created <= d2 <= today:
                    notes.append({
                        "date":   d2,
                        "note":   note,
                        "ticked": v.get("ticks", {}).get(gid, False),
                    })
            except ValueError:
                pass

    return {
        "total": total, "done": done, "rate": rate,
        "streak": streak, "best_streak": best,
        "month_done": m_done, "month_total": len(m_days),
        "monthly": monthly, "dow": dow,
        "ticked": ticked, "created": created, "notes": notes,
    }

# ─── widgets ──────────────────────────────────────────────────────────────────

class RoundedBar(tk.Canvas):
    def __init__(self, parent, height=10, **kw):
        super().__init__(parent, height=height, bg=CARD, highlightthickness=0, **kw)
        self._pct = 0.0
        self.bind("<Configure>", lambda _e: self._redraw())

    def set(self, pct):
        self._pct = max(0.0, min(1.0, pct))
        self._redraw()

    def _redraw(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 2: return
        r = H // 2
        self._rr(2, 2, W-2, H-2, r, fill="#E2E8F0", outline="")
        if self._pct > 0:
            fw = max(H, int((W-4)*self._pct)+2)
            clr = SUCCESS if self._pct == 1.0 else WARN if self._pct >= 0.5 else ACCENT
            self._rr(2, 2, fw, H-2, r, fill=clr, outline="")

    def _rr(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(pts, smooth=True, **kw)

# ─── application ──────────────────────────────────────────────────────────────

class App:

    DAY_HDR = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Focus Tracker")
        self.root.geometry("980x700")
        self.root.minsize(820, 580)
        self.root.configure(bg=BG)

        self.data = load_data()
        self.today = date.today()
        self.sel   = self.today
        self.view_y = self.today.year
        self.view_m = self.today.month
        self._detail_gid = None

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
        self.f_big    = tkfont.Font(family="Segoe UI", size=22, weight="bold")

    # ── skeleton ──────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self.root, bg=ACCENT, padx=20, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎯  Focus Tracker", bg=ACCENT, fg="white",
                 font=self.f_h1).pack(side="left")
        self._streak_lbl = tk.Label(hdr, text="", bg=ACCENT, fg="#C7D2FE",
                                    font=self.f_small)
        self._streak_lbl.pack(side="right")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        sb = tk.Frame(body, bg=BG, width=224)
        sb.pack(side="left", fill="y", padx=(0, 12))
        sb.pack_propagate(False)
        self._build_sidebar(sb)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_right(right)

    # ── sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        tk.Label(parent, text="MY GOALS", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", pady=(4, 6))

        list_card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                             highlightbackground=BORDER)
        list_card.pack(fill="both", expand=True)

        self._gl_cv = tk.Canvas(list_card, bg=CARD, highlightthickness=0)
        gl_sb = ttk.Scrollbar(list_card, orient="vertical",
                              command=self._gl_cv.yview)
        self._gl_cv.configure(yscrollcommand=gl_sb.set)
        self._gl_cv.pack(side="left", fill="both", expand=True)
        gl_sb.pack(side="right", fill="y")

        self._gl_fr = tk.Frame(self._gl_cv, bg=CARD)
        self._gl_win = self._gl_cv.create_window((0,0), window=self._gl_fr, anchor="nw")
        self._gl_fr.bind("<Configure>", lambda _e: self._gl_cv.configure(
            scrollregion=self._gl_cv.bbox("all")))
        self._gl_cv.bind("<Configure>", lambda e: self._gl_cv.itemconfigure(
            self._gl_win, width=e.width))

        tk.Button(parent, text="＋  Add Goal", bg=ACCENT, fg="white",
                  bd=0, cursor="hand2", font=self.f_h3, pady=9,
                  activebackground="#3B55D9", activeforeground="white",
                  command=self._add_goal_dialog).pack(fill="x", pady=(10, 0))

    def _render_sidebar(self):
        for w in self._gl_fr.winfo_children():
            w.destroy()

        goals = active_goals(self.data)
        if not goals:
            tk.Label(self._gl_fr, text="No goals yet.\nClick 'Add Goal' below.",
                     bg=CARD, fg=SUBTEXT, font=self.f_small,
                     justify="center").pack(pady=28)
            return

        for g in goals:
            sel = (self._detail_gid == g["id"])
            rbg = hex_lighten(g.get("color", ACCENT), 0.88) if sel else CARD

            row = tk.Frame(self._gl_fr, bg=rbg, cursor="hand2")
            row.pack(fill="x")
            tk.Frame(row, width=5, bg=g.get("color", ACCENT)).pack(
                side="left", fill="y")

            inner = tk.Frame(row, bg=rbg, padx=10, pady=9)
            inner.pack(side="left", fill="both", expand=True)
            tk.Label(inner, text=g["title"], bg=rbg, fg=TEXT,
                     font=self.f_h3, anchor="w").pack(fill="x")
            if g.get("desc"):
                tk.Label(inner, text=g["desc"], bg=rbg, fg=SUBTEXT,
                         font=self.f_micro, anchor="w",
                         wraplength=148, justify="left").pack(fill="x")

            del_btn = tk.Button(row, text="✕", bg=rbg, fg="#CBD5E1",
                                activebackground="#FEE2E2",
                                activeforeground=DANGER,
                                font=self.f_micro, bd=0,
                                cursor="hand2", padx=6,
                                command=lambda gid=g["id"]: self._delete_goal(gid))
            del_btn.pack(side="right", padx=(0, 6))
            del_btn.bind("<Button-1>", lambda e: "break")

            gid = g["id"]
            for w in [row, inner] + inner.winfo_children():
                w.bind("<Button-1>",
                       lambda _e, i=gid: self._show_detail(i))

            tk.Frame(self._gl_fr, bg=BORDER, height=1).pack(fill="x")

    # ── right panel ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        self._main_fr = tk.Frame(parent, bg=BG)
        self._build_main_view(self._main_fr)

        self._det_fr = tk.Frame(parent, bg=BG)
        self._build_detail_shell(self._det_fr)

        self._main_fr.pack(fill="both", expand=True)

    def _show_main(self):
        self._detail_gid = None
        self._det_fr.pack_forget()
        self._main_fr.pack(fill="both", expand=True)
        self._render_sidebar()
        self._render_calendar()
        self._render_day()

    def _show_detail(self, gid):
        self._detail_gid = gid
        self._main_fr.pack_forget()
        self._det_fr.pack(fill="both", expand=True)
        self._render_sidebar()
        self._render_detail(gid)

    # ── main view ─────────────────────────────────────────────────────────────

    def _build_main_view(self, parent):
        cal_card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER)
        cal_card.pack(fill="x", pady=(0, 10))
        self._cal_inner = tk.Frame(cal_card, bg=CARD, padx=16, pady=12)
        self._cal_inner.pack(fill="both", expand=True)
        self._build_cal_shell()

        day_card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER)
        day_card.pack(fill="both", expand=True)
        day_wrap = tk.Frame(day_card, bg=CARD, padx=16, pady=14)
        day_wrap.pack(fill="both", expand=True)
        self._build_day_shell(day_wrap)

    def _build_cal_shell(self):
        p = self._cal_inner
        nav = tk.Frame(p, bg=CARD)
        nav.pack(fill="x", pady=(0, 10))
        tk.Button(nav, text="◀", bg=CARD, fg=SUBTEXT, bd=0,
                  font=("Segoe UI",12), cursor="hand2", activebackground=BG,
                  command=lambda: self._shift_month(-1)).pack(side="left")
        self._month_lbl = tk.Label(nav, text="", bg=CARD, fg=TEXT,
                                   font=self.f_h2, anchor="center")
        self._month_lbl.pack(side="left", expand=True, fill="x")
        tk.Button(nav, text="▶", bg=CARD, fg=SUBTEXT, bd=0,
                  font=("Segoe UI",12), cursor="hand2", activebackground=BG,
                  command=lambda: self._shift_month(1)).pack(side="right")
        self._cal_grid = tk.Frame(p, bg=CARD)
        self._cal_grid.pack(fill="x")
        leg = tk.Frame(p, bg=CARD)
        leg.pack(anchor="w", pady=(8, 0))
        for c, l in [(SUCCESS,"All done"),(WARN,"Partial"),(ORANGE,"Started"),
                     (DANGER,"None done"),("#DDE3F0","No goals / future")]:
            f = tk.Frame(leg, bg=CARD)
            f.pack(side="left", padx=(0,14))
            tk.Frame(f, width=11, height=11, bg=c).pack(side="left", padx=(0,4))
            tk.Label(f, text=l, bg=CARD, fg=SUBTEXT, font=self.f_micro).pack(side="left")

    def _build_day_shell(self, parent):
        parent.rowconfigure(3, weight=1)
        parent.columnconfigure(0, weight=1)

        hdr = tk.Frame(parent, bg=CARD)
        hdr.grid(row=0, column=0, sticky="ew")
        self._day_lbl = tk.Label(hdr, text="", bg=CARD, fg=TEXT,
                                  font=self.f_h2, anchor="w")
        self._day_lbl.pack(side="left")
        tk.Button(hdr, text="Go to Today", bg="#EEF2FF", fg=ACCENT,
                  activebackground="#C7D2FE", bd=0, font=self.f_small,
                  padx=10, pady=4, cursor="hand2",
                  command=self._jump_to_today).pack(side="right")

        pr = tk.Frame(parent, bg=CARD)
        pr.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        pr.columnconfigure(0, weight=1)
        self._prog_bar = RoundedBar(pr, height=10)
        self._prog_bar.grid(row=0, column=0, sticky="ew", padx=(0,10))
        self._prog_lbl = tk.Label(pr, text="", bg=CARD, fg=SUBTEXT,
                                   font=self.f_small, width=13, anchor="e")
        self._prog_lbl.grid(row=0, column=1)

        ch = tk.Frame(parent, bg=CARD)
        ch.grid(row=2, column=0, sticky="ew", pady=(12, 4))
        ch.columnconfigure(0, weight=3)
        ch.columnconfigure(1, weight=2)
        tk.Label(ch, text="GOALS", bg=CARD, fg=SUBTEXT,
                 font=self.f_micro).grid(row=0, column=0, sticky="w")
        tk.Label(ch, text="📝  PROGRESS NOTES", bg=CARD, fg=SUBTEXT,
                 font=self.f_micro).grid(row=0, column=1, sticky="w", padx=(16,0))

        cols = tk.Frame(parent, bg=CARD)
        cols.grid(row=3, column=0, sticky="nsew")
        cols.rowconfigure(0, weight=1)
        cols.columnconfigure(0, weight=3)
        cols.columnconfigure(1, weight=2)

        th = tk.Frame(cols, bg=CARD)
        th.grid(row=0, column=0, sticky="nsew")
        th.rowconfigure(0, weight=1)
        th.columnconfigure(0, weight=1)
        self._tick_cv = tk.Canvas(th, bg=CARD, highlightthickness=0)
        tsb = ttk.Scrollbar(th, orient="vertical", command=self._tick_cv.yview)
        self._tick_cv.configure(yscrollcommand=tsb.set)
        self._tick_cv.grid(row=0, column=0, sticky="nsew")
        tsb.grid(row=0, column=1, sticky="ns")
        self._tick_fr = tk.Frame(self._tick_cv, bg=CARD)
        self._tf_win = self._tick_cv.create_window(
            (0,0), window=self._tick_fr, anchor="nw")
        self._tick_fr.bind("<Configure>", lambda _e: self._tick_cv.configure(
            scrollregion=self._tick_cv.bbox("all")))
        self._tick_cv.bind("<Configure>", lambda e: self._tick_cv.itemconfigure(
            self._tf_win, width=e.width))

        nh = tk.Frame(cols, bg=CARD)
        nh.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        nh.rowconfigure(0, weight=1)
        nh.columnconfigure(0, weight=1)
        self._note_txt = tk.Text(nh, bg=STRIPE, fg=TEXT, font=self.f_body,
                                  relief="flat", padx=10, pady=8, wrap="word",
                                  highlightthickness=1, highlightbackground=BORDER,
                                  insertbackground=ACCENT, spacing3=2)
        self._note_txt.grid(row=0, column=0, sticky="nsew")
        nsb = ttk.Scrollbar(nh, orient="vertical", command=self._note_txt.yview)
        self._note_txt.configure(yscrollcommand=nsb.set)
        nsb.grid(row=0, column=1, sticky="ns")
        self._save_note_btn = tk.Button(
            nh, text="💾  Save Note", bg=ACCENT, fg="white", bd=0,
            cursor="hand2", font=self.f_small, padx=12, pady=5,
            activebackground="#3B55D9", activeforeground="white",
            command=self._save_day_note)
        self._save_note_btn.grid(row=1, column=0, sticky="e", pady=(6, 0))

    # ── detail shell (built once, content rebuilt on each navigation) ──────────

    def _build_detail_shell(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        back = tk.Frame(parent, bg=BG)
        back.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Button(back, text="← Back to Calendar", bg=BG, fg=ACCENT,
                  activebackground="#C7D2FE", bd=0, font=self.f_small,
                  cursor="hand2", command=self._show_main).pack(side="left")

        wrap = tk.Frame(parent, bg=BG)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self._det_cv = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        det_sb = ttk.Scrollbar(wrap, orient="vertical",
                               command=self._det_cv.yview)
        self._det_cv.configure(yscrollcommand=det_sb.set)
        self._det_cv.grid(row=0, column=0, sticky="nsew")
        det_sb.grid(row=0, column=1, sticky="ns")

        self._det_content = tk.Frame(self._det_cv, bg=BG)
        self._det_win = self._det_cv.create_window(
            (0, 0), window=self._det_content, anchor="nw")
        self._det_content.bind("<Configure>", lambda _e: self._det_cv.configure(
            scrollregion=self._det_cv.bbox("all")))
        self._det_cv.bind("<Configure>", lambda e: self._det_cv.itemconfigure(
            self._det_win, width=e.width))
        self._det_cv.bind("<MouseWheel>", lambda e: self._det_cv.yview_scroll(
            int(-e.delta/120), "units"))

    # ── detail view render ────────────────────────────────────────────────────

    def _render_detail(self, gid):
        for w in self._det_content.winfo_children():
            w.destroy()
        self._det_cv.yview_moveto(0)

        g = next((x for x in self.data["goals"] if x["id"] == gid), None)
        if not g:
            return
        st    = goal_analytics(self.data, gid)
        color = g.get("color", ACCENT)
        p     = self._det_content

        # ── goal header card ──────────────────────────────────────────────
        hc = self._card(p)
        hc.pack(fill="x", pady=(0, 10))

        title_row = tk.Frame(hc, bg=CARD)
        title_row.pack(fill="x")

        dot = tk.Canvas(title_row, width=16, height=16, bg=CARD,
                        highlightthickness=0)
        dot.pack(side="left", padx=(0, 10))
        dot.create_oval(1, 1, 15, 15, fill=color, outline=color)

        tk.Label(title_row, text=g["title"], bg=CARD, fg=TEXT,
                 font=self.f_h2).pack(side="left")

        brow = tk.Frame(title_row, bg=CARD)
        brow.pack(side="right")
        tk.Button(brow, text="✏  Edit", bg=BG, fg=SUBTEXT, bd=0,
                  font=self.f_small, padx=10, pady=4, cursor="hand2",
                  activebackground="#E2E8F0",
                  command=lambda: self._goal_dialog(gid)).pack(side="left", padx=(0,6))
        tk.Button(brow, text="🗑  Delete", bg="#FEE2E2", fg=DANGER, bd=0,
                  font=self.f_small, padx=10, pady=4, cursor="hand2",
                  activebackground="#FECACA",
                  command=lambda: self._delete_goal(gid)).pack(side="left")

        if g.get("desc"):
            tk.Label(hc, text=g["desc"], bg=CARD, fg=SUBTEXT,
                     font=self.f_body, anchor="w").pack(fill="x", pady=(6, 0))
        tk.Label(hc,
                 text=f"Created {st['created'].strftime('%B %d, %Y')}  ·  "
                      f"{st['total']} day{'s' if st['total']!=1 else ''} tracked  ·  "
                      f"{st['done']} completed",
                 bg=CARD, fg=SUBTEXT, font=self.f_micro).pack(anchor="w", pady=(4,0))

        # ── stat cards ────────────────────────────────────────────────────
        sf = tk.Frame(p, bg=BG)
        sf.pack(fill="x", pady=(0, 10))
        items = [
            (f"{int(st['rate']*100)}%",          "Completion Rate",  color),
            (f"{st['streak']}",                   "Current Streak",   ACCENT),
            (f"{st['best_streak']}",              "Best Streak",      SUCCESS),
            (f"{st['month_done']}/{st['month_total']}", "This Month", WARN),
        ]
        for i, (val, lbl, ac) in enumerate(items):
            sc = self._card(p=None, parent=sf, padding=(14,12))
            sc.grid(row=0, column=i, sticky="nsew", padx=(0 if i==0 else 6, 0))
            sf.columnconfigure(i, weight=1)
            tk.Frame(sc, height=3, bg=ac).pack(fill="x", pady=(0, 8))
            tk.Label(sc, text=val, bg=CARD, fg=ac, font=self.f_big).pack(anchor="w")
            tk.Label(sc, text=lbl, bg=CARD, fg=SUBTEXT, font=self.f_small).pack(anchor="w")

        # ── activity heatmap ──────────────────────────────────────────────
        hmc = self._card(p)
        hmc.pack(fill="x", pady=(0, 10))
        tk.Label(hmc, text="Activity  ·  Last 15 Weeks", bg=CARD, fg=TEXT,
                 font=self.f_h3).pack(anchor="w", pady=(0, 10))

        today   = date.today()
        wstart  = today - timedelta(days=today.weekday())
        hm_from = wstart - timedelta(weeks=14)
        WEEKS   = 15
        CELL    = 13
        GAP     = 2
        UNIT    = CELL + GAP
        LBL_W   = 28

        hm_cv = tk.Canvas(hmc, bg=CARD, highlightthickness=0,
                          width=LBL_W + WEEKS*UNIT,
                          height=7*UNIT + 22)
        hm_cv.pack(anchor="w")

        for ri, dl in enumerate(["M","T","W","T","F","S","S"]):
            hm_cv.create_text(LBL_W-4, ri*UNIT + CELL//2 + 2,
                              text=dl, anchor="e",
                              fill=SUBTEXT, font=("Segoe UI",7))

        for col in range(WEEKS):
            for row in range(7):
                d = hm_from + timedelta(weeks=col, days=row)
                x1 = LBL_W + col*UNIT
                y1 = row*UNIT + 2
                if d > today or d < st["created"]:
                    fill = "#E2E8F0"
                elif d in st["ticked"]:
                    fill = color
                else:
                    fill = hex_lighten(color, 0.80)
                hm_cv.create_rectangle(x1+1, y1+1, x1+CELL-1, y1+CELL-1,
                                       fill=fill, outline="")

        for col in range(0, WEEKS, 3):
            d = hm_from + timedelta(weeks=col)
            hm_cv.create_text(LBL_W + col*UNIT + CELL//2, 7*UNIT+14,
                              text=d.strftime("%b %d"), anchor="center",
                              fill=SUBTEXT, font=("Segoe UI",7))

        # ── monthly + DOW charts (side by side) ───────────────────────────
        cr = tk.Frame(p, bg=BG)
        cr.pack(fill="x", pady=(0, 10))
        cr.columnconfigure(0, weight=1)
        cr.columnconfigure(1, weight=1)

        mc = self._card(p=None, parent=cr, padding=(14,12))
        mc.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(mc, text="Monthly Completion", bg=CARD, fg=TEXT,
                 font=self.f_h3).pack(anchor="w", pady=(0, 8))
        m_cv = tk.Canvas(mc, bg=CARD, highlightthickness=0, height=120)
        m_cv.pack(fill="x")
        m_cv.bind("<Configure>",
                  lambda e, c=m_cv, s=st, cl=color: self._draw_monthly(c, s, cl))

        dc = self._card(p=None, parent=cr, padding=(14,12))
        dc.grid(row=0, column=1, sticky="nsew")
        tk.Label(dc, text="By Day of Week", bg=CARD, fg=TEXT,
                 font=self.f_h3).pack(anchor="w", pady=(0, 8))
        d_cv = tk.Canvas(dc, bg=CARD, highlightthickness=0, height=120)
        d_cv.pack(fill="x")
        d_cv.bind("<Configure>",
                  lambda e, c=d_cv, s=st, cl=color: self._draw_dow(c, s, cl))

        # ── goal notes ────────────────────────────────────────────────────
        gnc = self._card(p)
        gnc.pack(fill="x", pady=(0, 10))
        gnc.columnconfigure(0, weight=1)

        nh = tk.Frame(gnc, bg=CARD)
        nh.pack(fill="x")
        tk.Label(nh, text="Goal Notes", bg=CARD, fg=TEXT,
                 font=self.f_h3).pack(side="left")
        tk.Label(nh, text="— your reflections on this goal",
                 bg=CARD, fg=SUBTEXT, font=self.f_micro).pack(side="left", padx=(8,0))

        gn_txt = tk.Text(gnc, bg=STRIPE, fg=TEXT, font=self.f_body,
                         relief="flat", padx=10, pady=8, wrap="word",
                         highlightthickness=1, highlightbackground=BORDER,
                         insertbackground=ACCENT, height=5)
        gn_txt.pack(fill="x", pady=(8, 0))
        if g.get("note"):
            gn_txt.insert("1.0", g["note"])

        save_gn = tk.Button(gnc, text="💾  Save Notes", bg=ACCENT, fg="white",
                            bd=0, cursor="hand2", font=self.f_small,
                            padx=12, pady=5, activebackground="#3B55D9",
                            activeforeground="white",
                            command=lambda: self._save_goal_note(gid, gn_txt, save_gn))
        save_gn.pack(anchor="e", pady=(8, 0))

        # ── progress history ──────────────────────────────────────────────
        phc = self._card(p)
        phc.pack(fill="x", pady=(0, 4))
        tk.Label(phc, text="Progress History", bg=CARD, fg=TEXT,
                 font=self.f_h3).pack(anchor="w", pady=(0, 10))

        if not st["notes"]:
            tk.Label(phc,
                     text="No progress notes yet.\nAdd notes from the calendar view.",
                     bg=CARD, fg=SUBTEXT, font=self.f_body,
                     justify="center").pack(pady=10)
        else:
            for entry in st["notes"]:
                row = tk.Frame(phc, bg=CARD)
                row.pack(fill="x", pady=(0, 8))

                ic = tk.Canvas(row, width=14, height=14, bg=CARD,
                               highlightthickness=0)
                ic.pack(side="left", padx=(0, 10), pady=3)
                tc = color if entry["ticked"] else "#E2E8F0"
                ic.create_oval(1,1,13,13, fill=tc, outline=tc)
                if entry["ticked"]:
                    ic.create_text(7,7, text="✓", fill="white",
                                   font=("Segoe UI",7,"bold"))

                wrap2 = tk.Frame(row, bg=CARD)
                wrap2.pack(side="left", fill="x", expand=True)
                tk.Label(wrap2, text=entry["date"].strftime("%A, %B %d, %Y"),
                         bg=CARD, fg=SUBTEXT, font=self.f_micro).pack(anchor="w")
                tk.Label(wrap2, text=entry["note"], bg=CARD, fg=TEXT,
                         font=self.f_body, anchor="w",
                         wraplength=440, justify="left").pack(anchor="w")

                tk.Frame(phc, bg=BORDER, height=1).pack(fill="x", pady=(4,0))

    # ── chart renderers ───────────────────────────────────────────────────────

    def _draw_monthly(self, canvas, st, color):
        canvas.delete("all")
        W, H = canvas.winfo_width(), canvas.winfo_height()
        if W < 10: return
        months = list(st["monthly"].values())
        n = len(months)
        if not n: return
        ml, mr, mt, mb = 8, 8, 18, 22
        cw = W - ml - mr
        ch = H - mt - mb
        gap = cw / n
        bw  = int(gap * 0.55)

        for pct in (25, 50, 75, 100):
            y = mt + ch - int(ch * pct/100)
            canvas.create_line(ml, y, W-mr, y, fill="#F1F5F9", dash=(2,3))

        for i, m in enumerate(months):
            t = m["total"]; d = m["done"]
            r = d/t if t else 0
            cx = ml + i*gap + gap/2
            bx1, bx2 = int(cx - bw/2), int(cx + bw/2)
            bh = max(2, int(ch * r))
            by1 = mt + ch - bh
            by2 = mt + ch

            bc = SUCCESS if r == 1.0 else (color if r >= 0.5
                 else hex_lighten(color, 0.35) if r > 0 else "#E2E8F0")
            canvas.create_rectangle(bx1, by1, bx2, by2, fill=bc, outline="")
            if r > 0:
                canvas.create_text(int(cx), by1-3, text=f"{int(r*100)}%",
                                   anchor="s", fill=TEXT, font=("Segoe UI",7))
            canvas.create_text(int(cx), H-5, text=m["label"],
                               anchor="s", fill=SUBTEXT, font=("Segoe UI",8))

    def _draw_dow(self, canvas, st, color):
        canvas.delete("all")
        W, H = canvas.winfo_width(), canvas.winfo_height()
        if W < 10: return
        names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        ml, mr, mt = 32, 36, 4
        rh  = (H - mt) / 7
        bh  = int(rh * 0.52)
        mxw = W - ml - mr

        for i in range(7):
            d = st["dow"][i]
            r = d["done"] / d["total"] if d["total"] else 0
            yc = mt + i*rh + rh/2
            bt = int(yc - bh/2)
            bb = bt + bh

            canvas.create_text(ml-4, yc, text=names[i], anchor="e",
                               fill=SUBTEXT, font=("Segoe UI",8))
            canvas.create_rectangle(ml, bt, ml+mxw, bb, fill="#F1F5F9", outline="")
            if r > 0:
                fw  = max(bh, int(mxw * r))
                bc  = SUCCESS if r >= 0.9 else (color if r >= 0.5
                      else hex_lighten(color, 0.35))
                canvas.create_rectangle(ml, bt, ml+fw, bb, fill=bc, outline="")
            canvas.create_text(ml+mxw+4, yc, text=f"{int(r*100)}%",
                               anchor="w", fill=SUBTEXT, font=("Segoe UI",8))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _card(self, p=None, parent=None, padding=(16, 14)):
        host = parent if parent is not None else p
        outer = tk.Frame(host, bg=CARD, highlightthickness=1,
                         highlightbackground=BORDER)
        inner = tk.Frame(outer, bg=CARD, padx=padding[0], pady=padding[1])
        inner.pack(fill="both", expand=True)
        return inner

    def _save_goal_note(self, gid, widget, btn):
        for g in self.data["goals"]:
            if g["id"] == gid:
                g["note"] = widget.get("1.0", "end").rstrip()
                break
        save_data(self.data)
        btn.config(text="✓  Saved!", bg=SUCCESS)
        self.root.after(1400, lambda: btn.config(text="💾  Save Notes", bg=ACCENT))

    # ── calendar ──────────────────────────────────────────────────────────────

    def _shift_month(self, delta):
        m = self.view_m + delta
        y = self.view_y
        while m < 1:  m += 12; y -= 1
        while m > 12: m -= 12; y += 1
        self.view_y, self.view_m = y, m
        self._render_calendar()

    def _jump_to_today(self):
        self.today = date.today()
        self.view_y, self.view_m = self.today.year, self.today.month
        self.sel = self.today
        self._refresh()

    def _render_calendar(self):
        for w in self._cal_grid.winfo_children():
            w.destroy()
        self._month_lbl.config(
            text=f"{calendar.month_name[self.view_m]}   {self.view_y}")
        for ci, dl in enumerate(self.DAY_HDR):
            tk.Label(self._cal_grid, text=dl, bg=CARD, fg=SUBTEXT,
                     font=self.f_micro, width=4, anchor="center").grid(
                row=0, column=ci, padx=2, pady=(0,6))
            self._cal_grid.columnconfigure(ci, weight=1)
        today = date.today()
        for ri, week in enumerate(
                calendar.Calendar(firstweekday=0).monthdayscalendar(
                    self.view_y, self.view_m), 1):
            for ci, day in enumerate(week):
                if day == 0:
                    tk.Frame(self._cal_grid, bg=BG, width=36,
                             height=32).grid(row=ri, column=ci, padx=2, pady=2)
                    continue
                d  = date(self.view_y, self.view_m, day)
                bg = cell_color(self.data, d)
                is_today = (d == today)
                is_sel   = (d == self.sel)
                outer = tk.Frame(self._cal_grid,
                                 bg=ACCENT if (is_today or is_sel) else BG,
                                 padx=2 if (is_today or is_sel) else 0,
                                 pady=2 if (is_today or is_sel) else 0)
                outer.grid(row=ri, column=ci, padx=2, pady=2, sticky="nsew")
                fg = TEXT if bg in ("#DDE3F0", WARN) else "white"
                lbl = tk.Label(outer, text=str(day), bg=bg, fg=fg,
                               font=self.f_h3 if is_today else self.f_small,
                               width=3, anchor="center", cursor="hand2", pady=5)
                lbl.pack(fill="both", expand=True)
                lbl.bind("<Button-1>", lambda _e, dd=d: self._on_day(dd))
                outer.bind("<Button-1>", lambda _e, dd=d: self._on_day(dd))

    def _on_day(self, d):
        self.sel = d
        self._render_calendar()
        self._render_day()

    # ── day panel ─────────────────────────────────────────────────────────────

    def _render_day(self):
        d = self.sel
        prefix = "Today" if d == date.today() else d.strftime("%A")
        self._day_lbl.config(text=f"{prefix}  ·  {d.strftime('%B %d, %Y')}")

        done, total = day_progress(self.data, d)
        pct = done/total if total else 0
        self._prog_bar.set(pct)
        self._prog_lbl.config(
            text=f"{int(pct*100)}%  ({done}/{total})" if total else "no goals")

        for w in self._tick_fr.winfo_children():
            w.destroy()

        goals     = active_goals(self.data)
        k         = dkey(d)
        ticks     = self.data["days"].get(k, {}).get("ticks", {})
        is_future = d > date.today()

        if not goals:
            tk.Label(self._tick_fr, text="Add goals in the sidebar →",
                     bg=CARD, fg=SUBTEXT, font=self.f_body,
                     justify="center").pack(pady=24)
        else:
            for g in goals:
                checked = ticks.get(g["id"], False)
                gc      = g.get("color", ACCENT)

                row = tk.Frame(self._tick_fr, bg=CARD)
                row.pack(fill="x", pady=1)

                box = tk.Canvas(row, width=22, height=22, bg=CARD,
                                highlightthickness=0,
                                cursor="" if is_future else "hand2")
                box.pack(side="left", padx=(4,8), pady=6)

                def _draw_box(c=box, chk=checked, col=gc):
                    c.delete("all")
                    if chk:
                        c.create_rectangle(2,2,20,20, fill=col, outline=col)
                        c.create_text(11,11, text="✓", fill="white", font=self.f_h3)
                    else:
                        c.create_rectangle(2,2,20,20, fill=CARD,
                                           outline=BORDER, width=2)
                _draw_box()

                lbl = tk.Label(row, text=g["title"], bg=CARD,
                               fg=SUBTEXT if checked else TEXT,
                               font=self.f_strike if checked else self.f_body,
                               anchor="w")
                lbl.pack(side="left", fill="x", expand=True)
                tk.Frame(row, width=6, height=22, bg=gc).pack(side="right", padx=(0,6))
                tk.Frame(self._tick_fr, bg=BORDER, height=1).pack(fill="x")

                if not is_future:
                    def _make(gid, canvas, label, col):
                        state = [ticks.get(gid, False)]
                        def toggle(_e=None):
                            state[0] = not state[0]
                            self.data["days"].setdefault(k, {"ticks":{},"note":""})
                            self.data["days"][k].setdefault("ticks", {})
                            self.data["days"][k]["ticks"][gid] = state[0]
                            save_data(self.data)
                            canvas.delete("all")
                            if state[0]:
                                canvas.create_rectangle(2,2,20,20,
                                    fill=col, outline=col)
                                canvas.create_text(11,11, text="✓",
                                    fill="white", font=self.f_h3)
                            else:
                                canvas.create_rectangle(2,2,20,20,
                                    fill=CARD, outline=BORDER, width=2)
                            label.config(
                                font=self.f_strike if state[0] else self.f_body,
                                fg=SUBTEXT if state[0] else TEXT)
                            dn, tot = day_progress(self.data, self.sel)
                            pp = dn/tot if tot else 0
                            self._prog_bar.set(pp)
                            self._prog_lbl.config(
                                text=f"{int(pp*100)}%  ({dn}/{tot})" if tot else "no goals")
                            self._update_streak()
                            self._render_calendar()
                        return toggle
                    fn = _make(g["id"], box, lbl, gc)
                    box.bind("<Button-1>", fn)
                    lbl.bind("<Button-1>", fn)
                    row.bind("<Button-1>", fn)

        self._note_txt.configure(state="normal")
        self._note_txt.delete("1.0", "end")
        note = self.data["days"].get(k, {}).get("note", "")
        if note:
            self._note_txt.insert("1.0", note)
        if is_future:
            self._note_txt.configure(state="disabled", bg="#F1F5F9")
            self._save_note_btn.configure(state="disabled", bg="#94A3B8")
        else:
            self._note_txt.configure(state="normal", bg=STRIPE)
            self._save_note_btn.configure(state="normal", bg=ACCENT)

    def _save_day_note(self):
        k = dkey(self.sel)
        self.data["days"].setdefault(k, {"ticks":{}, "note":""})
        self.data["days"][k]["note"] = self._note_txt.get("1.0","end").rstrip()
        save_data(self.data)
        self._save_note_btn.config(text="✓  Saved!", bg=SUCCESS)
        self.root.after(1400, lambda: self._save_note_btn.config(
            text="💾  Save Note", bg=ACCENT))

    # ── goal management ────────────────────────────────────────────────────────

    def _add_goal_dialog(self):
        self._goal_dialog(None)

    def _goal_dialog(self, gid):
        is_edit = gid is not None
        g_obj   = next((g for g in self.data["goals"] if g["id"] == gid), None) if is_edit else None

        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Goal" if is_edit else "New Goal")
        dlg.geometry("400x300")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        self.root.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 400)//2
        py = self.root.winfo_y() + (self.root.winfo_height() - 300)//2
        dlg.geometry(f"400x300+{px}+{py}")

        tk.Label(dlg, text="Edit Goal" if is_edit else "Add a New Goal",
                 bg=BG, fg=TEXT, font=self.f_h2).pack(anchor="w", padx=24, pady=(20,2))

        tk.Label(dlg, text="Title *", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", padx=24, pady=(12,2))
        tv = tk.StringVar(value=g_obj["title"] if g_obj else "")
        te = tk.Entry(dlg, textvariable=tv, bg=CARD, fg=TEXT, font=self.f_body,
                      relief="flat", bd=0, highlightthickness=1,
                      highlightbackground=BORDER, insertbackground=ACCENT)
        te.pack(fill="x", padx=24, ipady=7)
        te.focus_set()

        tk.Label(dlg, text="Description (optional)", bg=BG, fg=SUBTEXT,
                 font=self.f_micro).pack(anchor="w", padx=24, pady=(10,2))
        dv = tk.StringVar(value=g_obj.get("desc","") if g_obj else "")
        de = tk.Entry(dlg, textvariable=dv, bg=CARD, fg=TEXT, font=self.f_body,
                      relief="flat", bd=0, highlightthickness=1,
                      highlightbackground=BORDER, insertbackground=ACCENT)
        de.pack(fill="x", padx=24, ipady=6)

        sr = tk.Frame(dlg, bg=BG)
        sr.pack(anchor="w", padx=24, pady=(12,0))
        tk.Label(sr, text="Colour:", bg=BG, fg=SUBTEXT,
                 font=self.f_small).pack(side="left", padx=(0,10))

        cur_c  = g_obj.get("color", PALETTE[0]) if g_obj else \
                 PALETTE[len(self.data["goals"]) % len(PALETTE)]
        chosen = [cur_c]
        frms   = []

        def pick(c, idx):
            chosen[0] = c
            for j, fr in enumerate(frms):
                fr.config(highlightthickness=2 if j==idx else 0,
                          highlightbackground=TEXT)
        for i, c in enumerate(PALETTE):
            fr = tk.Frame(sr, width=20, height=20, bg=c, cursor="hand2",
                          highlightthickness=2 if c==cur_c else 0,
                          highlightbackground=TEXT)
            fr.pack(side="left", padx=3)
            fr.bind("<Button-1>", lambda _e, cc=c, ii=i: pick(cc, ii))
            frms.append(fr)

        br = tk.Frame(dlg, bg=BG)
        br.pack(fill="x", padx=24, pady=(16,0))

        def confirm(_e=None):
            t = tv.get().strip()
            if not t:
                te.configure(highlightbackground=DANGER, highlightthickness=2)
                return
            if is_edit and g_obj:
                g_obj["title"] = t
                g_obj["desc"]  = dv.get().strip()
                g_obj["color"] = chosen[0]
            else:
                self.data["goals"].append({
                    "id": str(uuid.uuid4()), "title": t,
                    "desc": dv.get().strip(), "color": chosen[0],
                    "active": True, "created": dkey(date.today()), "note": "",
                })
            save_data(self.data)
            dlg.destroy()
            if is_edit and self._detail_gid == gid:
                self._show_detail(gid)
            else:
                self._refresh()

        te.bind("<Return>", confirm)
        de.bind("<Return>", confirm)
        tk.Button(br, text="Cancel", bg=BG, fg=SUBTEXT, bd=0, font=self.f_body,
                  cursor="hand2", activebackground="#E2E8F0",
                  command=dlg.destroy).pack(side="left")
        tk.Button(br, text="Save" if is_edit else "Add Goal →",
                  bg=ACCENT, fg="white", bd=0, font=self.f_h3,
                  padx=18, pady=8, cursor="hand2",
                  activebackground="#3B55D9", activeforeground="white",
                  command=confirm).pack(side="right")

    def _delete_goal(self, gid):
        name = next((g["title"] for g in self.data["goals"] if g["id"]==gid), "goal")
        if not messagebox.askyesno("Delete Goal",
                                   f"Delete '{name}'?\n\nRemoves it from all days.",
                                   parent=self.root):
            return
        self.data["goals"] = [g for g in self.data["goals"] if g["id"] != gid]
        save_data(self.data)
        self._show_main()

    # ── refresh ───────────────────────────────────────────────────────────────

    def _update_streak(self):
        s = calc_streak(self.data)
        self._streak_lbl.config(
            text=f"🔥  {s}-day streak" if s >= 1 else "")

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
