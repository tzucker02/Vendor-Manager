import customtkinter as ctk
import sqlite3
import bcrypt
import os
from tkinter import filedialog, messagebox
import cv2
import pytesseract
import re
from datetime import datetime

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

        # Profiles Table (1 profile row per user)
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
        # Get IDs
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


# --- Application UI ---
class VendorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_user = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.title("Vendor Management System")
        self.geometry("900x700")

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

    def open_profile(self):
        profile = self.db.get_user_profile(self.current_user) or {
            "full_name": "",
            "email": "",
            "phone": "",
            "last_updated": "",
        }

        dialog = ctk.CTkToplevel(self)
        dialog.title("My Profile")
        dialog.geometry("420x360")
        
        ctk.CTkLabel(dialog, text="Full Name").pack(pady=5)
        full_name_entry = ctk.CTkEntry(dialog, width=320)
        full_name_entry.pack(pady=5)
        full_name_entry.insert(0, profile["full_name"])

        ctk.CTkLabel(dialog, text="Email").pack(pady=5)
        email_entry = ctk.CTkEntry(dialog, width=320)
        email_entry.pack(pady=5)
        email_entry.insert(0, profile["email"])

        ctk.CTkLabel(dialog, text="Phone").pack(pady=5)
        phone_entry = ctk.CTkEntry(dialog, width=320)
        phone_entry.pack(pady=5)
        phone_entry.insert(0, profile["phone"])

        last_updated_label = ctk.CTkLabel(
            dialog,
            text=f"Last Updated: {profile['last_updated'] or 'Never'}",
        )
        last_updated_label.pack(pady=10)

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
            dialog.destroy() # Close after saving to simplify flow. Remove this line if you want to keep the dialog open.
            
        ctk.CTkButton(dialog, text="Save Profile", command=save_profile).pack(pady=12)
        ctk.CTkButton(dialog, text="Cancel", command=dialog.destroy).pack(pady=6)
    def clear_frame(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_login_screen(self):
        self.clear_frame()
        frame = ctk.CTkFrame(self, corner_radius=10, width=400, height=300)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(frame, text="Vendor Manager Login", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        self.username_entry = ctk.CTkEntry(frame, placeholder_text="Username")
        self.username_entry.pack(pady=10)

        self.password_entry = ctk.CTkEntry(frame, placeholder_text="Password", show="*")
        self.password_entry.pack(pady=10)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(btn_frame, text="Login", command=self.login).grid(row=0, column=0, padx=10)
        ctk.CTkButton(btn_frame, text="Register", command=self.register).grid(row=0, column=1, padx=10)

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
            else:
                messagebox.showerror("Error", "Username already exists.")
        else:
            messagebox.showwarning("Input", "Please fill all fields.")

    def show_main_dashboard(self):
        self.clear_frame()

        # Header
        header = ctk.CTkFrame(self, height=60, fg_color="#2b2b2b")
        header.pack(fill="x")
        
        profile = self.db.get_user_profile(self.current_user) or {}
        display_name = profile.get("full_name", "").strip()
        first_name = display_name.split()[0] if display_name else self.current_user

        ctk.CTkLabel(
            header,
            text=f"Welcome, {first_name}",
            font=ctk.CTkFont(size=16)
        ).pack(side="left", padx=20)
        
        # ctk.CTkLabel(header, text=f"Welcome, {self.current_user}", font=ctk.CTkFont(size=16)).pack(side="left", padx=20)
        ctk.CTkButton(header, text="Logout", width=80, command=self.show_login_screen).pack(side="right", padx=20)

        # Main Layout
        main_container = ctk.CTkScrollableFrame(self)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Buttons Grid
        btn_grid = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_grid.pack(fill="x", pady=10)

        ctk.CTkButton(btn_grid, text="Add New Vendor", command=self.open_add_vendor, width=200, height=50).grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkButton(btn_grid, text="Add Payment Method", command=self.open_add_payment, width=200, height=50).grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkButton(btn_grid, text="Scan Object (OCR)", command=self.open_scanner, width=200, height=50).grid(row=0, column=2, padx=10, pady=10)
        ctk.CTkButton(btn_grid, text="View All Vendors", command=self.view_vendors, width=200, height=50).grid(row=0, column=3, padx=10, pady=10)
        ctk.CTkButton(btn_grid, text="My Profile", command=self.open_profile, width=200, height=50).grid(row=1, column=0, padx=10, pady=10)

        # Vendor List Preview
        self.vendor_list_label = ctk.CTkLabel(main_container, text="Recent Vendors:", font=ctk.CTkFont(size=14, weight="bold"))
        self.vendor_list_label.pack(anchor="w")
        self.vendor_list_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        self.vendor_list_frame.pack(fill="x", pady=5)
        self.refresh_vendor_list()

    def refresh_vendor_list(self):
        # Keep the preview list scoped to the dashboard list frame.
        if not hasattr(self, "vendor_list_frame"):
            return

        for widget in self.vendor_list_frame.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                widget.destroy()

        vendors = self.db.get_all_vendors()
        for v in vendors[-5:]:  # Show last 5
            method = v[5] if v[5] else "No method set"
            lbl = ctk.CTkLabel(self.vendor_list_frame, text=f"{v[0]} | Cycle: {v[4]} | Method: {method}", anchor="w")
            lbl.pack(fill="x", pady=2)

    def open_add_vendor(self):
        # Simplified dialog for prototype
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add New Vendor")
        dialog.geometry("400x500")

        ctk.CTkLabel(dialog, text="Vendor Name").pack(pady=5)
        name = ctk.CTkEntry(dialog)
        name.pack(pady=5)

        ctk.CTkLabel(dialog, text="Address").pack(pady=5)
        addr = ctk.CTkEntry(dialog)
        addr.pack(pady=5)

        ctk.CTkLabel(dialog, text="Phone").pack(pady=5)
        phone = ctk.CTkEntry(dialog)
        phone.pack(pady=5)

        ctk.CTkLabel(dialog, text="Account Number").pack(pady=5)
        acc = ctk.CTkEntry(dialog)
        acc.pack(pady=5)

        ctk.CTkLabel(dialog, text="Billing Cycle").pack(pady=5)
        cycle_values = self.db.get_billing_cycle_names()
        cycle = ctk.CTkComboBox(dialog, values=cycle_values)
        cycle.pack(pady=5)
        if cycle_values:
            cycle.set(cycle_values[0])

        ctk.CTkLabel(dialog, text="Payment Method").pack(pady=5)
        method_values = self.db.get_payment_method_names()
        if not method_values:
            method_values = ["No saved methods"]
        method = ctk.CTkComboBox(dialog, values=method_values)
        method.pack(pady=5)
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
                    vendor_name,
                    addr.get().strip(),
                    phone.get().strip(),
                    acc.get().strip(),
                    cycle.get().strip(),
                    selected_method,
                )
                messagebox.showinfo("Success", "Vendor Added!")
                dialog.destroy()
                self.refresh_vendor_list()
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Could not add vendor: {str(e)}")

        ctk.CTkButton(dialog, text="Save Vendor", command=save).pack(pady=20)

    def open_add_payment(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Payment Method")
        dialog.geometry("300x200")

        ctk.CTkLabel(dialog, text="Method Name (e.g., Visa ending 1234)").pack(pady=10)
        name = ctk.CTkEntry(dialog)
        name.pack(pady=5)

        ctk.CTkLabel(dialog, text="Last 4 Digits").pack(pady=5)
        digits = ctk.CTkEntry(dialog)
        digits.pack(pady=5)

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

        ctk.CTkButton(dialog, text="Save", command=save).pack(pady=10)

    def open_scanner(self):
        # Simulates scanning an image file
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp")])
        if file_path:
            try:
                # Load image
                img = cv2.imread(file_path)
                if img is None:
                    raise ValueError("Selected file could not be read as an image.")
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                # Perform OCR
                text = pytesseract.image_to_string(gray)
                if not text.strip():
                    text = "[No text detected in image.]"

                # Display result
                result_window = ctk.CTkToplevel(self)
                result_window.title("Scan Results")
                result_window.geometry("500x400")

                ctk.CTkLabel(result_window, text="Extracted Text:", font=ctk.CTkFont(weight="bold")).pack(pady=10)

                text_box = ctk.CTkTextbox(result_window, wrap="word")
                text_box.pack(fill="both", expand=True, padx=20, pady=10)
                text_box.insert("0.0", text)

                ctk.CTkButton(
                    result_window,
                    text="Use as Vendor Input",
                    command=lambda: self.populate_from_scan(text, result_window),
                ).pack(pady=10)

            except pytesseract.TesseractNotFoundError:
                messagebox.showerror(
                    "Error",
                    "Tesseract OCR is not installed or not in PATH. Install Tesseract to enable scanning.",
                )
            except Exception as e:
                messagebox.showerror("Error", f"Could not scan image: {str(e)}")

    def populate_from_scan(self, text, window):
        messagebox.showinfo("Success", "Text extracted! In a full version, this would auto-fill the 'Add Vendor' form.")
        window.destroy()
        self.open_add_vendor()

    def view_vendors(self):
        # Simple list view
        vendors = self.db.get_all_vendors()
        list_window = ctk.CTkToplevel(self)
        list_window.title("All Vendors")
        list_window.geometry("600x400")

        text_area = ctk.CTkTextbox(list_window, wrap="word")
        text_area.pack(fill="both", expand=True, padx=10, pady=10)

        if not vendors:
            text_area.insert("end", "No vendors found. Add a vendor from the dashboard.")
            return

        for v in vendors:
            method = v[5] if v[5] else "No method set"
            line = f"Name: {v[0]}\nAddress: {v[1]}\nPhone: {v[2]}\nAcct: {v[3]}\nCycle: {v[4]}\nMethod: {method}\n{'-'*30}\n"
            text_area.insert("end", line)

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = VendorApp()
    app.mainloop()