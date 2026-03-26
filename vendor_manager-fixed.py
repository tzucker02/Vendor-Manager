import customtkinter as ctk
import sqlite3
import bcrypt
import os
from tkinter import filedialog, messagebox
import cv2
import pytesseract
import re
from datetime import datetime, timedelta

# --- Configuration ---
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor_db.sqlite")
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.seed_sample_data()

    def create_tables(self):
        # Users Table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )

        # Profiles Table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                last_updated TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # Billing Cycles
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS billing_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """
        )
        # Seed default cycles if empty
        self.cursor.execute("SELECT count(*) FROM billing_cycles")
        if self.cursor.fetchone()[0] == 0:
            cycles = ["Monthly", "Semi-Annually", "Annually", "As Needed", "Other"]
            for c in cycles:
                self.cursor.execute("INSERT INTO billing_cycles (name) VALUES (?)", (c,))

        # Payment Methods
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method_name TEXT NOT NULL,
                account_last_four TEXT,
                is_default BOOLEAN DEFAULT 0
            )
            """
        )

        # Vendors
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                account_number TEXT,
                billing_cycle_id INTEGER,
                payment_method_id INTEGER,
                notes TEXT,
                last_scan_data TEXT,
                FOREIGN KEY(billing_cycle_id) REFERENCES billing_cycles(id),
                FOREIGN KEY(payment_method_id) REFERENCES payment_methods(id)
            )
            """
        )

        # NEW: Bills Table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id INTEGER NOT NULL,
                description TEXT,
                amount REAL NOT NULL,
                paid_amount REAL DEFAULT 0,
                due_date TEXT NOT NULL,
                is_paid BOOLEAN DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(vendor_id) REFERENCES vendors(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.commit()

    def seed_sample_data(self):
        """Creates sample data if the DB is empty to demonstrate the Pay Bills feature."""
        self.cursor.execute("SELECT count(*) FROM vendors")
        if self.cursor.fetchone()[0] == 0:
            # Add a sample vendor
            self.cursor.execute("SELECT id FROM billing_cycles WHERE name='Monthly'")
            cycle_id = self.cursor.fetchone()[0]
            
            self.cursor.execute(
                "INSERT INTO vendors (name, address, phone, account_number, billing_cycle_id) VALUES (?, ?, ?, ?, ?)",
                ("Sample Vendor Inc.", "123 Business Rd", "555-0199", "ACC-001", cycle_id)
            )
            vendor_id = self.cursor.lastrowid
            
            today = datetime.now()
            # Create 3 sample bills: one overdue, one due soon, one future
            bills = [
                (vendor_id, "Office Supplies", 150.00, 0.00, (today - timedelta(days=5)).strftime("%Y-%m-%d")), # Overdue
                (vendor_id, "Software License", 299.99, 100.00, (today + timedelta(days=3)).strftime("%Y-%m-%d")), # Partially paid, due soon
                (vendor_id, "Consulting Fee", 500.00, 0.00, (today + timedelta(days=30)).strftime("%Y-%m-%d")) # Future
            ]
            
            for b in bills:
                self.cursor.execute(
                    "INSERT INTO bills (vendor_id, description, amount, paid_amount, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (b[0], b[1], b[2], b[3], b[4], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            self.conn.commit()

    def register_user(self, username, password):
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            self.cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hashed),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def login_user(self, username, password):
        self.cursor.execute("SELECT password_hash FROM users WHERE username=?", (username,))
        result = self.cursor.fetchone()
        if result:
            stored_hash = result[0]
            if isinstance(stored_hash, str):
                stored_hash = stored_hash.encode("utf-8")
            if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
                return True
        return False

    def close(self):
        self.conn.close()

    def add_vendor(self, name, address, phone, account, cycle_name, method_name, notes=""):
        self.cursor.execute("SELECT id FROM billing_cycles WHERE name=?", (cycle_name,))
        cycle_row = self.cursor.fetchone()
        if not cycle_row:
            raise ValueError("Please select a valid billing cycle.")
        cycle_id = cycle_row[0]

        self.cursor.execute("SELECT id FROM payment_methods WHERE method_name=?", (method_name,))
        method_row = self.cursor.fetchone()
        method_id = method_row[0] if method_row else None

        self.cursor.execute(
            """
            INSERT INTO vendors (name, address, phone, account_number, billing_cycle_id, payment_method_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, address, phone, account, cycle_id, method_id, notes),
        )
        self.conn.commit()

    def get_billing_cycle_names(self):
        self.cursor.execute("SELECT name FROM billing_cycles ORDER BY id")
        return [row[0] for row in self.cursor.fetchall()]

    def get_payment_method_names(self):
        self.cursor.execute("SELECT method_name FROM payment_methods ORDER BY id")
        return [row[0] for row in self.cursor.fetchall()]

    def add_payment_method(self, method_name, account_last_four):
        self.cursor.execute(
            "INSERT INTO payment_methods (method_name, account_last_four) VALUES (?, ?)",
            (method_name, account_last_four),
        )
        self.conn.commit()

    def get_all_vendors(self):
        self.cursor.execute(
            """
            SELECT v.name, v.address, v.phone, v.account_number, bc.name, pm.method_name
            FROM vendors v
            JOIN billing_cycles bc ON v.billing_cycle_id = bc.id
            LEFT JOIN payment_methods pm ON v.payment_method_id = pm.id
            """
        )
        return self.cursor.fetchall()

    def get_user_profile(self, username):
        self.cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        row = self.cursor.fetchone()
        if not row:
            return None

        user_id = row[0]
        self.cursor.execute(
            "SELECT full_name, email, phone, last_updated FROM user_profiles WHERE user_id=?",
            (user_id,),
        )
        profile = self.cursor.fetchone()
        if not profile:
            return {"full_name": "", "email": "", "phone": "", "last_updated": ""}

        return {
            "full_name": profile[0] or "",
            "email": profile[1] or "",
            "phone": profile[2] or "",
            "last_updated": profile[3] or "",
        }

    def save_user_profile(self, username, full_name, email, phone, last_updated):
        self.cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        row = self.cursor.fetchone()
        if not row:
            raise ValueError("User not found.")

        user_id = row[0]
        self.cursor.execute(
            """
            INSERT INTO user_profiles (user_id, full_name, email, phone, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                email=excluded.email,
                phone=excluded.phone,
                last_updated=excluded.last_updated
            """,
            (user_id, full_name, email, phone, last_updated),
        )
        self.conn.commit()

    # --- New Bill Methods ---
    def get_all_bills(self):
        """Returns all bills joined with vendor names."""
        self.cursor.execute(
            """
            SELECT b.id, v.name as vendor_name, b.description, b.amount, b.paid_amount, b.due_date, b.is_paid
            FROM bills b
            JOIN vendors v ON b.vendor_id = v.id
            ORDER BY b.due_date ASC
            """
        )
        return self.cursor.fetchall()

    def update_bill_status(self, bill_id, is_paid, paid_amount=None):
        """Updates the paid status and optionally the paid amount."""
        if paid_amount is not None:
            self.cursor.execute(
                "UPDATE bills SET is_paid=?, paid_amount=? WHERE id=?",
                (1 if is_paid else 0, paid_amount, bill_id)
            )
        else:
            # If just toggling status, set paid_amount to 0 if unpaid, or full amount if paid
            self.cursor.execute("SELECT amount FROM bills WHERE id=?", (bill_id,))
            row = self.cursor.fetchone()
            if row:
                amount = row[0]
                new_paid = amount if is_paid else 0
                self.cursor.execute(
                    "UPDATE bills SET is_paid=?, paid_amount=? WHERE id=?",
                    (1 if is_paid else 0, new_paid, bill_id)
                )
        self.conn.commit()


