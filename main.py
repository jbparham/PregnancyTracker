"""Pythonista-friendly pregnancy/fertility tracker with macOS Tkinter fallback.

Features implemented in both UIs:
- Calendar with month/year header
- Weekday labels (3-letter)
- Per-day toggles: 'P' to mark/unmark period day, 'S' to mark/unmark sex day
- Periods can be multiple days (storage tracks `periods` with duration and per-day intensity mapping `period_levels`)
- Current day highlighted

Run inside Pythonista to use the native `ui`/`console` interface. Run on macOS to use Tkinter.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
import sys

# detect platforms
try:
    import ui
    import console
    _HAS_PYTHONISTA = True
except Exception:
    ui = None
    console = None
    _HAS_PYTHONISTA = False

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    _HAS_TK = True
except Exception:
    tk = None
    messagebox = None
    simpledialog = None
    _HAS_TK = False

from storage import (
    load_data,
    add_period,
    add_sex,
    set_settings,
    toggle_period_day,
    toggle_sex,
    edit_period,
    remove_period,
    migrate_period_days_to_levels,
    undo,
    redo,
)
from models import day_status_for_month, predict_from_periods


# --- UI helpers: color utilities and theme palettes ---
def _hex_to_rgb(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _rgb_to_hex(rgb):
    return '#%02x%02x%02x' % (int(rgb[0]), int(rgb[1]), int(rgb[2]))

def _blend_hex(c1: str, c2: str, t: float) -> str:
    """Blend two hex colors (c1 -> c2) by t in [0,1]."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = r1 + (r2 - r1) * t
    g = g1 + (g2 - g1) * t
    b = b1 + (b2 - b1) * t
    return _rgb_to_hex((r, g, b))

def get_palette(theme: str = 'light') -> dict:
    if theme == 'dark':
        return {
            'bg': '#1e1e1e',
            'panel': '#2a2a2a',
            'panel_border': '#3a3a3a',
            'text': '#ffffff',
            'cell': '#222222',
            'empty_cell': '#2b2b2b',
            'period_shades': ['#3e0000', '#660000', '#990000'],
            'fertile': '#4b2a3a',
            'ovulation': '#2a3b4b',
            'sex': '#2a4b2a',
            'pred_light': '#331111',
            'pred_dark': '#660000'
        }
    # default light
    return {
        'bg': '#ffffff',
        'panel': '#f7f7f7',
        'panel_border': '#e0e0e0',
        'text': '#000000',
        'cell': '#ffffff',
        'empty_cell': '#efefef',
        # period intensity shades light->heavy
        'period_shades': ['#ffebeb', '#ffb3b3', '#ff6666'],
        'fertile': '#ffd0ff',
        'ovulation': '#cce0ff',
        'sex': '#ccffcc',
        'pred_light': '#fff5f5',
        'pred_dark': '#ff9999'
    }


