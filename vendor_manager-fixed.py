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
        self.migrate_database()  # Add missing columns if they don't exist
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

        # --- Bills Table (NEW) ---
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

    def migrate_database(self):
        """Add missing columns to existing tables if they don't exist."""
        try:
            # Check if 'category' column exists in bills table
            self.cursor.execute("PRAGMA table_info(bills)")
            columns = [col[1] for col in self.cursor.fetchall()]
            
            if 'category' not in columns:
                print("Adding 'category' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN category TEXT DEFAULT 'Other'")
            
            if 'paid_date' not in columns:
                print("Adding 'paid_date' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN paid_date TEXT")
            
            if 'frequency' not in columns:
                print("Adding 'frequency' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN frequency TEXT DEFAULT 'Infrequent'")
            
            if 'is_recurring' not in columns:
                print("Adding 'is_recurring' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN is_recurring BOOLEAN DEFAULT 0")
            
            if 'receipt_path' not in columns:
                print("Adding 'receipt_path' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN receipt_path TEXT")
            
            if 'status' not in columns:
                print("Adding 'status' column to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN status TEXT DEFAULT 'Pending'")
            
            if 'custom_field_1' not in columns:
                print("Adding custom fields to bills table...")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN custom_field_1 TEXT")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN custom_field_2 TEXT")
                self.cursor.execute("ALTER TABLE bills ADD COLUMN custom_field_3 TEXT")
            
            self.conn.commit()
            print("Database migration complete.")
        except Exception as e:
            print(f"Migration warning (may already be migrated): {e}")

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

        self.cursor.execute("SELECT id FROM payment_methods WHERE method_name=?", (method_name,))
        method_row = self.cursor.fetchone()
        method_id = method_row[0] if method_row else None

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
        add_payment
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

    # --- Bill Management Methods ---
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
        if paid_amount is not None:
            new_status = "Paid" if is_paid and paid_amount >= self.get_bill_amount(bill_id) else "Pending"
            self.cursor.execute("UPDATE bills SET is_paid=?, paid_amount=?, status=? WHERE id=?",
                                (1 if is_paid else 0, paid_amount, new_status, bill_id))
        else:
            self.cursor.execute("SELECT amount FROM bills WHERE id=?", (bill_id,))
            row = self.cursor.fetchone()
            if row:
                amount = row[0]
                new_paid = amount if is_paid else 0
                new_status = "Paid" if is_paid else "Pending"
                self.cursor.execute("UPDATE bills SET is_paid=?, paid_amount=?, status=?, paid_date=? WHERE id=?",
                                    (1 if is_paid else 0, new_paid, new_status, datetime.now().strftime("%Y-%m-%d") if is_paid else None, bill_id))
        self.conn.commit()

    def get_bill_amount(self, bill_id):
        self.cursor.execute("SELECT amount FROM bills WHERE id=?", (bill_id,))
        row = self.cursor.fetchone()
        return row[0] if row else 0

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
        self.manage_bills_dialog = None  # Track the bills dialog to prevent duplicates
        self.show_login_screen()
        self.on_close_callbacks = []

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

    def open_manage_bills(self):
        # Prevent duplicate windows
        if self.manage_bills_dialog and self.manage_bills_dialog.winfo_exists():
            self.manage_bills_dialog.lift()
            self.manage_bills_dialog.focus_force()
            return
        
        self.manage_bills_dialog = ctk.CTkToplevel(self)
        self.manage_bills_dialog.title("Manage Bills")
        self.manage_bills_dialog.geometry("900x600")
        self.bring_dialog_to_front(self.manage_bills_dialog)
        
        # Close callback to reset the reference
        self.manage_bills_dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_manage_bills())

        header_frame = ctk.CTkFrame(self.manage_bills_dialog, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(header_frame, text="Bill Management", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkButton(header_frame, text="+ Add New Bill", width=120, height=30, command=self.open_add_bill_dialog).pack(side="right")

        scroll_frame = ctk.CTkScrollableFrame(self.manage_bills_dialog, width=860, height=450)
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

        btn_frame = ctk.CTkFrame(self.manage_bills_dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=self._close_manage_bills).pack(pady=5)

    def _close_manage_bills(self):
        """Properly close the manage bills dialog."""
        if self.manage_bills_dialog and self.manage_bills_dialog.winfo_exists():
            self.manage_bills_dialog.destroy()
        self.manage_bills_dialog = None

    def open_add_bill_dialog(self):
        add_win = ctk.CTkToplevel(self.manage_bills_dialog if self.manage_bills_dialog else self)
        add_win.title("Add New Bill")
        add_win.geometry("400x850")
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
        ctk.CTkLabel(add_win, text="Additional Notes", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        notes_entry = ctk.CTkTextbox(add_win, height=80, width=300)
        notes_entry.pack(pady=2)
        def save_new_bill():
            vendor_name = vendor_var.get()
            if vendor_name == "--- Create New Vendor ---":
                vendor_name = new_v_name.get().strip()
                if not vendor_name:
                    messagebox.showwarning("Input Error", "Please enter a name for the new vendor.")
                    return
                address = new_v_addr.get().strip()
                phone = new_v_phone.get().strip()
                cycle_name = "Monthly"
                method_name = None
                try:
                    vendor_id = self.db.add_vendor(vendor_name, address, phone, "", cycle_name, method_name)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create vendor: {e}")
                    return
            else:
                vendor_id = self.db.get_vendor_by_name(vendor_name)
                if not vendor_id:
                    messagebox.showerror("Error", "Selected vendor not found.")
                    return

            description = desc_entry.get().strip()
            category = cat_combo.get()
            amount_str = amt_entry.get().strip()
            due_date_str = due_entry.get().strip()
            frequency = freq_combo.get()
            custom1 = c1_entry.get().strip()
            custom2 = c2_entry.get().strip()
            custom3 = c3_entry.get().strip()
            notes = notes_entry.get("1.0", "end").strip()

            if not description or not amount_str or not due_date_str:
                messagebox.showwarning("Input Error", "Please fill in all required fields (Description, Amount, Due Date).")
                return
            
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Input Error", "Please enter a valid positive number for Amount.")
                return
            
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("Input Error", "Please enter Due Date in YYYY-MM-DD format.")
                return
            
            try:
                self.db.create_bill(vendor_id, description, category, amount, due_date_str, frequency, "Pending", custom1, custom2, custom3, notes)
                messagebox.showinfo("Success", "Bill created successfully!")
                add_win.destroy()
                self.open_manage_bills()  # Refresh the bills list
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create bill: {e}")    
        ctk.CTkButton(add_win, text="Save Bill", width=120, height=30, command=save_new_bill).pack(pady=20) 
    def toggle_bill_status(self, bill_id, is_paid):
        try:
            self.db.update_bill_status(bill_id, is_paid)
            self.open_manage_bills()  # Refresh the bills list
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update bill status: {e}")
    def edit_bill(self, bill_id):
        bill = None
        bills = self.db.get_all_bills()
        for b in bills:
            if b[0] == bill_id:
                bill = b
                break
        if not bill:
            messagebox.showerror("Error", "Bill not found.")
            return
        
        bid, vendor, desc, cat, amount, paid_amt, due_str, paid_date, freq, status, c1, c2, c3, notes = bill
        
        edit_win = ctk.CTkToplevel(self.manage_bills_dialog if self.manage_bills_dialog else self)
        edit_win.title("Edit Bill")
        edit_win.geometry("400x850")
        self.bring_dialog_to_front(edit_win)

        ctk.CTkLabel(edit_win, text="Edit Bill Details", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(edit_win, text="Vendor", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        vendors = self.db.get_all_vendors()
        vendor_names = [v[0] for v in vendors]
        vendor_var = ctk.StringVar(value=vendor)
        vendor_combo = ctk.CTkComboBox(edit_win, values=vendor_names, variable=vendor_var, height=28, width=300)
        vendor_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Description", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        desc_entry = ctk.CTkEntry(edit_win, height=28, width=300)
        desc_entry.insert(0, desc)
        desc_entry.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Category", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        categories = self.db.get_categories()
        cat_combo = ctk.CTkComboBox(edit_win, values=categories, height=28, width=300)
        cat_combo.set(cat if cat in categories else categories[0])
        cat_combo.pack(pady=2)

        ctk.CTkLabel(edit_win, text="Amount ($)", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        amt_entry = ctk.CTkEntry(edit_win, height=28, width=300)
        amt_entry.insert(0, f"{amount:.2f}")
        amt_entry.pack(pady=2)
        ctk.CTkLabel(edit_win, text="Due Date", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        due_entry = ctk.CTkEntry(edit_win, height=28, width=300)
        due_entry.insert(0, due_str)
        due_entry.pack(pady=2)
        ctk.CTkLabel(edit_win, text="Frequency", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        freq_combo = ctk.CTkComboBox(edit_win, values=self.db.get_frequency_options(), height=28, width=300)
        freq_combo.set(freq if freq in self.db.get_frequency_options() else self.db.get_frequency_options()[0])
        freq_combo.pack(pady=2)
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
        ctk.CTkLabel(edit_win, text="Additional Notes", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        notes_entry = ctk.CTkTextbox(edit_win, height=80, width=300)
        notes_entry.insert("1.0", notes)
        notes_entry.pack(pady=2)
        def save_edited_bill():
            vendor_name = vendor_var.get()
            vendor_id = self.db.get_vendor_by_name(vendor_name)
            if not vendor_id:
                messagebox.showerror("Error", "Selected vendor not found.")
                return

            description = desc_entry.get().strip()
            category = cat_combo.get()
            amount_str = amt_entry.get().strip()
            due_date_str = due_entry.get().strip()
            frequency = freq_combo.get()
            custom1 = c1_entry.get().strip()
            custom2 = c2_entry.get().strip()
            custom3 = c3_entry.get().strip()
            notes = notes_entry.get("1.0", "end").strip()

            if not description or not amount_str or not due_date_str:
                messagebox.showwarning("Input Error", "Please fill in all required fields (Description, Amount, Due Date).")
                return
            
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Input Error", "Please enter a valid positive number for Amount.")
                return
            
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("Input Error", "Please enter Due Date in YYYY-MM-DD format.")
                return
            
            try:
                # Update the bill by deleting the old one and creating a new one with the same ID
                self.db.cursor.execute("""
                    UPDATE bills SET vendor_id=?, description=?, category=?, amount=?, due_date=?, frequency=?, custom_field_1=?, custom_field_2=?, custom_field_3=?, notes=?
                    WHERE id=?
                """, (vendor_id, description, category, amount, due_date_str, frequency, custom1, custom2, custom3, notes, bill_id))
                self.db.conn.commit()
                messagebox.showinfo("Success", "Bill updated successfully!")
                edit_win.destroy()
                self.open_manage_bills()  # Refresh the bills list
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update bill: {e}")
        ctk.CTkButton(edit_win, text="Save Changes", width=120, height=30, command=save_edited_bill).pack(pady=20)
    def delete_bill(self, bill_id):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this bill? This action cannot be undone."):
            try:
                self.db.cursor.execute("DELETE FROM bills WHERE id=?", (bill_id,))
                self.db.conn.commit()
                messagebox.showinfo("Deleted", "Bill deleted successfully.")
                self.open_manage_bills()  # Refresh the bills list
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete bill: {e}")
    def open_add_payment(self):
        add_win = ctk.CTkToplevel(self)
        add_win.title("Add Payment")
        add_win.geometry("400x400")
        self.bring_dialog_to_front(add_win)

        ctk.CTkLabel(add_win, text="Record a Payment", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(add_win, text="Vendor", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        vendors = self.db.get_all_vendors()
        vendor_names = [v[0] for v in vendors]
        vendor_var = ctk.StringVar(value=vendor_names[0] if vendor_names else "")
        vendor_combo = ctk.CTkComboBox(add_win, values=vendor_names, variable=vendor_var, height=28, width=300)
        vendor_combo.pack(pady=2)

        ctk.CTkLabel(add_win, text="Amount Paid ($)", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        amt_entry = ctk.CTkEntry(add_win, height=28, width=300)
        amt_entry.pack(pady=2)

        ctk.CTkLabel(add_win, text="Payment Method", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        methods = self.db.get_payment_method_names()
        methods = [self.db.get_payment_method_id_by_name(name) for name in methods]
        method_var = ctk.StringVar(value=methods[0] if methods else "")
        method_combo = ctk.CTkComboBox(add_win, values=methods, variable=method_var, height=28, width=300)
        method_combo.pack(pady=2)

        def save_payment():
            vendor_name = vendor_var.get()
            amount_str = amt_entry.get().strip()
            method_name = method_var.get()

            if not vendor_name or not amount_str:
                messagebox.showwarning("Input Error", "Please fill in all required fields (Vendor and Amount).")
                return
            
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Input Error", "Please enter a valid positive number for Amount.")
                return
            
            try:
                vendor_id = self.db.get_vendor_by_name(vendor_name)
                if not vendor_id:
                    messagebox.showerror("Error", "Selected vendor not found.")
                    return
                method_id = self.db.get_payment_method_id_by_name(method_name)
                if not method_id:
                    messagebox.showerror("Error", "Selected payment method not found.")
                    return
                self.db.add_payment(vendor_id, amount, method_id)
                messagebox.showinfo("Success", "Payment recorded successfully!")
                add_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to record payment: {e}")
        ctk.CTkButton(add_win, text="Save Payment", width=120, height=30, command=save_payment).pack(pady=20)
    def open_profile(self):
        profile_win = ctk.CTkToplevel(self)
        profile_win.title("User Profile")
        profile_win.geometry("400x400")
        self.bring_dialog_to_front(profile_win)

        ctk.CTkLabel(profile_win, text="Your Profile", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        profile = self.db.get_user_profile(self.current_user) or {}
        full_name = profile.get("full_name", "")
        email = profile.get("email", "")
        phone = profile.get("phone", "")

        ctk.CTkLabel(profile_win, text="Full Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        name_entry.insert(0, full_name)
        name_entry.pack(pady=2)

        ctk.CTkLabel(profile_win, text="Email", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        email_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        email_entry.insert(0, email)
        email_entry.pack(pady=2)

        ctk.CTkLabel(profile_win, text="Phone", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        phone_entry = ctk.CTkEntry(profile_win, height=28, width=300)
        phone_entry.insert(0, phone)
        phone_entry.pack(pady=2)

        def save_profile():
            new_name = name_entry.get().strip()
            new_email = email_entry.get().strip()
            new_phone = phone_entry.get().strip()

            if new_email and not self._is_valid_email(new_email):
                messagebox.showwarning("Input Error", "Please enter a valid email address.")
                return
            
            if new_phone and not self._is_valid_phone(new_phone):
                messagebox.showwarning("Input Error", "Please enter a valid phone number.")
                return
            
            try:
                self.db.update_user_profile(self.current_user, new_name, new_email, new_phone)
                messagebox.showinfo("Success", "Profile updated successfully!")
                profile_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update profile: {e}")
        ctk.CTkButton(profile_win, text="Save Profile", width=120, height=30, command=save_profile).pack(pady=20)
if __name__ == "__main__":
    tesseract_ok, tesseract_msg = check_tesseract_installed()
    if not tesseract_ok:
        if messagebox.askyesno("Tesseract Not Found", f"{tesseract_msg}\n\nWould you like to download it now?"):
            open_tesseract_installer()
        else:
             messagebox.showwarning("Warning", "OCR scanning will be unavailable without Tesseract.")
    app=VendorApp()
    app.mainloop()
    


