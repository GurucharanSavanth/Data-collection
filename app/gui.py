from __future__ import annotations

import logging
import os
import re
from pathlib import Path
import tkinter as tk
from tkinter import END, LEFT, RIGHT, VERTICAL, W, messagebox, ttk
from typing import Any

from csv_manager import CSVManager
from session_manager import SessionManager
from utils import current_timestamp


class RecordManagerApp:
    def __init__(
        self,
        root: tk.Tk,
        settings: dict[str, Any],
        csv_manager: CSVManager,
        session_manager: SessionManager,
        logger: logging.Logger,
        csv_path: Path,
    ) -> None:
        self.root = root
        self.settings = settings
        self.csv_manager = csv_manager
        self.session_manager = session_manager
        self.logger = logger
        self.csv_path = csv_path

        self.status_values = settings.get("status_values", ["Open", "Close"])
        self.mode = "idle"
        self.current_record_id = ""
        self.records: list[dict[str, str]] = []
        self.filtered_records: list[dict[str, str]] = []
        self.pending_state_save_job: str | None = None

        self.app_state = self.session_manager.mark_startup()
        self.session_state = self.session_manager.load_session_state()
        self.session_state["last_opened_at"] = current_timestamp()

        self.root.title(settings.get("window_title", "Record Manager Dashboard"))
        self.root.geometry(self.session_state.get("window_geometry") or settings.get("default_window_size", "1280x800"))
        if self.session_state.get("window_state") in {"normal", "zoomed"}:
            self.root.state(self.session_state["window_state"])
        self.root.minsize(1080, 680)

        saved_form = self.session_state.get("form_values", {})
        short_note_value = saved_form.get("short_note", saved_form.get("notes", ""))

        self.search_var = tk.StringVar(value=self.session_state.get("search_text", ""))
        self.title_var = tk.StringVar(value=saved_form.get("title", ""))
        self.category_var = tk.StringVar(value=saved_form.get("category", ""))
        self.name_var = tk.StringVar(value=saved_form.get("name", ""))
        self.phone_var = tk.StringVar(value=saved_form.get("phone_number", ""))
        self.status_var = tk.StringVar(value=saved_form.get("status", self.status_values[0]))
        self.mode_var = tk.StringVar(value="Mode: idle")
        self.record_id_var = tk.StringVar(value="Selected Record ID: none")
        self.created_at_var = tk.StringVar(value="-")
        self.updated_at_var = tk.StringVar(value="-")
        self.status_message_var = tk.StringVar(value="Ready.")

        self._build_layout()
        self._bind_events()
        self.refresh_records(initial_restore=True)
        self.apply_session_state(short_note_value)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        search_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Search / Filter").grid(row=0, column=0, sticky=W, padx=(0, 8))
        ttk.Entry(search_frame, textvariable=self.search_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(search_frame, text="Clear Search", command=self.clear_search).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(search_frame, text="Reload Data", command=self.refresh_records).grid(row=0, column=3, padx=(8, 0))

        table_frame = ttk.Frame(self.root, padding=(12, 6, 6, 6))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("record_id", "name", "phone_number", "status", "created_at", "updated_at", "short_note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "record_id": "Record ID",
            "name": "Name",
            "phone_number": "Phone Number",
            "status": "Status",
            "created_at": "Created At",
            "updated_at": "Updated At",
            "short_note": "Short Note / Description",
        }
        widths = {
            "record_id": 175,
            "name": 190,
            "phone_number": 150,
            "status": 100,
            "created_at": 145,
            "updated_at": 145,
            "short_note": 280,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=W, stretch=column == "short_note")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        form_frame = ttk.Frame(self.root, padding=(6, 6, 12, 6))
        form_frame.grid(row=1, column=1, sticky="nsew")
        form_frame.columnconfigure(1, weight=1)
        form_frame.rowconfigure(9, weight=1)

        ttk.Label(form_frame, text="Record Details", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 8))
        ttk.Label(form_frame, textvariable=self.record_id_var).grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 12))

        ttk.Label(form_frame, text="Title *").grid(row=2, column=0, sticky=W, padx=(0, 8), pady=4)
        self.title_combo = ttk.Combobox(form_frame, textvariable=self.title_var, state="normal")
        self.title_combo.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Category *").grid(row=3, column=0, sticky=W, padx=(0, 8), pady=4)
        self.category_combo = ttk.Combobox(form_frame, textvariable=self.category_var, state="normal")
        self.category_combo.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Name *").grid(row=4, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Entry(form_frame, textvariable=self.name_var).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Phone Number *").grid(row=5, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Entry(form_frame, textvariable=self.phone_var).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Status").grid(row=6, column=0, sticky=W, padx=(0, 8), pady=4)
        self.status_combo = ttk.Combobox(form_frame, textvariable=self.status_var, values=self.status_values, state="readonly")
        self.status_combo.grid(row=6, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Created At").grid(row=7, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Label(form_frame, textvariable=self.created_at_var).grid(row=7, column=1, sticky="w", pady=4)

        ttk.Label(form_frame, text="Updated At").grid(row=8, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Label(form_frame, textvariable=self.updated_at_var).grid(row=8, column=1, sticky="w", pady=4)

        ttk.Label(form_frame, text="Short Note / Description").grid(row=9, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.short_note_text = tk.Text(form_frame, height=10, wrap="word")
        self.short_note_text.grid(row=9, column=1, sticky="nsew", pady=4)

        button_frame = ttk.Frame(form_frame, padding=(0, 12, 0, 0))
        button_frame.grid(row=10, column=0, columnspan=2, sticky="ew")
        for index in range(3):
            button_frame.columnconfigure(index, weight=1)

        ttk.Button(button_frame, text="Prepare New", command=self.prepare_new_record).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(button_frame, text="Save Record", command=self.save_record).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_record).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(8, 0))
        ttk.Button(button_frame, text="Reset Filter", command=self.clear_search).grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(button_frame, text="Open Data Folder", command=self.open_data_folder).grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        footer = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)

        ttk.Label(footer, textvariable=self.mode_var).pack(side=LEFT)
        ttk.Label(footer, textvariable=self.status_message_var).pack(side=RIGHT)

        style = ttk.Style()
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))

    def _bind_events(self) -> None:
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_selection)
        self.search_var.trace_add("write", self.on_search_changed)
        self.title_var.trace_add("write", self.on_form_changed)
        self.category_var.trace_add("write", self.on_form_changed)
        self.name_var.trace_add("write", self.on_form_changed)
        self.phone_var.trace_add("write", self.on_form_changed)
        self.status_var.trace_add("write", self.on_form_changed)
        self.short_note_text.bind("<KeyRelease>", lambda _event: self.on_form_changed())

    def refresh_records(self, initial_restore: bool = False) -> None:
        try:
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.apply_filter()
            if not initial_restore:
                self.set_status(f"Loaded {len(self.records)} record(s) from CSV.")
        except Exception as exc:
            self.logger.exception("Failed to refresh records")
            self.set_status("Failed to load records. See the log file for details.", error=True)
            messagebox.showerror("Load Error", f"The application could not load the CSV file.\n\n{exc}")

    def _refresh_reference_values(self) -> None:
        self.title_combo["values"] = self.csv_manager.get_unique_values(self.records, "title")
        self.category_combo["values"] = self.csv_manager.get_unique_values(self.records, "category")

    def apply_filter(self) -> None:
        query = self.search_var.get()
        self.filtered_records = self.csv_manager.filter_records(self.records, query)
        selected_id = self.current_record_id or self.session_state.get("selected_record_id", "")
        self.populate_tree(selected_id)
        self.schedule_state_save()

    def populate_tree(self, selected_record_id: str = "") -> None:
        self.tree.delete(*self.tree.get_children())
        tree_item_to_select = ""
        for record in self.filtered_records:
            item_id = self.tree.insert(
                "",
                END,
                values=(
                    record.get("record_id", ""),
                    record.get("name", ""),
                    record.get("phone_number", ""),
                    record.get("status", ""),
                    record.get("created_at", ""),
                    record.get("updated_at", ""),
                    record.get("short_note", ""),
                ),
            )
            if record.get("record_id") == selected_record_id:
                tree_item_to_select = item_id

        if tree_item_to_select:
            self.tree.selection_set(tree_item_to_select)
            self.tree.focus(tree_item_to_select)
            self.tree.see(tree_item_to_select)

    def apply_session_state(self, short_note_value: str) -> None:
        self.mode = self.session_state.get("mode", "idle")
        self.set_mode(self.mode)
        self.short_note_text.delete("1.0", END)
        self.short_note_text.insert("1.0", short_note_value)

        selected_id = self.session_state.get("selected_record_id", "")
        if selected_id:
            record = self.csv_manager.find_record(self.records, selected_id)
            if record:
                self.current_record_id = selected_id
                self.load_record_into_form(record)
                self.populate_tree(selected_id)

        if self.app_state.get("unclean_previous_shutdown"):
            self.set_status(
                "The previous session did not shut down cleanly. Restored the last saved session state.",
                error=True,
            )
            messagebox.showwarning(
                "Recovered Previous Session",
                "The previous session appears to have closed unexpectedly.\n\n"
                "The application restored the last saved search and form state.",
            )
        else:
            self.set_status(f"Ready. {len(self.records)} record(s) available.")

    def load_record_into_form(self, record: dict[str, str]) -> None:
        self.current_record_id = record.get("record_id", "")
        self.record_id_var.set(f"Selected Record ID: {self.current_record_id}")
        self.title_var.set(record.get("title", ""))
        self.category_var.set(record.get("category", ""))
        self.name_var.set(record.get("name", ""))
        self.phone_var.set(record.get("phone_number", ""))
        self.status_var.set(record.get("status", self.status_values[0]))
        self.created_at_var.set(record.get("created_at", "") or "-")
        self.updated_at_var.set(record.get("updated_at", "") or "-")
        self.short_note_text.delete("1.0", END)
        self.short_note_text.insert("1.0", record.get("short_note", ""))
        self.set_mode("edit")
        self.schedule_state_save()

    def collect_form_data(self) -> dict[str, str]:
        return {
            "record_id": self.current_record_id,
            "title": self.title_var.get().strip(),
            "category": self.category_var.get().strip(),
            "name": self.name_var.get().strip(),
            "phone_number": self.phone_var.get().strip(),
            "status": self.status_var.get().strip() or self.status_values[0],
            "short_note": self.short_note_text.get("1.0", END).strip(),
        }

    def validate_form_data(self, data: dict[str, str]) -> None:
        if not data["title"]:
            raise ValueError("Title is required.")
        if not data["category"]:
            raise ValueError("Category is required.")
        if not data["name"]:
            raise ValueError("Name is required.")
        if not data["phone_number"]:
            raise ValueError("Phone number is required.")
        if data["status"] not in self.status_values:
            raise ValueError("Status must be Open or Close.")

        digits_only = re.sub(r"\D", "", data["phone_number"])
        if len(digits_only) < 7 or len(digits_only) > 15:
            raise ValueError("Phone number must contain between 7 and 15 digits.")
        if not re.fullmatch(r"[0-9+\-\s()]+", data["phone_number"]):
            raise ValueError("Phone number contains unsupported characters.")

    def prepare_new_record(self) -> None:
        self.clear_form()
        self.set_mode("add")
        self.set_status("Form is ready for a new record.")

    def clear_form(self) -> None:
        self.current_record_id = ""
        self.record_id_var.set("Selected Record ID: new record (ID assigned on save)")
        self.created_at_var.set("Assigned on save")
        self.updated_at_var.set("Assigned on save")
        self.title_var.set("")
        self.category_var.set("")
        self.name_var.set("")
        self.phone_var.set("")
        self.status_var.set(self.status_values[0])
        self.short_note_text.delete("1.0", END)
        self.tree.selection_remove(self.tree.selection())
        self.set_mode("idle")
        self.schedule_state_save()

    def clear_search(self) -> None:
        self.search_var.set("")
        self.apply_filter()

    def save_record(self) -> None:
        form_data = self.collect_form_data()
        try:
            self.validate_form_data(form_data)
            records = self.csv_manager.load_records()

            if self.current_record_id:
                existing = self.csv_manager.find_record(records, self.current_record_id)
                if not existing:
                    raise ValueError("The selected record no longer exists on disk.")
                updated_record = self.csv_manager.build_updated_record(self.current_record_id, form_data, existing)
                updated_records = [
                    updated_record if item.get("record_id") == self.current_record_id else item
                    for item in records
                ]
                action = "updated"
            else:
                new_record = self.csv_manager.build_new_record(form_data)
                self.current_record_id = new_record["record_id"]
                updated_records = records + [new_record]
                action = "created"

            self.csv_manager.save_records(updated_records, backup_reason=action)
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.filtered_records = self.csv_manager.filter_records(self.records, self.search_var.get())
            self.populate_tree(self.current_record_id)
            saved_record = self.csv_manager.find_record(self.records, self.current_record_id)
            if saved_record:
                self.load_record_into_form(saved_record)
            else:
                self.record_id_var.set(f"Selected Record ID: {self.current_record_id}")
            self.session_manager.record_successful_save(len(self.records))
            self.set_mode("edit")
            self.set_status(f"Record {self.current_record_id} {action} successfully.")
            self.schedule_state_save()
        except ValueError as exc:
            messagebox.showwarning("Validation Error", str(exc))
            self.set_status(str(exc), error=True)
        except Exception as exc:
            self.logger.exception("Failed to save record")
            self.session_manager.record_error(str(exc))
            messagebox.showerror(
                "Save Error",
                "The application could not save the record.\n\n"
                "Your original CSV file was left untouched if the save did not validate.\n\n"
                f"Technical message: {exc}",
            )
            self.set_status("Failed to save record. See the log file for details.", error=True)

    def delete_selected_record(self) -> None:
        record_id = self.current_record_id
        if not record_id:
            messagebox.showinfo("Delete Record", "Select a record before attempting to delete it.")
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete record {record_id}?\n\nA CSV backup will be created before the file is replaced.",
        ):
            return

        try:
            updated_records = [record for record in self.csv_manager.load_records() if record.get("record_id") != record_id]
            self.csv_manager.save_records(updated_records, backup_reason="delete")
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.current_record_id = ""
            self.clear_form()
            self.apply_filter()
            self.session_manager.record_successful_save(len(self.records))
            self.set_status(f"Record {record_id} deleted.")
        except Exception as exc:
            self.logger.exception("Failed to delete record")
            self.session_manager.record_error(str(exc))
            messagebox.showerror("Delete Error", f"The record could not be deleted.\n\n{exc}")
            self.set_status("Failed to delete record. See the log file for details.", error=True)

    def on_tree_selection(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if not values:
            return
        record_id = values[0]
        record = self.csv_manager.find_record(self.records, record_id)
        if record:
            self.load_record_into_form(record)
            self.set_status(f"Loaded record {record_id} into the form.")

    def on_search_changed(self, *_args: Any) -> None:
        self.apply_filter()

    def on_form_changed(self, *_args: Any) -> None:
        self.schedule_state_save()

    def schedule_state_save(self) -> None:
        if self.pending_state_save_job:
            self.root.after_cancel(self.pending_state_save_job)
        self.pending_state_save_job = self.root.after(500, self.persist_session_state)

    def persist_session_state(self) -> None:
        self.pending_state_save_job = None
        try:
            if self.root.state() == "zoomed":
                geometry = self.session_state.get("window_geometry", self.root.winfo_geometry())
            else:
                geometry = self.root.winfo_geometry()

            state = {
                "window_geometry": geometry,
                "window_state": self.root.state(),
                "search_text": self.search_var.get(),
                "selected_record_id": self.current_record_id,
                "mode": self.mode,
                "last_opened_at": self.session_state.get("last_opened_at", ""),
                "form_values": self.collect_form_data(),
            }
            self.session_state = state
            self.session_manager.save_session_state(state)
        except Exception:
            self.logger.exception("Failed to persist session state")

    def build_shutdown_session_state(self) -> dict[str, Any]:
        geometry = self.session_state.get("window_geometry", "")
        if self.root.state() != "zoomed":
            geometry = self.root.winfo_geometry()

        return {
            "window_geometry": geometry,
            "window_state": self.root.state(),
            "search_text": self.search_var.get(),
            "selected_record_id": self.current_record_id,
            "mode": self.mode,
            "last_opened_at": self.session_state.get("last_opened_at", ""),
            "form_values": self.collect_form_data(),
        }

    def on_close(self) -> None:
        try:
            shutdown_state = self.build_shutdown_session_state()
            self.session_manager.mark_clean_shutdown(shutdown_state)
        except Exception:
            self.logger.exception("Failed during clean shutdown")
        finally:
            self.root.destroy()

    def open_data_folder(self) -> None:
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.csv_path.parent))
        except Exception as exc:
            self.logger.exception("Failed to open data folder")
            messagebox.showerror("Open Folder Error", f"Could not open the data folder.\n\n{exc}")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_var.set(f"Mode: {mode}")
        self.schedule_state_save()

    def set_status(self, message: str, error: bool = False) -> None:
        prefix = "Status: "
        self.status_message_var.set(f"{prefix}{message}")
