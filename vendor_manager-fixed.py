import customtkinter as ctk
import sqlite3
import bcrypt
import os
import subprocess
import sys
import platform
import webbrowser
from tkinter import filedialog, messagebox, simpledialog
import cv2
import pytesseract
import re
from datetime import datetime, timedelta

# --- Configuration ---
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor_db.sqlite")
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

TESSERACT_DOWNLOADS = {
    "Windows": "https://github.com/UB-Mannheim/tesseract/wiki",
    "Darwin": "https://formulae.brew.sh/formula/tesseract",
    "Linux": "https://tesseract-ocr.github.io/tessdoc/Installation.html"
}

class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.seed_sample_data()

    def create_tables(self):
        # --- Users & Profiles ---
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)""")
        
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, last_updated TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")

        # --- Billing Cycles & Payment Methods ---
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS billing_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)""")
        
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, method_name TEXT NOT NULL, account_last_four TEXT, is_default BOOLEAN DEFAULT 0)""")

        # --- Vendors ---
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT, phone TEXT,
            account_number TEXT, billing_cycle_id INTEGER, payment_method_id INTEGER, notes TEXT,
            last_scan_data TEXT, FOREIGN KEY(billing_cycle_id) REFERENCES billing_cycles(id),
            FOREIGN KEY(payment_method_id) REFERENCES payment_methods(id))""")

        # --- Bills ---
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            description TEXT,
            category TEXT,
            amount REAL NOT NULL,
            paid_amount REAL DEFAULT 0,
            due_date TEXT NOT NULL,
            paid_date TEXT,
            frequency TEXT,
            is_recurring BOOLEAN DEFAULT 0,
            receipt_path TEXT,
            status TEXT DEFAULT 'Pending',
            custom_field_1 TEXT,
            custom_field_2 TEXT,
            custom_field_3 TEXT,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY(vendor_id) REFERENCES vendors(id) ON DELETE CASCADE
        )""")
        
        # Seed default cycles if empty
        self.cursor.execute("SELECT count(*) FROM billing_cycles")
        if self.cursor.fetchone()[0] == 0:
            cycles = ["Monthly", "Semi-Annually", "Annually", "As Needed", "Other"]
            for c in cycles:
                self.cursor.execute("INSERT INTO billing_cycles (name) VALUES (?)", (c,))
        
        self.conn.commit()

    def seed_sample_data(self):
        self.cursor.execute("SELECT count(*) FROM vendors")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("SELECT id FROM billing_cycles WHERE name='Monthly'")
            cycle_id = self.cursor.fetchone()[0]
            
            self.cursor.execute(
                "INSERT INTO vendors (name, address, phone, account_number, billing_cycle_id) VALUES (?, ?, ?, ?, ?)",
                ("Sample Vendor Inc.", "123 Business Rd", "555-0199", "ACC-001", cycle_id)
            )
            vendor_id = self.cursor.lastrowid
            
            today = datetime.now()
            bills = [
                (vendor_id, "Office Rent", "Rent", 1500.00, 0.00, (today + timedelta(days=5)).strftime("%Y-%m-%d"), "Monthly", 1, "Pending", "Office", "", ""),
                (vendor_id, "Internet Service", "Utilities", 89.99, 89.99, (today - timedelta(days=2)).strftime("%Y-%m-%d"), "Monthly", 1, "Paid", "ISP", "", ""),
                (vendor_id, "Software License", "Software", 299.99, 0.00, (today + timedelta(days=30)).strftime("%Y-%m-%d"), "Annual", 1, "Pending", "SaaS", "", ""),
                (vendor_id, "Freelance Design", "Services", 500.00, 0.00, (today + timedelta(days=1)).strftime("%Y-%m-%d"), "Infrequent", 0, "Pending", "Project X", "", "")
            ]
            
            for b in bills:
                self.cursor.execute("""
                    INSERT INTO bills (vendor_id, description, category, amount, paid_amount, due_date, frequency, is_recurring, status, custom_field_1, custom_field_2, custom_field_3, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (*b, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            self.conn.commit()

    def register_user(self, username, password):
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            self.cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def login_user(self, username, password):
        self.cursor.execute("SELECT password_hash FROM users WHERE username=?", (username,))
        result = self.cursor.fetchone()
        if result:
            stored_hash = result[0]
            if isinstance(stored_hash, str): stored_hash = stored_hash.encode("utf-8")
            if bcrypt.checkpw(password.encode("utf-8"), stored_hash): return True
        return False

    def close(self): self.conn.close()

    def add_vendor(self, name, address, phone, account, cycle_name, method_name, notes=""):
        self.cursor.execute("SELECT id FROM billing_cycles WHERE name=?", (cycle_name,))
        cycle_row = self.cursor.fetchone()
        if not cycle_row: raise ValueError("Please select a valid billing cycle.")
        cycle_id = cycle_row[0]

        method_id = None
        if method_name and method_name != "None":
            self.cursor.execute("SELECT id FROM payment_methods WHERE method_name=?", (method_name,))
            method_row = self.cursor.fetchone()
            if method_row:
                method_id = method_row[0]

        self.cursor.execute("""INSERT INTO vendors (name, address, phone, account_number, billing_cycle_id, payment_method_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (name, address, phone, account, cycle_id, method_id, notes))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_billing_cycle_names(self):
        self.cursor.execute("SELECT name FROM billing_cycles ORDER BY id")
        return [row[0] for row in self.cursor.fetchall()]

    def get_payment_method_names(self):
        self.cursor.execute("SELECT method_name FROM payment_methods ORDER BY id")
        return [row[0] for row in self.cursor.fetchall()]

    def add_payment_method(self, method_name, account_last_four):
        self.cursor.execute("INSERT INTO payment_methods (method_name, account_last_four) VALUES (?, ?)", (method_name, account_last_four))
        self.conn.commit()

    def get_all_vendors(self):
        self.cursor.execute("""SELECT v.name, v.address, v.phone, v.account_number, bc.name, pm.method_name
            FROM vendors v JOIN billing_cycles bc ON v.billing_cycle_id = bc.id
            LEFT JOIN payment_methods pm ON v.payment_method_id = pm.id""")
        return self.cursor.fetchall()

    def get_user_profile(self, username):
        self.cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        row = self.cursor.fetchone()
        if not row: return None
        user_id = row[0]
        self.cursor.execute("SELECT full_name, email, phone, last_updated FROM user_profiles WHERE user_id=?", (user_id,))
        profile = self.cursor.fetchone()
        if not profile: return {"full_name": "", "email": "", "phone": "", "last_updated": ""}
        return {"full_name": profile[0] or "", "email": profile[1] or "", "phone": profile[2] or "", "last_updated": profile[3] or ""}

    def save_user_profile(self, username, full_name, email, phone, last_updated):
        self.cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        row = self.cursor.fetchone()
        if not row: raise ValueError("User not found.")
        user_id = row[0]
        self.cursor.execute("""INSERT INTO user_profiles (user_id, full_name, email, phone, last_updated)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET
            full_name=excluded.full_name, email=excluded.email, phone=excluded.phone, last_updated=excluded.last_updated""",
            (user_id, full_name, email, phone, last_updated))
        self.conn.commit()

    def get_all_bills(self):
        self.cursor.execute("""
            SELECT b.id, v.name as vendor_name, b.description, b.category, b.amount, b.paid_amount, 
                   b.due_date, b.paid_date, b.frequency, b.status, b.custom_field_1, b.custom_field_2, b.custom_field_3, b.notes
            FROM bills b
            JOIN vendors v ON b.vendor_id = v.id
            ORDER BY b.due_date ASC
        """)
        return self.cursor.fetchall()

    def create_bill(self, vendor_id, description, category, amount, due_date, frequency, status, custom1, custom2, custom3, notes):
        self.cursor.execute("""
            INSERT INTO bills (vendor_id, description, category, amount, paid_amount, due_date, frequency, status, custom_field_1, custom_field_2, custom_field_3, notes, created_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vendor_id, description, category, amount, due_date, frequency, status, custom1, custom2, custom3, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.conn.commit()
        return self.cursor.lastrowid

    def update_bill_status(self, bill_id, is_paid, paid_amount=None):
        self.cursor.execute("SELECT amount FROM bills WHERE id=?", (bill_id,))
        row = self.cursor.fetchone()
        if not row: return
        
        amount = row[0]
        new_paid = paid_amount if paid_amount is not None else (amount if is_paid else 0)
        
        # Ensure paid amount doesn't exceed total
        if new_paid > amount:
            new_paid = amount
            
        new_status = "Paid" if new_paid >= amount else ("Overdue" if is_paid else "Pending")
        if is_paid and new_paid == 0:
             new_status = "Pending" # Edge case: marked paid but 0 amount?

        paid_date_val = datetime.now().strftime("%Y-%m-%d") if is_paid and new_paid >= amount else None
        
        self.cursor.execute("""UPDATE bills 
            SET paid_amount=?, status=?, paid_date=? 
            WHERE id=?""", (new_paid, new_status, paid_date_val, bill_id))
        self.conn.commit()

    def get_bill_details(self, bill_id):
        self.cursor.execute("""
            SELECT b.id, v.name as vendor_name, b.description, b.category, b.amount, b.paid_amount, 
                   b.due_date, b.paid_date, b.frequency, b.status, b.custom_field_1, b.custom_field_2, b.custom_field_3, b.notes
            FROM bills b
            JOIN vendors v ON b.vendor_id = v.id
            WHERE b.id = ?
        """, (bill_id,))
        return self.cursor.fetchone()

    def update_bill(self, bill_id, vendor_id, description, category, amount, due_date, frequency, status, custom1, custom2, custom3, notes):
        self.cursor.execute("""
            UPDATE bills SET vendor_id=?, description=?, category=?, amount=?, due_date=?, frequency=?, status=?, 
            custom_field_1=?, custom_field_2=?, custom_field_3=?, notes=?
            WHERE id=?
        """, (vendor_id, description, category, amount, due_date, frequency, status, custom1, custom2, custom3, notes, bill_id))
        self.conn.commit()

    def get_vendor_by_name(self, name):
        self.cursor.execute("SELECT id FROM vendors WHERE name=?", (name,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def get_frequency_options(self):
        return ["Weekly", "Bi-Weekly", "Monthly", "Semi-Annual", "Annual", "Infrequent", "Custom"]

    def get_categories(self):
        return ["Rent", "Utilities", "Software", "Services", "Supplies", "Insurance", "Taxes", "Other"]

# --- Helper Functions for OCR ---
def check_tesseract_installed():
    try:
        subprocess.run(["tesseract", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True, None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False, "Tesseract OCR is not installed or not in your system PATH."

def open_tesseract_installer():
    system = platform.system()
    url = TESSERACT_DOWNLOADS.get(system, "https://tesseract-ocr.github.io/tessdoc/")
    msg = f"Tesseract OCR is required for scanning.\n\nWe have opened the official download page for {system}.\nPlease install it and restart this application."
    messagebox.showinfo("Install Tesseract", msg)
    try: webbrowser.open(url)
    except Exception as e: messagebox.showerror("Error", f"Could not open browser: {e}")

# --- Application UI ---
class VendorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_user = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.title("Vendor Management System")
        self.geometry("900x650")
        self.show_login_screen()

    def _is_valid_email(self, email):
        if not email: return True
        return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None

    def _is_valid_phone(self, phone):
        if not phone: return True
        cleaned = re.sub(r"[^\d]", "", phone)
        return len(cleaned) >= 7

    def bring_dialog_to_front(self, dialog):
        try:
            dialog.transient(self)
            self.focus_force()
            self.after(50, lambda: dialog.focus_force())
            dialog.lift()
            dialog.attributes('-topmost', True)
            self.after(100, lambda: dialog.attributes('-topmost', False))
        except Exception:
            dialog.lift()
            dialog.focus_force()

    def clear_frame(self):
        for widget in self.winfo_children(): widget.destroy()

    def show_login_screen(self):
        self.clear_frame()
        frame = ctk.CTkFrame(self, corner_radius=10, width=350, height=280)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(frame, text="Vendor Manager Login", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=15)
        self.username_entry = ctk.CTkEntry(frame, placeholder_text="Username", height=28, width=280)
        self.username_entry.pack(pady=5)
        self.password_entry = ctk.CTkEntry(frame, placeholder_text="Password", show="*", height=28, width=280)
        self.password_entry.pack(pady=5)
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="Login", width=100, height=28, command=self.login).grid(row=0, column=0, padx=8)
        ctk.CTkButton(btn_frame, text="Register", width=100, height=28, command=self.register).grid(row=0, column=1, padx=8)
        self.username_entry.focus_set()

    def login(self):
        u = self.username_entry.get().strip()
        p = self.password_entry.get()
        if not u or not p:
            messagebox.showwarning("Input", "Please enter both username and password.")
            return
        if self.db.login_user(u, p):
            self.current_user = u
            self.show_main_dashboard()
        else:
            messagebox.showerror("Error", "Invalid credentials or user does not exist.")

    def register(self):
        u = self.username_entry.get().strip()
        p = self.password_entry.get()
        if u and p:
            if self.db.register_user(u, p):
                messagebox.showinfo("Success", "User registered! Please login.")
                self.username_entry.delete(0, 'end')
                self.password_entry.delete(0, 'end')
            else:
                messagebox.showerror("Error", "Username already exists.")
        else:
            messagebox.showwarning("Input", "Please fill all fields.")

    def show_main_dashboard(self):
        self.clear_frame()
        header = ctk.CTkFrame(self, height=45, fg_color="#2b2b2b")
        header.pack(fill="x")
        profile = self.db.get_user_profile(self.current_user) or {}
        display_name = profile.get("full_name", "").strip()
        first_name = display_name.split()[0] if display_name else self.current_user
        ctk.CTkLabel(header, text=f"Welcome, {first_name}", font=ctk.CTkFont(size=14)).pack(side="left", padx=15)
        ctk.CTkButton(header, text="Logout", width=70, height=28, command=self.show_login_screen).pack(side="right", padx=15)

        main_container = ctk.CTkScrollableFrame(self)
        main_container.pack(fill="both", expand=True, padx=15, pady=15)

        btn_grid = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_grid.pack(fill="x", pady=5)
        ctk.CTkButton(btn_grid, text="Add Vendor", command=self.open_add_vendor, width=140, height=32).grid(row=0, column=0, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="Add Payment", command=self.open_add_payment, width=140, height=32).grid(row=0, column=1, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="Scan OCR", command=self.open_scanner, width=140, height=32).grid(row=0, column=2, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="View Vendors", command=self.view_vendors, width=140, height=32).grid(row=0, column=3, padx=8, pady=5)
        
        btn_grid2 = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_grid2.pack(fill="x", pady=5)
        ctk.CTkButton(btn_grid2, text="Manage Bills", command=self.open_manage_bills, width=140, height=32).grid(row=0, column=0, padx=8, pady=5)
        ctk.CTkButton(btn_grid2, text="Profile", command=self.open_profile, width=140, height=32).grid(row=0, column=1, padx=8, pady=5)

        self.vendor_list_label = ctk.CTkLabel(main_container, text="Recent Vendors:", font=ctk.CTkFont(size=13, weight="bold"))
        self.vendor_list_label.pack(anchor="w", pady=(10, 3))
        self.vendor_list_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        self.vendor_list_frame.pack(fill="x", pady=3)
        self.refresh_vendor_list()

    def refresh_vendor_list(self):
        if not hasattr(self, "vendor_list_frame"): return
        for widget in self.vendor_list_frame.winfo_children():
            if isinstance(widget, ctk.CTkLabel): widget.destroy()
        vendors = self.db.get_all_vendors()
        for v in vendors[-5:]:
            method = v[5] if v[5] else "No method set"
            lbl = ctk.CTkLabel(self.vendor_list_frame, text=f"{v[0]} | Cycle: {v[4]} | Method: {method}", anchor="w", font=ctk.CTkFont(size=11))
            lbl.pack(fill="x", pady=1)

    # --- NEW: Manage Bills Dialog ---
    def open_manage_bills(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Manage Bills")
        dialog.geometry("900x600")
        self.bring_dialog_to_front(dialog)

        header_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(header_frame, text="Bill Management", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkButton(header_frame, text="+ Add New Bill", width=120, height=30, command=lambda: self.open_add_bill_dialog(dialog)).pack(side="right")

        scroll_frame = ctk.CTkScrollableFrame(dialog, width=860, height=450)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        bills = self.db.get_all_bills()
        
        if not bills:
            ctk.CTkLabel(scroll_frame, text="No bills found. Click '+ Add New Bill' to create one.", font=ctk.CTkFont(size=12)).pack(pady=20)
        else:
            today = datetime.now()
            for bill in bills:
                bid, vendor, desc, cat, amount, paid_amt, due_str, paid_date, freq, status, c1, c2, c3, notes = bill
                
                due_date = datetime.strptime(due_str, "%Y-%m-%d")
                days_diff = (due_date - today).days
                
                outstanding = amount - paid_amt
                is_overdue = days_diff < 0 and status != "Paid"
                
                if status == "Paid":
                    row_bg = "#2a3a2a"
                    text_color = "#4dff4d"
                elif is_overdue:
                    row_bg = "#3a2a2a"
                    text_color = "#ff4d4d"
                else:
                    row_bg = "#2a2a2a"
                    text_color = "#ffffff"

                row_frame = ctk.CTkFrame(scroll_frame, fg_color=row_bg, corner_radius=5)
                row_frame.pack(fill="x", pady=4, padx=5)

                var = ctk.BooleanVar(value=(status == "Paid"))
                chk = ctk.CTkCheckBox(row_frame, text="", variable=var, command=lambda b=bid, v=var: self.toggle_bill_status(b, v.get()))
                chk.pack(side="left", padx=10, pady=10)
                
                status_lbl = ctk.CTkLabel(row_frame, text=status, font=ctk.CTkFont(size=11, weight="bold"), text_color=text_color)
                status_lbl.pack(side="left", padx=5)

                details_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                details_frame.pack(side="left", fill="x", expand=True, padx=10)
                
                top_line = f"{vendor} - {desc} ({cat})"
                ctk.CTkLabel(details_frame, text=top_line, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
                
                bottom_line = f"Freq: {freq} | Due: {due_str} ({days_diff} days) | Paid: ${paid_amt:.2f} / ${amount:.2f}"
                ctk.CTkLabel(details_frame, text=bottom_line, font=ctk.CTkFont(size=11), text_color="#aaaaaa").pack(anchor="w")
                
                if c1 or c2 or c3:
                    custom_line = f"Custom: {c1} | {c2} | {c3}"
                    ctk.CTkLabel(details_frame, text=custom_line, font=ctk.CTkFont(size=10), text_color="#888888").pack(anchor="w")

                btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                btn_frame.pack(side="right", padx=10)
                ctk.CTkButton(btn_frame, text="Edit", width=60, height=24, command=lambda b=bid: self.edit_bill(b)).pack(padx=2)
                ctk.CTkButton(btn_frame, text="Delete", width=60, height=24, fg_color="#cc0000", hover_color="#990000", command=lambda b=bid: self.delete_bill(b)).pack(padx=2)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=dialog.destroy).pack(pady=5)

    def open_add_bill_dialog(self, parent_window):
        add_win = ctk.CTkToplevel(parent_window)
        add_win.title("Add New Bill")
        add_win.geometry("400x900")
        self.bring_dialog_to_front(add_win)

        ctk.CTkLabel(add_win, text="Bill Details", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(add_win, text="Vendor", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        vendors = self.db.get_all_vendors()
        vendor_names = [v[0] for v in vendors]
        vendor_names.insert(0, "--- Create New Vendor ---")
        vendor_var = ctk.StringVar(value=vendor_names[0])
        vendor_combo = ctk.CTkComboBox(add_win, values=vendor_names, variable=vendor_var, height=28, width=300)
        vendor_combo.pack(pady=2)

        new_vendor_frame = ctk.CTkFrame(add_win, fg_color="#333333", corner_radius=5)
        new_vendor_frame.pack(pady=5, fill="x", padx=20)
        new_vendor_frame.pack_forget()

        def on_vendor_change(*args):
            if vendor_var.get() == "--- Create New Vendor ---":
                new_vendor_frame.pack(fill="x", padx=20)
            else:
                new_vendor_frame.pack_forget()
        
        vendor_var.trace("w", on_vendor_change)

        ctk.CTkLabel(new_vendor_frame, text="New Vendor Name", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        new_v_name = ctk.CTkEntry(new_vendor_frame, height=24)
        new_v_name.pack(pady=2, padx=10)
        new_v_addr = ctk.CTkEntry(new_vendor_frame, height=24, placeholder_text="Address")
        new_v_addr.pack(pady=2, padx=10)
        new_v_phone = ctk.CTkEntry(new_vendor_frame, height=24, placeholder_text="Phone")
        new_v_phone.pack(pady=2, padx=10)

        ctk.CTkLabel(add_win, text="Description", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        desc_entry = ctk.CTkEntry(add_win, height=28, width=300)
        desc_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Category", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        categories = self.db.get_categories()
        cat_combo = ctk.CTkComboBox(add_win, values=categories, height=28, width=300)
        cat_combo.pack(pady=2)
        if categories:
            cat_combo.set(categories[0])

        ctk.CTkLabel(add_win, text="Amount ($)", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        amt_entry = ctk.CTkEntry(add_win, height=28, width=300)
        amt_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Due Date", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        due_entry = ctk.CTkEntry(add_win, height=28, width=300, placeholder_text="YYYY-MM-DD")
        due_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Frequency", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        freq_combo = ctk.CTkComboBox(add_win, values=self.db.get_frequency_options(), height=28, width=300)
        freq_combo.pack(pady=2)

        ctk.CTkLabel(add_win, text="Custom Field 1", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c1_entry = ctk.CTkEntry(add_win, height=24, width=300)
        c1_entry.pack(pady=2)
        
        ctk.CTkLabel(add_win, text="Custom Field 2", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c2_entry = ctk.CTkEntry(add_win, height=24, width=300)
        c2_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Custom Field 3", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c3_entry = ctk.CTkEntry(add_win, height=24, width=300)
        c3_entry.pack(pady=2)

        def save_bill():
            try:
                desc = desc_entry.get().strip()
                cat = cat_combo.get()
                amt = float(amt_entry.get())
                due = due_entry.get().strip()
                freq = freq_combo.get()
                c1 = c1_entry.get().strip()
                c2 = c2_entry.get().strip()
                c3 = c3_entry.get().strip()

                if not desc or not due:
                    messagebox.showwarning("Input", "Description and Due Date are required.")
                    return

                selected_vendor = vendor_var.get()
                vendor_id = None
                if selected_vendor == "--- Create New Vendor ---":
                    v_name = new_v_name.get().strip()
                    if not v_name:
                        messagebox.showwarning("Input", "Vendor Name is required for new vendor.")
                        return
                    vendor_id = self.db.add_vendor(v_name, new_v_addr.get().strip(), new_v_phone.get().strip(), "", "Monthly", "No saved methods")
                else:
                    vendor_id = self.db.get_vendor_by_name(selected_vendor)
                    if not vendor_id:
                        messagebox.showerror("Error", "Vendor not found.")
                        return

                self.db.create_bill(vendor_id, desc, cat, amt, due, freq, "Pending", c1, c2, c3, "")
                messagebox.showinfo("Success", "Bill added successfully!")
                add_win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid Amount or Date format.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not add bill: {str(e)}")

        btn_frame = ctk.CTkFrame(add_win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save Bill", width=120, height=30, command=save_bill).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=120, height=30, command=add_win.destroy).pack(side="left", padx=10)

    def toggle_bill_status(self, bill_id, is_paid):
        try:
            self.db.update_bill_status(bill_id, is_paid)
            self.open_manage_bills()
        except Exception as e:
            messagebox.showerror("Error", f"Could not update bill status: {str(e)}")

    def edit_bill(self, bill_id):
        bill_data = self.db.get_bill_details(bill_id)
        if not bill_data:
            messagebox.showerror("Error", "Bill not found.")
            return

        bid, vendor_name, desc, cat, amount, paid_amt, due_str, paid_date, freq, status, c1, c2, c3, notes = bill_data

        edit_win = ctk.CTkToplevel(self)
        edit_win.title("Edit Bill")
        edit_win.geometry("400x900")
        self.bring_dialog_to_front(edit_win)

        ctk.CTkLabel(edit_win, text="Edit Bill", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(edit_win, text="Vendor", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        vendors = self.db.get_all_vendors()
        vendor_names = [v[0] for v in vendors]
        vendor_var = ctk.StringVar(value=vendor_name)
        vendor_combo = ctk.CTkComboBox(edit_win, values=vendor_names, variable=vendor_var, height=28, width=300)
        vendor_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Description", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        desc_entry = ctk.CTkEntry(edit_win, height=28, width=300)
        desc_entry.insert(0, desc)
        desc_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Category", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        categories = self.db.get_categories()
        cat_combo = ctk.CTkComboBox(edit_win, values=categories, height=28, width=300)
        cat_combo.set(cat)
        cat_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Amount ($)", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        amt_entry = ctk.CTkEntry(edit_win, height=28, width=300)
        amt_entry.insert(0, str(amount))
        amt_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Due Date", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        due_entry = ctk.CTkEntry(edit_win, height=28, width=300, placeholder_text="YYYY-MM-DD")
        due_entry.insert(0, due_str)
        due_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Frequency", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        freq_combo = ctk.CTkComboBox(edit_win, values=self.db.get_frequency_options(), height=28, width=300)
        freq_combo.set(freq)
        freq_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Status", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        status_combo = ctk.CTkComboBox(edit_win, values=["Pending", "Paid", "Overdue", "Disputed"], height=28, width=300)
        status_combo.set(status)
        status_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Custom Field 1", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c1_entry = ctk.CTkEntry(edit_win, height=24, width=300)
        c1_entry.insert(0, c1)
        c1_entry.pack(pady=2)
        
        ctk.CTkLabel(edit_win, text="Custom Field 2", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c2_entry = ctk.CTkEntry(edit_win, height=24, width=300)
        c2_entry.insert(0, c2)
        c2_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Custom Field 3", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        c3_entry = ctk.CTkEntry(edit_win, height=24, width=300)
        c3_entry.insert(0, c3)
        c3_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Notes", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        notes_entry = ctk.CTkTextbox(edit_win, height=60, width=300)
        notes_entry.insert("0.0", notes)
        notes_entry.pack(pady=2)

        def save_edits():
            try:
                vendor_name = vendor_var.get()
                vendor_id = self.db.get_vendor_by_name(vendor_name)
                if not vendor_id:
                    messagebox.showerror("Error", "Selected vendor not found.")
                    return

                new_desc = desc_entry.get().strip()
                new_cat = cat_combo.get()
                new_amt = float(amt_entry.get())
                new_due = due_entry.get().strip()
                new_freq = freq_combo.get()
                new_status = status_combo.get()
                new_c1 = c1_entry.get().strip()
                new_c2 = c2_entry.get().strip()
                new_c3 = c3_entry.get().strip()
                new_notes = notes_entry.get("0.0", "end-1c")

                if not new_desc or not new_due:
                    messagebox.showwarning("Input", "Description and Due Date are required.")
                    return

                self.db.update_bill(bid, vendor_id, new_desc, new_cat, new_amt, new_due, new_freq, new_status, new_c1, new_c2, new_c3, new_notes)
                messagebox.showinfo("Success", "Bill updated successfully!")
                edit_win.destroy()
                # Refresh the manage bills window if it's open
                # Note: In a real app, you'd track open windows better, but this works for now
                try:
                    self.open_manage_bills() 
                except:
                    pass
            except ValueError:
                messagebox.showerror("Error", "Invalid Amount or Date format.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not update bill: {str(e)}")

        btn_frame = ctk.CTkFrame(edit_win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save Changes", width=120, height=30, command=save_edits).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=120, height=30, command=edit_win.destroy).pack(side="left", padx=10)

    def delete_bill(self, bill_id):
        if messagebox.askyesno("Delete Bill", "Are you sure you want to delete this bill?"):
            try:
                self.db.cursor.execute("DELETE FROM bills WHERE id=?", (bill_id,))
                self.db.conn.commit()
                self.open_manage_bills()
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete bill: {str(e)}")

    # --- IMPLEMENTED: Add Vendor ---
    def open_add_vendor(self):
        add_win = ctk.CTkToplevel(self)
        add_win.title("Add New Vendor")
        add_win.geometry("400x900")
        self.bring_dialog_to_front(add_win)

        ctk.CTkLabel(add_win, text="Vendor Details", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(add_win, text="Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name_entry = ctk.CTkEntry(add_win, height=28, width=300)
        name_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Address", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        addr_entry = ctk.CTkEntry(add_win, height=28, width=300)
        addr_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Phone", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        phone_entry = ctk.CTkEntry(add_win, height=28, width=300)
        phone_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Account Number", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        acc_entry = ctk.CTkEntry(add_win, height=28, width=300)
        acc_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Billing Cycle", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        cycles = self.db.get_billing_cycle_names()
        cycle_combo = ctk.CTkComboBox(add_win, values=cycles, height=28, width=300)
        if cycles: cycle_combo.set(cycles[0])
        cycle_combo.pack(pady=2)

        ctk.CTkLabel(add_win, text="Payment Method", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        methods = self.db.get_payment_method_names()
        method_combo = ctk.CTkComboBox(add_win, values=methods, height=28, width=300)
        method_combo.pack(pady=2)

        ctk.CTkLabel(add_win, text="Notes", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        notes_entry = ctk.CTkTextbox(add_win, height=60, width=300)
        notes_entry.pack(pady=2)

        def save_vendor():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Input", "Vendor Name is required.")
                return
            
            try:
                self.db.add_vendor(
                    name, 
                    addr_entry.get().strip(), 
                    phone_entry.get().strip(), 
                    acc_entry.get().strip(), 
                    cycle_combo.get(), 
                    method_combo.get(), 
                    notes_entry.get("0.0", "end-1c")
                )
                messagebox.showinfo("Success", "Vendor added successfully!")
                add_win.destroy()
                self.refresh_vendor_list()
            except Exception as e:
                messagebox.showerror("Error", f"Could not add vendor: {str(e)}")

        btn_frame = ctk.CTkFrame(add_win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save Vendor", width=120, height=30, command=save_vendor).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=120, height=30, command=add_win.destroy).pack(side="left", padx=10)

    # --- IMPLEMENTED: Add Payment Method ---
    def open_add_payment(self):
        add_win = ctk.CTkToplevel(self)
        add_win.title("Add Payment Method")
        add_win.geometry("350x300")
        self.bring_dialog_to_front(add_win)

        ctk.CTkLabel(add_win, text="Payment Method Details", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(add_win, text="Method Name (e.g., Visa ending in 1234)", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name_entry = ctk.CTkEntry(add_win, height=28, width=300)
        name_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Last Four Digits", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        last_four_entry = ctk.CTkEntry(add_win, height=28, width=300, placeholder_text="XXXX")
        last_four_entry.pack(pady=2)

        def save_payment():
            name = name_entry.get().strip()
            last_four = last_four_entry.get().strip()
            
            if not name or not last_four:
                messagebox.showwarning("Input", "Both fields are required.")
                return
            
            if not last_four.isdigit() or len(last_four) != 4:
                messagebox.showwarning("Input", "Last four digits must be exactly 4 numbers.")
                return

            try:
                self.db.add_payment_method(name, last_four)
                messagebox.showinfo("Success", "Payment method added!")
                add_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Could not add payment method: {str(e)}")

        btn_frame = ctk.CTkFrame(add_win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save", width=120, height=30, command=save_payment).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=120, height=30, command=add_win.destroy).pack(side="left", padx=10)

    # --- IMPLEMENTED: View Vendors ---
    def view_vendors(self):
        view_win = ctk.CTkToplevel(self)
        view_win.title("All Vendors")
        view_win.geometry("800x500")
        self.bring_dialog_to_front(view_win)

        ctk.CTkLabel(view_win, text="Vendor List", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)

        scroll_frame = ctk.CTkScrollableFrame(view_win, width=760, height=400)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        vendors = self.db.get_all_vendors()
        if not vendors:
            ctk.CTkLabel(scroll_frame, text="No vendors found.", font=ctk.CTkFont(size=12)).pack(pady=20)
        else:
            for v in vendors:
                # v: name, address, phone, account, cycle, method
                row_frame = ctk.CTkFrame(scroll_frame, fg_color="#2a2a2a", corner_radius=5)
                row_frame.pack(fill="x", pady=4, padx=5)
                
                ctk.CTkLabel(row_frame, text=f"{v[0]}", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=10, pady=10)
                ctk.CTkLabel(row_frame, text=f"| {v[1]}", font=ctk.CTkFont(size=11), text_color="#aaaaaa").pack(side="left", padx=5)
                ctk.CTkLabel(row_frame, text=f"| {v[4]}", font=ctk.CTkFont(size=11), text_color="#888888").pack(side="right", padx=10)

        btn_frame = ctk.CTkFrame(view_win, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=view_win.destroy).pack(pady=5)

    # --- IMPLEMENTED: Profile Management ---
    def open_profile(self):
        profile_win = ctk.CTkToplevel(self)
        profile_win.title("User Profile")
        profile_win.geometry("400x600")
        self.bring_dialog_to_front(profile_win)

        ctk.CTkLabel(profile_win, text="My Profile", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        profile_data = self.db.get_user_profile(self.current_user)
        
        ctk.CTkLabel(profile_win, text="Full Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        name_entry.insert(0, profile_data.get("full_name", ""))
        name_entry.pack(pady=2)

        ctk.CTkLabel(profile_win, text="Email", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        email_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        email_entry.insert(0, profile_data.get("email", ""))
        email_entry.pack(pady=2)

        ctk.CTkLabel(profile_win, text="Phone", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        phone_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        phone_entry.insert(0, profile_data.get("phone", ""))
        phone_entry.pack(pady=2)

        def save_profile():
            full_name = name_entry.get().strip()
            email = email_entry.get().strip()
            phone = phone_entry.get().strip()
            
            if not self._is_valid_email(email):
                messagebox.showwarning("Input", "Invalid email format.")
                return
            if not self._is_valid_phone(phone):
                messagebox.showwarning("Input", "Invalid phone number format.")
                return

            try:
                self.db.save_user_profile(self.current_user, full_name, email, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                messagebox.showinfo("Success", "Profile updated!")
                profile_win.destroy()
                # Refresh dashboard welcome message
                self.show_main_dashboard()
            except Exception as e:
                messagebox.showerror("Error", f"Could not update profile: {str(e)}")

        btn_frame = ctk.CTkFrame(profile_win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save", width=120, height=30, command=save_profile).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=120, height=30, command=profile_win.destroy).pack(side="left", padx=10)

    # --- IMPLEMENTED: OCR Scanner ---
    def open_scanner(self):
        # Check if Tesseract is installed (optional, but good practice)
        is_installed, error_msg = check_tesseract_installed()
        if not is_installed:
            # We won't block, but we'll warn the user
            if messagebox.askyesno("Tesseract Missing", f"{error_msg}\n\nDo you want to open the download page?"):
                open_tesseract_installer()
            return

        file_path = filedialog.askopenfilename(
            title="Select Receipt/Invoice Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff")]
        )

        if not file_path:
            return

        try:
            # Load image
            img = cv2.imread(file_path)
            if img is None:
                messagebox.showerror("Error", "Could not load image file.")
                return

            # Preprocessing (optional but recommended)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

            # Extract text
            text = pytesseract.image_to_string(gray)

            # Show result
            result_win = ctk.CTkToplevel(self)
            result_win.title("OCR Results")
            result_win.geometry("500x800")
            self.bring_dialog_to_front(result_win)

            ctk.CTkLabel(result_win, text="Extracted Text", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
            
            text_box = ctk.CTkTextbox(result_win, width=460, height=300)
            text_box.pack(padx=10, pady=5)
            text_box.insert("0.0", text)
            text_box.configure(state="disabled") # Read-only

            ctk.CTkButton(result_win, text="Copy to Clipboard", command=lambda: self.copy_to_clipboard(text)).pack(pady=5)
            ctk.CTkButton(result_win, text="Close", command=result_win.destroy).pack(pady=5)

        except Exception as e:
            messagebox.showerror("OCR Error", f"Failed to process image: {str(e)}")

    def copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Text copied to clipboard!")

    def on_close(self):
        self.db.close()
        self.quit()

if __name__ == "__main__":    
    app = VendorApp()
    app.mainloop()