# --- Application UI ---
class VendorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_user = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.title("Vendor Management System")
        self.geometry("800x600")

        self.show_login_screen()

    def _is_valid_email(self, email):
        if not email:
            return True
        return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None

    def _is_valid_phone(self, phone):
        if not phone:
            return True
        cleaned = re.sub(r"[^\d]", "", phone)
        return len(cleaned) >= 7

    def bring_dialog_to_front(self, dialog):
        """Helper method to ensure a dialog window comes to the front and gains focus."""
        try:
            dialog.attributes('-topmost', True)
            dialog.lift()
            dialog.focus_force()
            dialog.attributes('-topmost', False)
        except Exception:
            dialog.lift()
            dialog.focus_force()

    def open_profile(self):
        profile = self.db.get_user_profile(self.current_user) or {
            "full_name": "", "email": "", "phone": "", "last_updated": "",
        }

        dialog = ctk.CTkToplevel(self)
        dialog.title("My Profile")
        dialog.geometry("380x320")
        self.bring_dialog_to_front(dialog)
        
        ctk.CTkLabel(dialog, text="Full Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        full_name_entry = ctk.CTkEntry(dialog, width=300, height=28)
        full_name_entry.pack(pady=2)
        full_name_entry.insert(0, profile["full_name"])

        ctk.CTkLabel(dialog, text="Email", font=ctk.CTkFont(size=12)).pack(pady=(8, 2))
        email_entry = ctk.CTkEntry(dialog, width=300, height=28)
        email_entry.pack(pady=2)
        email_entry.insert(0, profile["email"])

        ctk.CTkLabel(dialog, text="Phone", font=ctk.CTkFont(size=12)).pack(pady=(8, 2))
        phone_entry = ctk.CTkEntry(dialog, width=300, height=28)
        phone_entry.pack(pady=2)
        phone_entry.insert(0, profile["phone"])

        last_updated_label = ctk.CTkLabel(
            dialog,
            text=f"Last Updated: {profile['last_updated'] or 'Never'}",
            font=ctk.CTkFont(size=11),
        )
        last_updated_label.pack(pady=8)

        def save_profile():
            full_name = full_name_entry.get().strip()
            email = email_entry.get().strip()
            phone = phone_entry.get().strip()

            if not self._is_valid_email(email):
                messagebox.showwarning("Validation", "Please enter a valid email.")
                return
            if not self._is_valid_phone(phone):
                messagebox.showwarning("Validation", "Please enter a valid phone number.")
                return

            last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.save_user_profile(self.current_user, full_name, email, phone, last_updated)
            last_updated_label.configure(text=f"Last Updated: {last_updated}")
            messagebox.showinfo("Success", "Profile saved.")
            dialog.destroy()
            
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Save", width=100, height=28, command=save_profile).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, height=28, command=dialog.destroy).pack(side="left", padx=10)

    def clear_frame(self):
        for widget in self.winfo_children():
            widget.destroy()

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

        # Buttons Grid - Added "Pay Bills"
        btn_grid = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_grid.pack(fill="x", pady=5)

        ctk.CTkButton(btn_grid, text="Add Vendor", command=self.open_add_vendor, width=140, height=32).grid(row=0, column=0, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="Add Payment", command=self.open_add_payment, width=140, height=32).grid(row=0, column=1, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="Scan OCR", command=self.open_scanner, width=140, height=32).grid(row=0, column=2, padx=8, pady=5)
        ctk.CTkButton(btn_grid, text="View Vendors", command=self.view_vendors, width=140, height=32).grid(row=0, column=3, padx=8, pady=5)
        
        # New Row for Pay Bills and Profile
        btn_grid2 = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_grid2.pack(fill="x", pady=5)
        ctk.CTkButton(btn_grid2, text="Pay Bills", command=self.open_pay_bills, width=140, height=32).grid(row=0, column=0, padx=8, pady=5)
        ctk.CTkButton(btn_grid2, text="Profile", command=self.open_profile, width=140, height=32).grid(row=0, column=1, padx=8, pady=5)

        self.vendor_list_label = ctk.CTkLabel(main_container, text="Recent Vendors:", font=ctk.CTkFont(size=13, weight="bold"))
        self.vendor_list_label.pack(anchor="w", pady=(10, 3))
        self.vendor_list_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        self.vendor_list_frame.pack(fill="x", pady=3)
        self.refresh_vendor_list()

    def refresh_vendor_list(self):
        if not hasattr(self, "vendor_list_frame"):
            return
        for widget in self.vendor_list_frame.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                widget.destroy()
        vendors = self.db.get_all_vendors()
        for v in vendors[-5:]:
            method = v[5] if v[5] else "No method set"
            lbl = ctk.CTkLabel(self.vendor_list_frame, text=f"{v[0]} | Cycle: {v[4]} | Method: {method}", anchor="w", font=ctk.CTkFont(size=11))
            lbl.pack(fill="x", pady=1)

    def open_add_vendor(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add New Vendor")
        dialog.geometry("360x420")
        self.bring_dialog_to_front(dialog)

        ctk.CTkLabel(dialog, text="Vendor Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name = ctk.CTkEntry(dialog, height=28)
        name.pack(pady=2)

        ctk.CTkLabel(dialog, text="Address", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        addr = ctk.CTkEntry(dialog, height=28)
        addr.pack(pady=2)

        ctk.CTkLabel(dialog, text="Phone", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        phone = ctk.CTkEntry(dialog, height=28)
        phone.pack(pady=2)

        ctk.CTkLabel(dialog, text="Account Number", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        acc = ctk.CTkEntry(dialog, height=28)
        acc.pack(pady=2)

        ctk.CTkLabel(dialog, text="Billing Cycle", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        cycle_values = self.db.get_billing_cycle_names()
        cycle = ctk.CTkComboBox(dialog, values=cycle_values, height=28)
        cycle.pack(pady=2)
        if cycle_values:
            cycle.set(cycle_values[0])

        ctk.CTkLabel(dialog, text="Payment Method", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        method_values = self.db.get_payment_method_names()
        if not method_values:
            method_values = ["No saved methods"]
        method = ctk.CTkComboBox(dialog, values=method_values, height=28)
        method.pack(pady=2)
        method.set(method_values[0])

        def save():
            try:
                vendor_name = name.get().strip()
                if not vendor_name:
                    messagebox.showwarning("Input", "Vendor name is required.")
                    return
                selected_method = method.get()
                if selected_method == "No saved methods":
                    selected_method = ""
                self.db.add_vendor(
                    vendor_name, addr.get().strip(), phone.get().strip(), acc.get().strip(),
                    cycle.get().strip(), selected_method,
                )
                messagebox.showinfo("Success", "Vendor Added!")
                dialog.destroy()
                self.refresh_vendor_list()
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Could not add vendor: {str(e)}")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=12)
        ctk.CTkButton(btn_frame, text="Save", width=100, height=28, command=save).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, height=28, command=dialog.destroy).pack(side="left", padx=10)

    def open_add_payment(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Payment Method")
        dialog.geometry("280x180")
        self.bring_dialog_to_front(dialog)

        ctk.CTkLabel(dialog, text="Method Name", font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
        name = ctk.CTkEntry(dialog, height=28)
        name.pack(pady=2)

        ctk.CTkLabel(dialog, text="Last 4 Digits", font=ctk.CTkFont(size=12)).pack(pady=(6, 2))
        digits = ctk.CTkEntry(dialog, height=28)
        digits.pack(pady=2)

        def save():
            method_name = name.get().strip()
            last_four = digits.get().strip()
            if not method_name:
                messagebox.showwarning("Input", "Payment method name is required.")
                return
            if last_four and (not last_four.isdigit() or len(last_four) != 4):
                messagebox.showwarning("Input", "Last 4 digits must be exactly 4 numbers.")
                return
            self.db.add_payment_method(method_name, last_four)
            messagebox.showinfo("Success", "Payment Method Added!")
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Save", width=100, height=28, command=save).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, height=28, command=dialog.destroy).pack(side="left", padx=10)

    def open_scanner(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp")])
        if file_path:
            try:
                img = cv2.imread(file_path)
                if img is None:
                    raise ValueError("Selected file could not be read as an image.")
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                text = pytesseract.image_to_string(gray)
                if not text.strip():
                    text = "[No text detected in image.]"

                result_window = ctk.CTkToplevel(self)
                result_window.title("Scan Results")
                result_window.geometry("480x350")
                self.bring_dialog_to_front(result_window)

                ctk.CTkLabel(result_window, text="Extracted Text:", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=8)
                text_box = ctk.CTkTextbox(result_window, wrap="word")
                text_box.pack(fill="both", expand=True, padx=15, pady=10)
                text_box.insert("0.0", text)

                btn_frame = ctk.CTkFrame(result_window, fg_color="transparent")
                btn_frame.pack(pady=8)
                ctk.CTkButton(btn_frame, text="Use as Vendor Input", width=140, height=28, 
                             command=lambda: self.populate_from_scan(text, result_window)).pack(side="left", padx=10)
                ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=result_window.destroy).pack(side="left", padx=10)

            except pytesseract.TesseractNotFoundError:
                messagebox.showerror("Error", "Tesseract OCR is not installed or not in PATH.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not scan image: {str(e)}")

    def populate_from_scan(self, text, window):
        messagebox.showinfo("Success", "Text extracted! In a full version, this would auto-fill the 'Add Vendor' form.")
        window.destroy()
        self.open_add_vendor()

    def open_pay_bills(self):
        """
        Opens a dialog to manage bills.
        Shows: Paid/Unpaid checkbox, Days until due, Total Paid, Total Outstanding.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Pay Bills")
        dialog.geometry("700x500")
        self.bring_dialog_to_front(dialog)

        # Header
        ctk.CTkLabel(dialog, text="Bill Management", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        
        # Scrollable frame for bills
        scroll_frame = ctk.CTkScrollableFrame(dialog, width=660, height=350)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        bills = self.db.get_all_bills()
        
        if not bills:
            ctk.CTkLabel(scroll_frame, text="No bills found.", font=ctk.CTkFont(size=12)).pack(pady=20)
        else:
            today = datetime.now()
            
            for bill in bills:
                # bill structure: (id, vendor_name, description, amount, paid_amount, due_date, is_paid)
                bid, vendor, desc, amount, paid_amt, due_str, is_paid = bill
                
                due_date = datetime.strptime(due_str, "%Y-%m-%d")
                days_diff = (due_date - today).days
                
                outstanding = amount - paid_amt
                
                # Color coding for days
                if days_diff < 0:
                    status_color = "#ff4d4d" # Red (Overdue)
                    days_text = f"{abs(days_diff)} days overdue"
                elif days_diff == 0:
                    status_color = "#ffa500" # Orange (Due Today)
                    days_text = "Due Today"
                else:
                    status_color = "#4dff4d" # Green (Future)
                    days_text = f"{days_diff} days left"

                # Create a row frame
                row_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=4)

                # Checkbox
                var = ctk.BooleanVar(value=bool(is_paid))
                chk = ctk.CTkCheckBox(row_frame, text="", variable=var, command=lambda b=bid, v=var: self.toggle_bill_status(b, v.get()))
                chk.pack(side="left", padx=(0, 10))

                # Details Frame
                details = ctk.CTkFrame(row_frame, fg_color="#2a2a2a", corner_radius=5)
                details.pack(side="left", fill="x", expand=True, padx=5)

                # Top line: Vendor & Desc
                info_label = ctk.CTkLabel(details, text=f"{vendor}: {desc}", font=ctk.CTkFont(size=12, weight="bold"))
                info_label.pack(anchor="w", padx=10, pady=(5, 0))

                # Bottom line: Stats
                stats_text = f"Due: {due_str} ({days_text}) | Paid: ${paid_amt:.2f} | Outstanding: ${outstanding:.2f}"
                stats_label = ctk.CTkLabel(details, text=stats_text, font=ctk.CTkFont(size=11), text_color=status_color)
                stats_label.pack(anchor="w", padx=10, pady=(2, 5))

        # Close button
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=dialog.destroy).pack(pady=5)

    def toggle_bill_status(self, bill_id, is_paid):
        """Callback for checkbox toggle."""
        self.db.update_bill_status(bill_id, is_paid)
        # Optional: Refresh the view if needed, but since we rebuild the list on open, 
        # the user just needs to reopen or we could reload the frame. 
        # For simplicity in this prototype, we rely on the user reopening or the DB update being immediate.
        # To make it instant, we could destroy and recreate the dialog, but that's jarring.
        # Instead, we'll just log or show a toast if desired.
        pass

    def view_vendors(self):
        vendors = self.db.get_all_vendors()
        list_window = ctk.CTkToplevel(self)
        list_window.title("All Vendors")
        list_window.geometry("550x380")
        self.bring_dialog_to_front(list_window)

        text_area = ctk.CTkTextbox(list_window, wrap="word")
        text_area.pack(fill="both", expand=True, padx=10, pady=10)

        if not vendors:
            text_area.insert("end", "No vendors found. Add a vendor from the dashboard.")
            return

        for v in vendors:
            method = v[5] if v[5] else "No method set"
            line = f"Name: {v[0]}\nAddress: {v[1]}\nPhone: {v[2]}\nAcct: {v[3]}\nCycle: {v[4]}\nMethod: {method}\n{'-'*30}\n"
            text_area.insert("end", line)

        btn_frame = ctk.CTkFrame(list_window, fg_color="transparent")
        btn_frame.pack(pady=5)
        ctk.CTkButton(btn_frame, text="Close", width=100, height=28, command=list_window.destroy).pack(pady=5)

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = VendorApp()
    app.mainloop()