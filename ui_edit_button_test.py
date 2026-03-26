import customtkinter as ctk
import vendor_manager as vm


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def main():
    app = None
    result = {"ok": False, "reason": None}
    try:
        app = vm.VendorApp()
        app.update_idletasks()
        app.update()

        bills = app.db.get_all_bills()
        if not bills:
            result["reason"] = "no bills"
            print(result)
            return

        app.edit_bill(bills[0][0])
        app.update_idletasks()
        app.update()

        for w in walk(app):
            try:
                if isinstance(w, ctk.CTkButton) and w.cget("text") == "Save Changes":
                    result["ok"] = True
                    break
            except Exception:
                pass

        if not result["ok"]:
            result["reason"] = "Save Changes button not found"

    except Exception as e:
        result["reason"] = str(e)
    finally:
        try:
            if app is not None:
                app.destroy()
        except Exception:
            pass

    print(result)


if __name__ == "__main__":
    main()
