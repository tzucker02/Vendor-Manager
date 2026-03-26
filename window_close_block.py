def safe_close_window(win):
 try:
 current = win.grab_current()
 if current is not None:
 current.grab_release()
 except Exception:
 pass
 try:
 win.withdraw()
 except Exception:
 pass
 try:
 win.destroy()
 except Exception:
 pass


class VendorApp(ctk.CTk):
 def init(self):
 super().init()
 self.protocol("WM_DELETE_WINDOW", self.on_close)

 def bring_dialog_to_front(self, dialog):
 try:
 dialog.transient(self)
 dialog.update_idletasks()
 dialog.deiconify()
 dialog.lift()
 dialog.attributes("-topmost", True)
 dialog.focus_force()
 dialog.grab_set()
 dialog.after(200, lambda: dialog.attributes("-topmost", False))
 except Exception:
 dialog.lift()
 dialog.focus_force()

 def on_close(self):
 try:
 if hasattr(self, "db") and self.db:
 self.db.close()
 except Exception:
 pass
 safe_close_window(self)

 def open_any_dialog(self):
 dialog = ctk.CTkToplevel(self)
 self.bring_dialog_to_front(dialog)

 def save():
 # your save logic here
 safe_close_window(dialog)

 def cancel():
 safe_close_window(dialog)

 ctk.CTkButton(dialog, text="Save", command=save).pack(pady=8)
 ctk.CTkButton(dialog, text="Cancel", command=cancel).pack(pady=8)