if _HAS_PYTHONISTA:
    class CalendarView(ui.View):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.data = load_data()
            self.year = date.today().year
            self.month = date.today().month
            self.create_toolbar()
            self.build_grid()

        def create_toolbar(self):
            tb = ui.View(frame=(0, 0, self.width, 64))
            tb.flex = 'W'
            # read theme from data and apply panel background
            settings = self.data.get('settings', {'theme': 'light'})
            palette = get_palette(settings.get('theme', 'light'))
            tb.background_color = palette.get('panel', '#f7f7f7')

            # Navigation row (top)
            btn_prev = ui.Button(title='←')
            btn_prev.frame = (8, 6, 40, 28)
            btn_prev.action = lambda sender: self.nav_month(-1)
            btn_prev.font = ('<system>', 18)
            tb.add_subview(btn_prev)

            # month label
            self.month_label = ui.Label(frame=(52, 6, 200, 28))
            self.month_label.font = ('<system-bold>', 16)
            self.month_label.alignment = ui.ALIGN_CENTER
            self.month_label.text_color = palette.get('text', '#000000')
            tb.add_subview(self.month_label)

            btn_next = ui.Button(title='→')
            btn_next.frame = (256, 6, 40, 28)
            btn_next.action = lambda sender: self.nav_month(1)
            btn_next.font = ('<system>', 18)
            tb.add_subview(btn_next)

            btn_today = ui.Button(title='Today')
            btn_today.frame = (300, 6, 56, 28)
            btn_today.flex = 'L'
            btn_today.action = self.go_today
            tb.add_subview(btn_today)

            # Stats and settings buttons row (bottom)
            # Hamburger menu button
            btn_menu = ui.Button(title='≡')  # Hamburger icon
            btn_menu.frame = (self.width - 46, 34, 40, 26)
            btn_menu.font = ('<system>', 24)
            btn_menu.action = self.show_menu
            tb.add_subview(btn_menu)

            self.add_subview(tb)

        def build_grid(self):
            # remove existing calendar subviews
            for sv in list(self.subviews):
                if getattr(sv, 'is_day_grid', False):
                    self.remove_subview(sv)

            import calendar
            cal = calendar.monthcalendar(self.year, self.month)
            grid = ui.View(frame=(0, 64, self.width, self.height-64))
            grid.is_day_grid = True

            # month label text
            self.month_label.text = f"{calendar.month_name[self.month]} {self.year}"

            # prepare statuses and theme
            settings = self.data.get('settings', {'cycle_length': 28, 'luteal_phase': 14, 'theme': 'light'})
            theme = settings.get('theme', 'light')
            palette = get_palette(theme)
            # Get predicted cycles and calculate duration
            period_starts = [p['start'] for p in self.data.get('periods', [])]
            durations = [p.get('duration', 5) for p in self.data.get('periods', [])]
            pred_duration = int(round(sum(durations) / len(durations))) if durations else 5

            # weekday header
            weekdays = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
            w_h = 24
            for i, wd in enumerate(weekdays):
                lbl = ui.Label(frame=(i * (self.width/7), 0, self.width/7, w_h))
                lbl.text = wd
                lbl.alignment = ui.ALIGN_CENTER
                lbl.background_color = palette.get('panel', '#f0f0f0')  # themed header background
                lbl.font = ('<system-bold>', 12)  # make text bold for better contrast
                lbl.border_width = 0.5  # subtle border
                lbl.border_color = palette.get('panel_border', '#e0e0e0')  # themed border
                grid.add_subview(lbl)

            rows = len(cal)
            cols = 7
            cell_w = self.width / cols
            cell_h = (self.height - 64 - w_h) / rows

            predictions = predict_from_periods(
                period_starts,
                settings.get('cycle_length', 28),
                settings.get('luteal_phase', 14),
                lookahead_months=6
            )

            # Calculate all predicted period days and starts
            predicted_days = set()
            predicted_starts = []
            for start_iso in predictions.get('predicted_cycles', []):
                if start_iso <= date.today().isoformat():
                    continue  # skip past/current predictions
                start_date = datetime.strptime(start_iso, '%Y-%m-%d').date()
                predicted_starts.append(start_date)
                # Add all days in the predicted duration
                for i in range(pred_duration):
                    predicted_days.add(start_date + timedelta(days=i))

            status_map = day_status_for_month(
                self.data.get('periods', []),
                list(self.data.get('period_levels', {}).keys()),
                self.data.get('sex', []),
                settings.get('cycle_length', 28),
                settings.get('luteal_phase', 14),
                self.year,
                self.month,
            )

            y = w_h
            today = date.today()
            for r, week in enumerate(cal):
                x = 0
                for c, day in enumerate(week):
                    container = ui.View()
                    container.frame = (x, y, cell_w-1, cell_h-1)
                    container.background_color = palette.get('cell', '#ffffff')
                    # empty cell
                    if day == 0:
                        container.background_color = palette.get('empty_cell', '#efefef')
                    else:
                        d = date(self.year, self.month, day)
                        iso = d.isoformat()
                        s = status_map.get(iso, set())

                        # determine per-day period intensity (0..3)
                        intensity = int(self.data.get('period_levels', {}).get(iso, 0))

                        # color priority for entire cell background (period intensity wins)
                        if intensity > 0 or 'period' in s:
                            # choose shade based on intensity (1->light,2->med,3->heavy)
                            shades = palette.get('period_shades', ['#ffebeb', '#ffb3b3', '#ff6666'])
                            container.background_color = shades[max(0, min(2, intensity-1))]
                        elif 'fertile' in s:
                            container.background_color = palette.get('fertile', '#ffd0ff')
                        elif 'ovulation' in s:
                            container.background_color = palette.get('ovulation', '#cce0ff')
                        elif 'sex' in s:
                            container.background_color = palette.get('sex', '#ccffcc')

                        day_lbl = ui.Label(frame=(4, 8, 28, 20))
                        day_lbl.text = str(day)
                        day_lbl.font = ('<system>', 12)
                        day_lbl.text_color = palette.get('text', '#000000')
                        container.add_subview(day_lbl)

                        # ovulation marker (egg emoji) top-right
                        if 'ovulation' in s:
                            ov = ui.Label()
                            ov.frame = (cell_w-22, 2, 20, 20)
                            ov.text = '🥚'
                            ov.font = ('<system>', 14)
                            container.add_subview(ov)

                        # current day highlight
                        if d == today:
                            container.border_width = 2
                            container.border_color = '#ff9900'

                        # predicted period days indicator: gradient by proximity to predicted start
                        if d in predicted_days and d > today:
                            # find nearest predicted start >= d
                            nearest = None
                            for ps in predicted_starts:
                                if ps >= d:
                                    dist = (ps - d).days
                                    if nearest is None or dist < nearest:
                                        nearest = dist
                            if nearest is None:
                                nearest = 0
                            # map nearest (0..pred_duration-1) to blend factor
                            t = max(0.0, min(1.0, 1.0 - (nearest / max(1, pred_duration))))
                            pred_color = _blend_hex(palette.get('pred_light', '#fff5f5'), palette.get('pred_dark', '#ff9999'), t)
                            container.background_color = pred_color
                            container.border_width = 1
                            container.border_color = palette.get('pred_dark', '#ff9999')
                            # If it's the predicted start date, add the start marker and duration
                            if d in predicted_starts:
                                pred_mark = ui.Label()
                                pred_mark.frame = (cell_w-24, 2, 20, 20)
                                pred_mark.text = "◔"
                                pred_mark.font = ('<system>', 16)
                                pred_mark.text_color = palette.get('pred_dark', '#ff9999')
                                container.add_subview(pred_mark)

                                dur_label = ui.Label()
                                dur_label.frame = (cell_w-24, 20, 20, 16)
                                dur_label.text = str(pred_duration)
                                dur_label.font = ('<system>', 10)
                                dur_label.text_color = palette.get('pred_dark', '#ff9999')
                                dur_label.alignment = ui.ALIGN_CENTER
                                container.add_subview(dur_label)

                        # fertility highlight bar (thin bar at top of cell)
                        if 'fertile' in s:
                            try:
                                fert_bar = ui.View(frame=(0, 0, container.width, 6))
                                fert_bar.background_color = '#ffd0ff'
                                container.add_subview(fert_bar)
                            except Exception:
                                # geometry may not be set on some layouts; ignore if it fails
                                pass

                        # stack period and sex buttons vertically at bottom-left
                        # only show toggle buttons for today and past dates
                        if d <= today:
                            # period toggle button (above) - use blood-drop icon and intensity shading
                            pbtn = ui.Button(frame=(4, cell_h-60, 28, 24))
                            pbtn.title = '🩸'
                            pbtn.font = ('<system>', 14)
                            shades = palette.get('period_shades', ['#ffebeb', '#ffb3b3', '#ff6666'])
                            if intensity > 0:
                                pbtn.background_color = shades[max(0, min(2, intensity-1))]
                            else:
                                pbtn.background_color = '#ffffff'
                            pbtn.action = (lambda sender, dd=d: self.toggle_period(dd))
                            container.add_subview(pbtn)

                            # sex toggle button (below period button) - heart icon
                            sbtn = ui.Button(frame=(4, cell_h-30, 28, 24))
                            sbtn.title = '♥'
                            sbtn.font = ('<system>', 14)
                            sbtn.background_color = palette.get('sex', '#ccffcc') if 'sex' in s else '#ffffff'
                            sbtn.action = (lambda sender, dd=d: self.toggle_sex(dd))
                            container.add_subview(sbtn)

                        # allow tapping the day to open options as well
                        # already done via `opt` overlay

                    grid.add_subview(container)
                    x += cell_w
                y += cell_h
            self.add_subview(grid)

        def toggle_period(self, d: date):
            toggle_period_day(d)
            self.data = load_data()
            self.build_grid()

        def nav_month(self, delta: int):
            """Navigate months forward (delta=1) or back (delta=-1)."""
            m = self.month + delta
            y = self.year
            if m < 1:
                m = 12
                y -= 1
            elif m > 12:
                m = 1
                y += 1
            self.year = y
            self.month = m
            self.build_grid()

        def go_today(self, sender=None):
            t = date.today()
            self.year = t.year
            self.month = t.month
            self.build_grid()

        def toggle_sex(self, d: date):
            toggle_sex(d)
            self.data = load_data()
            self.build_grid()

        def show_menu(self, sender):
            # Create menu view with more height for spacing
            menu_view = ui.View(frame=(0, 0, self.bounds.width, 750))  # taller for comfort
            # use theme palette
            data_local = load_data()
            pal = get_palette(data_local.get('settings', {}).get('theme', 'light'))
            menu_view.background_color = pal.get('bg', '#ffffff')
            
            # Close button
            btn_close = ui.Button(title='×')
            btn_close.frame = (self.width - 46, 6, 40, 40)
            btn_close.font = ('<system>', 24)
            btn_close.action = lambda sender: menu_view.close()
            menu_view.add_subview(btn_close)
            
            # Title
            title = ui.Label()
            title.text = 'Menu'
            title.font = ('<system-bold>', 20)
            title.text_color = pal.get('text', '#000000')
            title.frame = (20, 30, 200, 30)  # moved down slightly
            menu_view.add_subview(title)
            
            # Stats section
            stats_title = ui.Label()
            stats_title.text = 'Statistics'
            stats_title.font = ('<system-bold>', 16)
            stats_title.frame = (20, 90, 200, 24)  # more space after title
            menu_view.add_subview(stats_title)
            
            data = load_data()
            periods = [p['start'] for p in data.get('periods', [])]
            settings = data.get('settings', {'cycle_length': 28, 'luteal_phase': 14})
            pred = predict_from_periods(periods, settings.get('cycle_length', 28), settings.get('luteal_phase', 14), lookahead_months=3)
            avg = pred.get('avg_cycle', settings.get('cycle_length', 28))
            
            stats_text = ui.TextView()
            stats_text.editable = False
            stats_text.frame = (20, 120, self.width - 40, 140)  # taller and more space
            stats_text.background_color = pal.get('panel', '#f7f7f7')
            stats_text.text_color = pal.get('text', '#000000')
            stats_text.text = f"Average cycle length: {avg} days\n\nNext ovulation dates:\n"
            for d in pred.get('ovulations', [])[:3]:
                stats_text.text += f"• {d}\n"
            menu_view.add_subview(stats_text)
            
            # Settings section
            settings_title = ui.Label()
            settings_title.text = 'Settings'
            settings_title.font = ('<system-bold>', 16)
            settings_title.frame = (20, 280, 200, 24)  # moved down
            menu_view.add_subview(settings_title)
            
            # Cycle length setting
            cycle_label = ui.Label()
            cycle_label.text = 'Cycle length (days):'
            cycle_label.frame = (20, 340, 150, 30)  # more space after section title
            menu_view.add_subview(cycle_label)
            
            cycle_field = ui.TextField()
            cycle_field.text = str(settings.get('cycle_length', 28))
            cycle_field.frame = (170, 340, 60, 30)
            cycle_field.keyboard_type = ui.KEYBOARD_NUMBER_PAD
            menu_view.add_subview(cycle_field)
            
            # Luteal phase setting
            luteal_label = ui.Label()
            luteal_label.text = 'Luteal phase (days):'
            luteal_label.frame = (20, 390, 150, 30)  # more space between inputs
            menu_view.add_subview(luteal_label)
            
            luteal_field = ui.TextField()
            luteal_field.text = str(settings.get('luteal_phase', 14))
            luteal_field.frame = (170, 390, 60, 30)
            luteal_field.keyboard_type = ui.KEYBOARD_NUMBER_PAD
            menu_view.add_subview(luteal_field)

            # Theme toggle
            theme_state = {'theme': settings.get('theme', 'light')}
            theme_label = ui.Label()
            theme_label.text = 'Theme:'
            theme_label.frame = (20, 420, 80, 30)  # moved down
            menu_view.add_subview(theme_label)

            theme_btn = ui.Button(title=theme_state['theme'].capitalize())
            theme_btn.frame = (110, 420, 80, 30)  # moved down
            def _toggle_theme(sender):
                theme_state['theme'] = 'dark' if theme_state['theme'] == 'light' else 'light'
                sender.title = theme_state['theme'].capitalize()
            theme_btn.action = _toggle_theme
            menu_view.add_subview(theme_btn)
            
            # Save button
            def save_settings(sender):
                try:
                    c = int(cycle_field.text)
                    l = int(luteal_field.text)
                    set_settings(c, l, theme_state.get('theme', 'light'))
                    self.data = load_data()
                    self.build_grid()
                    menu_view.close()
                except Exception:
                    console.alert('Error', 'Please enter valid numbers')
            
            save_btn = ui.Button(title='Save Settings')
            save_btn.frame = (20, 500, 120, 32)  # more space before actions
            save_btn.action = save_settings
            menu_view.add_subview(save_btn)

            # Migration and undo/redo buttons
            def _run_migration(sender):
                migrated = migrate_period_days_to_levels()
                # reload data and rebuild calendar
                self.data = load_data()
                self.build_grid()
                if migrated:
                    try:
                        console.alert('Migration', 'Converted legacy period_days to period_levels')
                    except Exception:
                        pass
                else:
                    try:
                        console.alert('Migration', 'No legacy period_days found; nothing to do')
                    except Exception:
                        pass

            def _do_undo(sender):
                ok = undo()
                if ok:
                    self.data = load_data()
                    self.build_grid()
                try:
                    console.alert('Undo', 'Undo performed' if ok else 'Nothing to undo')
                except Exception:
                    pass

            def _do_redo(sender):
                ok = redo()
                if ok:
                    self.data = load_data()
                    self.build_grid()
                try:
                    console.alert('Redo', 'Redo performed' if ok else 'Nothing to redo')
                except Exception:
                    pass

            mig_btn = ui.Button(title='Migrate Data')
            mig_btn.frame = (150, 500, 120, 32)  # aligned with save button
            mig_btn.action = _run_migration
            menu_view.add_subview(mig_btn)

            undo_btn = ui.Button(title='↩ Undo')  # added arrow
            undo_btn.frame = (20, 550, 80, 32)  # moved down, aligned left
            undo_btn.action = _do_undo
            menu_view.add_subview(undo_btn)

            redo_btn = ui.Button(title='Redo ↪')  # added arrow
            redo_btn.frame = (110, 550, 80, 32)  # next to undo
            redo_btn.action = _do_redo
            menu_view.add_subview(redo_btn)
            
            # Present the menu
            menu_view.present('sheet')


