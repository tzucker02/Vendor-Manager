import traceback
import customtkinter as ctk
import vendor_manager as vm


def main():
    result = {
        "app_started": False,
        "opened_manage_bills": False,
        "tested_toggle": False,
        "single_manage_window": None,
        "bill_count": None,
        "error": None,
    }

    app = None
    try:
        app = vm.VendorApp()
        app.update_idletasks()
        app.update()
        result["app_started"] = True

        app.open_manage_bills()
        app.update_idletasks()
        app.update()
        result["opened_manage_bills"] = True

        bills = app.db.get_all_bills()
        result["bill_count"] = len(bills)

        if bills:
            bill_id = bills[0][0]
            currently_paid = bills[0][9] == "Paid"

            app.toggle_bill_status(bill_id, not currently_paid)
            app.update_idletasks()
            app.update()

            app.toggle_bill_status(bill_id, currently_paid)
            app.update_idletasks()
            app.update()

            result["tested_toggle"] = True

        toplevels = [
            w for w in app.winfo_children()
            if isinstance(w, ctk.CTkToplevel) and w.winfo_exists()
        ]
        result["single_manage_window"] = len(toplevels) <= 1

    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        try:
            if app is not None:
                for w in app.winfo_children():
                    try:
                        if isinstance(w, ctk.CTkToplevel) and w.winfo_exists():
                            w.destroy()
                    except Exception:
                        pass
                app.destroy()
        except Exception:
            pass

    print(result)


if __name__ == "__main__":
    main()