def run_pythonista_ui():
    v = CalendarView(frame=(0, 0, 375, 667))
    v.present('sheet')


def run_tk_ui():
    # Minimal Tkinter calendar UI for macOS testing
    import calendar
    cur_year = date.today().year
    cur_month = date.today().month

    def menu_dialog():
        # Create a new top-level window for the menu
        menu = tk.Toplevel(root)
        menu.title('Menu')
        menu.geometry('300x500')
        
        # Title
        tk.Label(menu, text='Menu', font=('TkDefaultFont', 16, 'bold')).pack(pady=10)
        
        # Stats section
        stats_frame = tk.LabelFrame(menu, text='Statistics', padx=10, pady=10)
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        data = load_data()
        periods = [p['start'] for p in data.get('periods', [])]
        settings = data.get('settings', {'cycle_length': 28, 'luteal_phase': 14})
        pred = predict_from_periods(periods, settings.get('cycle_length', 28), settings.get('luteal_phase', 14), lookahead_months=3)
        avg = pred.get('avg_cycle', settings.get('cycle_length', 28))
        
        stats_text = f"Average cycle length: {avg} days\n\nNext ovulation dates:\n"
        for d in pred.get('ovulations', [])[:3]:
            stats_text += f"• {d}\n"
        
        stats_label = tk.Label(stats_frame, text=stats_text, justify='left')
        stats_label.pack(anchor='w')
        
        # Settings section
        settings_frame = tk.LabelFrame(menu, text='Settings', padx=10, pady=10)
        settings_frame.pack(fill='x', padx=10, pady=5)
        
        # Cycle length
        cycle_frame = tk.Frame(settings_frame)
        cycle_frame.pack(fill='x', pady=5)
        tk.Label(cycle_frame, text='Cycle length (days):').pack(side='left')
        cycle_var = tk.StringVar(value=str(settings.get('cycle_length', 28)))
        cycle_entry = tk.Entry(cycle_frame, textvariable=cycle_var, width=5)
        cycle_entry.pack(side='right')
        
        # Luteal phase
        luteal_frame = tk.Frame(settings_frame)
        luteal_frame.pack(fill='x', pady=5)
        tk.Label(luteal_frame, text='Luteal phase (days):').pack(side='left')
        luteal_var = tk.StringVar(value=str(settings.get('luteal_phase', 14)))
        luteal_entry = tk.Entry(luteal_frame, textvariable=luteal_var, width=5)
        luteal_entry.pack(side='right')

        # Theme selector
        theme_frame = tk.Frame(settings_frame)
        theme_frame.pack(fill='x', pady=5)
        tk.Label(theme_frame, text='Theme:').pack(side='left')
        theme_var = tk.StringVar(value=str(settings.get('theme', 'light')))
        theme_menu = tk.OptionMenu(theme_frame, theme_var, 'light', 'dark')
        theme_menu.pack(side='right')
        
        def save_settings():
            try:
                c = int(cycle_var.get())
                l = int(luteal_var.get())
                set_settings(c, l, theme_var.get())
                refresh_calendar(root, nav_state['year'], nav_state['month'])
                menu.destroy()
            except ValueError:
                messagebox.showerror('Error', 'Please enter valid numbers')
        
        # Save button
        tk.Button(menu, text='Save Settings', command=save_settings).pack(pady=10)
        
        # Close button
        tk.Button(menu, text='Close', command=menu.destroy).pack(pady=5)

        # Migration and undo/redo
        def _run_migration():
            migrated = migrate_period_days_to_levels()
            if migrated:
                messagebox.showinfo('Migration', 'Converted legacy period_days to period_levels')
                refresh_calendar(root, nav_state['year'], nav_state['month'])
            else:
                messagebox.showinfo('Migration', 'No legacy period_days found; nothing to do')

        def _do_undo():
            ok = undo()
            if ok:
                refresh_calendar(root, nav_state['year'], nav_state['month'])
            messagebox.showinfo('Undo', 'Undo performed' if ok else 'Nothing to undo')

        def _do_redo():
            ok = redo()
            if ok:
                refresh_calendar(root, nav_state['year'], nav_state['month'])
            messagebox.showinfo('Redo', 'Redo performed' if ok else 'Nothing to redo')

        tk.Button(menu, text='Migrate Data', command=_run_migration).pack(pady=2)
        tk.Button(menu, text='Undo', command=_do_undo).pack(pady=2)
        tk.Button(menu, text='Redo', command=_do_redo).pack(pady=2)
        
        # Make the window modal
        menu.transient(root)
        menu.grab_set()
        root.wait_window(menu)

    def refresh_calendar(root, year, month):
        for widget in root.winfo_children():
            widget.destroy()
        data = load_data()
        settings = data.get('settings', {'cycle_length': 28, 'luteal_phase': 14, 'theme': 'light'})
        theme = settings.get('theme', 'light')
        palette = get_palette(theme)
        header = tk.Frame(root)
        header.pack(fill='x')
        tk.Button(header, text='Prev', command=lambda: nav(-1)).pack(side='left')
        tk.Button(header, text='Next', command=lambda: nav(1)).pack(side='left')
        month_lbl = tk.Label(header, text=f"{calendar.month_name[month]} {year}", font=('TkDefaultFont', 12, 'bold'))
        month_lbl.pack(side='left', padx=8)
        tk.Button(header, text='Today', command=lambda: jump_to_today()).pack(side='left')
        # Add hamburger menu button
        tk.Button(header, text='≡', command=menu_dialog, font=('TkDefaultFont', 14)).pack(side='right', padx=5)

        # legend
        legend = tk.Frame(root)
        legend.pack(fill='x', pady=4)
        def _legend_item(parent, color, label):
            f = tk.Frame(parent)
            tk.Label(f, width=2, bg=color).pack(side='left')
            tk.Label(f, text=label).pack(side='left', padx=4)
            return f
        _legend_item(legend, '#ffcccc', 'Period').pack(side='left', padx=6)
        # period intensity examples
        shades = palette.get('period_shades', ['#ffebeb', '#ffb3b3', '#ff6666'])
        for i, sh in enumerate(shades, start=1):
            _legend_item(legend, sh, f'Period {"light" if i==1 else ("med" if i==2 else "heavy")}').pack(side='left', padx=4)
        _legend_item(legend, '#ffd0ff', 'Fertile').pack(side='left', padx=6)
        _legend_item(legend, '#cce0ff', 'Ovulation').pack(side='left', padx=6)
        _legend_item(legend, '#ccffcc', 'Sex').pack(side='left', padx=6)
        
        # Add predicted marker to legend
        pred_legend = tk.Frame(legend)
        pred_container = tk.Frame(pred_legend)
        tk.Label(pred_container, text="◔", font=('TkDefaultFont', 12), fg='#ff9999').pack()
        tk.Label(pred_container, text="5", font=('TkDefaultFont', 8), fg='#ff9999').pack()
        pred_container.pack(side='left')
        tk.Label(pred_legend, text=" Expected (days)", fg='#ff9999').pack(side='left', padx=4)
        pred_legend.pack(side='left', padx=6)

        cal_frame = tk.Frame(root)
        cal_frame.pack()
        cal = calendar.monthcalendar(year, month)

        # weekday header
        weekdays = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        for i, wd in enumerate(weekdays):
            tk.Label(cal_frame, text=wd, width=6).grid(row=0, column=i)

            # Get predicted cycles and calculate duration
            period_starts = [p['start'] for p in data.get('periods', [])]
            durations = [p.get('duration', 5) for p in data.get('periods', [])]
            pred_duration = int(round(sum(durations) / len(durations))) if durations else 5
            
            predictions = predict_from_periods(
                period_starts,
                settings.get('cycle_length', 28),
                settings.get('luteal_phase', 14),
                lookahead_months=6
            )
            
            # Calculate all predicted period days
            predicted_days = set()
            predicted_starts = set()
            for start_iso in predictions.get('predicted_cycles', []):
                if start_iso <= today.isoformat():
                    continue  # skip past/current predictions
                start_date = datetime.strptime(start_iso, '%Y-%m-%d').date()
                predicted_starts.add(start_date)
                # Add all days in the predicted duration
                for i in range(pred_duration):
                    predicted_days.add(start_date + timedelta(days=i))

            status_map = day_status_for_month(
                data.get('periods', []),
                list(data.get('period_levels', {}).keys()),
                data.get('sex', []),
                settings.get('cycle_length', 28),
                settings.get('luteal_phase', 14),
                year,
                month,
            )
            
            today = date.today()
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                if day == 0:
                    lbl = tk.Label(cal_frame, text='', width=6, height=3, bg='#efefef', relief='ridge')
                    lbl.grid(row=r+1, column=c, padx=1, pady=1)
                else:
                    d = date(year, month, day)
                    iso = d.isoformat()
                    s = status_map.get(iso, set())
                    # per-day intensity map
                    intensity = int(data.get('period_levels', {}).get(iso, 0))
                    # choose background based on priority: period intensity > fertile > ovulation > sex
                    bg = palette.get('cell', 'white') if 'palette' in globals() else 'white'
                    if intensity > 0 or 'period' in s:
                        shades = palette.get('period_shades', ['#ffebeb', '#ffb3b3', '#ff6666'])
                        bg = shades[max(0, min(2, intensity-1))]
                    elif 'fertile' in s:
                        bg = palette.get('fertile', '#ffd0ff')
                    elif 'ovulation' in s:
                        bg = palette.get('ovulation', '#cce0ff')
                    elif 'sex' in s:
                        bg = palette.get('sex', '#ccffcc')
                    # Get predicted period starts
                    period_starts = [p['start'] for p in data.get('periods', [])]
                    predictions = predict_from_periods(
                        period_starts,
                        settings.get('cycle_length', 28),
                        settings.get('luteal_phase', 14),
                        lookahead_months=6
                    )
                    predicted_starts = set([
                        datetime.strptime(d, '%Y-%m-%d').date()
                        for d in predictions.get('predicted_cycles', [])
                        if d > today.isoformat()  # only future predictions
                    ])

                    cell = tk.Frame(cal_frame, width=48, height=64, bg=bg, relief='ridge', bd=1)
                    cell.grid_propagate(False)
                    cell.grid(row=r+1, column=c, padx=1, pady=1)
                    
                    # predicted period days indicator (gradient by proximity)
                    if d in predicted_days and d > today:
                        # find nearest predicted start >= d
                        nearest = None
                        for ps in predicted_starts:
                            if ps >= d:
                                dist = (ps - d).days
                                if nearest is None or dist < nearest:
                                    nearest = dist
                        if nearest is None:
                            nearest = 0
                        t = max(0.0, min(1.0, 1.0 - (nearest / max(1, pred_duration))))
                        pred_color = _blend_hex(palette.get('pred_light', '#fff5f5'), palette.get('pred_dark', '#ff9999'), t)
                        cell.config(relief='solid', bd=1)
                        cell.config(bg=pred_color)
                        for widget in cell.winfo_children():
                            try:
                                widget.config(bg=pred_color)
                            except Exception:
                                pass
                        if d in predicted_starts:
                            pred_container = tk.Frame(cell, bg=cell.cget('bg'))
                            pred_container.place(x=26, y=2)
                            pred_mark = tk.Label(pred_container, text='◔', font=('TkDefaultFont', 12), fg=palette.get('pred_dark', '#ff9999'), bg=cell.cget('bg'))
                            pred_mark.pack()
                            dur_label = tk.Label(pred_container, text=str(pred_duration), font=('TkDefaultFont', 8), fg=palette.get('pred_dark', '#ff9999'), bg=cell.cget('bg'))
                            dur_label.pack()
                    
                    # fertility bar at top (thin)
                    if 'fertile' in s:
                        bar = tk.Frame(cell, bg=palette.get('fertile', '#ffd0ff'), height=6)
                        bar.pack(fill='x', side='top')
                    # day number label
                    lbl = tk.Label(cell, text=str(day), bg=bg, fg=palette.get('text', '#000000'))
                    lbl.pack(anchor='nw', padx=2, pady=(4,0))
                    # toggles stacked vertically
                    p_active = (intensity > 0) or ('period' in s)
                    s_active = 'sex' in s
                    # only show toggle buttons for today and past dates
                    if d <= today:
                        # period button with blood-drop icon and intensity shading
                        shades = palette.get('period_shades', ['#ffebeb', '#ffb3b3', '#ff6666'])
                        p_bg = shades[max(0, min(2, intensity-1))] if intensity > 0 else '#ffffff'
                        pbtn = tk.Button(cell, text='🩸', bg=p_bg, command=lambda dd=d: (toggle_period_day(dd), refresh_calendar(root, nav_state['year'], nav_state['month'])))
                        pbtn.pack(side='top', anchor='w', padx=2, pady=(6,2))
                        sbtn = tk.Button(cell, text='♥', bg=palette.get('sex', '#ccffcc') if s_active else '#ffffff', command=lambda dd=d: (toggle_sex(dd), refresh_calendar(root, nav_state['year'], nav_state['month'])))
                        sbtn.pack(side='top', anchor='w', padx=2, pady=(0,4))
                    # highlight today
                    if d == today:
                        cell.config(bd=3, relief='solid')

    def settings_dialog():
        data = load_data()
        settings = data.get('settings', {'cycle_length': 28, 'luteal_phase': 14})
        c = simpledialog.askinteger('Cycle length', 'Days', initialvalue=settings.get('cycle_length', 28))
        l = simpledialog.askinteger('Luteal phase', 'Days', initialvalue=settings.get('luteal_phase', 14))
        if c and l:
            set_settings(c, l)
            refresh_calendar(root, nav_state['year'], nav_state['month'])

    def nav(delta):
        m = nav_state['month'] + delta
        y = nav_state['year']
        if m < 1:
            m = 12
            y -= 1
        elif m > 12:
            m = 1
            y += 1
        nav_state['month'] = m
        nav_state['year'] = y
        refresh_calendar(root, y, m)

    def jump_to_today():
        t = date.today()
        nav_state['year'] = t.year
        nav_state['month'] = t.month
        refresh_calendar(root, nav_state['year'], nav_state['month'])

    # build root
    root = tk.Tk()
    root.title('PregnancyTracker (macOS)')
    nav_state = {'year': cur_year, 'month': cur_month}
    refresh_calendar(root, cur_year, cur_month)
    root.mainloop()


def main():
    if _HAS_PYTHONISTA:
        run_pythonista_ui()
    else:
        if _HAS_TK:
            run_tk_ui()
        else:
            # Fallback: console mode
            print('Running in console mode. Tkinter not available.')
            data = load_data()
            print('Periods:', data.get('periods', []))
            print('Sex:', data.get('sex', []))
            print('Settings:', data.get('settings', {}))


if __name__ == '__main__':
    main()
