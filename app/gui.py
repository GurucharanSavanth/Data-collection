from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import END, VERTICAL, messagebox, ttk
from typing import Any

from constants import (
    APP_VERSION,
    DIRECT_CHILD_ROLES,
    MANAGER_ROLES,
    RECORD_STATUSES,
    ROLE_CANDIDATE,
    ROLE_ORDER,
    ROLE_SUPER_ADMIN,
    SOURCE_MODE_OFFLINE,
    SOURCE_MODE_ONLINE,
)
from services import AppServices
from session_manager import SessionManager
from utils import current_timestamp


class RecordManagerApp:
    def __init__(
        self,
        *,
        root: tk.Tk,
        settings: dict[str, Any],
        services: AppServices,
        session_manager: SessionManager,
        logger: Any,
        data_dir: Path,
        app_state: dict[str, Any] | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.services = services
        self.session_manager = session_manager
        self.logger = logger
        self.data_dir = data_dir
        self.app_state = app_state or self.session_manager.mark_startup()
        self.session_state = self.session_manager.load_session_state()
        self.session_state["last_opened_at"] = current_timestamp()

        self.current_user: dict[str, object] | None = None
        self.current_view = ""
        self.current_record_public_id = str(self.session_state.get("selected_record_public_id", "") or "")
        self.current_source_preview: dict[str, object] | None = None
        self.pending_state_save_job: str | None = None

        self.record_form_values = self.session_state.get("record_form", {}) if isinstance(self.session_state.get("record_form"), dict) else {}

        self.root.title(str(settings.get("window_title", "Record Manager Dashboard")))
        self.root.geometry(str(self.session_state.get("window_geometry") or settings.get("default_window_size", "1360x860")))
        if self.session_state.get("window_state") in {"normal", "zoomed"}:
            self.root.state(str(self.session_state["window_state"]))
        self.root.minsize(960, 640)

        self.login_id_var = tk.StringVar(value=str(self.session_state.get("last_login_id", "")))
        self.login_password_var = tk.StringVar()
        self.login_show_password_var = tk.BooleanVar(value=False)
        self.bootstrap_login_var = tk.StringVar(value="super.admin")
        self.bootstrap_display_name_var = tk.StringVar(value="Super Admin")
        self.bootstrap_password_var = tk.StringVar()
        self.bootstrap_confirm_var = tk.StringVar()
        self.bootstrap_show_password_var = tk.BooleanVar(value=False)

        self.dashboard_title_var = tk.StringVar(value="")
        self.dashboard_path_var = tk.StringVar(value="")
        self.status_message_var = tk.StringVar(value="Ready.")

        self.candidate_selection_var = tk.StringVar(value=str(self.session_state.get("selected_candidate_login_id", "")))
        self.user_selection_var = tk.StringVar(value=str(self.session_state.get("selected_user_login_id", "")))

        self.record_title_var = tk.StringVar(value=str(self.record_form_values.get("title_display", "")))
        self.record_application_var = tk.StringVar(value=str(self.record_form_values.get("application_number", "")))
        self.record_name_var = tk.StringVar(value=str(self.record_form_values.get("name", "")))
        self.record_phone_var = tk.StringVar(value=str(self.record_form_values.get("phone_number", "")))
        self.record_status_var = tk.StringVar(value=str(self.record_form_values.get("status", RECORD_STATUSES[0])))
        self.record_created_at_var = tk.StringVar(value="-")
        self.record_updated_at_var = tk.StringVar(value="-")

        self.user_login_var = tk.StringVar()
        self.user_role_var = tk.StringVar(value=ROLE_ORDER[1])
        self.user_display_name_var = tk.StringVar()
        self.user_location_var = tk.StringVar()
        self.user_phone_var = tk.StringVar()
        self.user_parent_var = tk.StringVar()
        self.user_password_var = tk.StringVar()
        self.user_active_var = tk.BooleanVar(value=True)
        self.user_parent_hint_var = tk.StringVar(value="")

        self.source_mode_var = tk.StringVar(value=SOURCE_MODE_OFFLINE)
        self.source_local_path_var = tk.StringVar()
        self.source_remote_url_var = tk.StringVar()
        self.source_health_var = tk.StringVar(value="Source health: unknown")
        self.source_last_sync_var = tk.StringVar(value="Last sync: never")
        self.source_checksum_var = tk.StringVar(value="Checksum: -")

        self._configure_styles()
        self.root.bind("<Return>", self.on_primary_action)
        self._build_initial_view()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.configure("AuthCard.TFrame", padding=28)
        style.configure("AuthTitle.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("AuthSubtitle.TLabel", foreground="#495057")
        style.configure("AuthHint.TLabel", foreground="#5f6b76")

    def _build_auth_shell(self, title: str, subtitle: str) -> ttk.Frame:
        self.root.minsize(860, 560)
        outer = ttk.Frame(self.root, padding=32)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        card = ttk.Frame(outer, style="AuthCard.TFrame")
        card.grid(row=0, column=0)
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text=title, style="AuthTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text=subtitle, style="AuthSubtitle.TLabel", wraplength=520, justify="left").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 18),
        )
        ttk.Label(card, text=f"Version {APP_VERSION}", style="AuthHint.TLabel").grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12),
        )
        return card

    def _toggle_password_entry(self, entry: ttk.Entry, visible: bool) -> None:
        entry.configure(show="" if visible else "*")

    def on_primary_action(self, _event: tk.Event | None = None) -> str | None:
        if self.current_view == "login":
            self.handle_login()
            return "break"
        if self.current_view == "bootstrap":
            self.handle_bootstrap()
            return "break"
        return None

    def _build_initial_view(self) -> None:
        if self.services.auth_service.needs_bootstrap():
            self.show_bootstrap_view()
        else:
            self.show_login_view()

    def clear_root(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def show_bootstrap_view(self) -> None:
        self.clear_root()
        self.current_view = "bootstrap"
        frame = self._build_auth_shell(
            "Bootstrap Super Admin",
            "First launch detected. Create the initial SUPER_ADMIN account. "
            "This account controls credential sync, hierarchy setup, and downstream manager provisioning.",
        )

        ttk.Label(frame, text="Login ID").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.bootstrap_login_entry = ttk.Entry(frame, textvariable=self.bootstrap_login_var)
        self.bootstrap_login_entry.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="Display Name").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(frame, textvariable=self.bootstrap_display_name_var).grid(row=4, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="Password").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=6)
        self.bootstrap_password_entry = ttk.Entry(frame, textvariable=self.bootstrap_password_var, show="*")
        self.bootstrap_password_entry.grid(row=5, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="Confirm Password").grid(row=6, column=0, sticky="w", padx=(0, 12), pady=6)
        self.bootstrap_confirm_entry = ttk.Entry(frame, textvariable=self.bootstrap_confirm_var, show="*")
        self.bootstrap_confirm_entry.grid(row=6, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(
            frame,
            text="Show password",
            variable=self.bootstrap_show_password_var,
            command=lambda: (
                self._toggle_password_entry(self.bootstrap_password_entry, self.bootstrap_show_password_var.get()),
                self._toggle_password_entry(self.bootstrap_confirm_entry, self.bootstrap_show_password_var.get()),
            ),
        ).grid(row=7, column=1, sticky="w", pady=(2, 10))
        ttk.Button(frame, text="Create Super Admin", command=self.handle_bootstrap).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(frame, text="Press Enter to create the account.", style="AuthHint.TLabel").grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(frame, textvariable=self.status_message_var, wraplength=520, justify="left").grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(14, 0),
        )
        self.root.after(25, self.bootstrap_password_entry.focus_set)

    def show_login_view(self) -> None:
        self.clear_root()
        self.current_view = "login"
        frame = self._build_auth_shell(
            "Role Login",
            "Use your assigned Login ID and password. Candidate referral number is always the same as the candidate Login ID.",
        )

        ttk.Label(frame, text="Login ID").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.login_id_entry = ttk.Entry(frame, textvariable=self.login_id_var)
        self.login_id_entry.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="Password").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=6)
        self.login_password_entry = ttk.Entry(frame, textvariable=self.login_password_var, show="*")
        self.login_password_entry.grid(row=4, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(
            frame,
            text="Show password",
            variable=self.login_show_password_var,
            command=lambda: self._toggle_password_entry(self.login_password_entry, self.login_show_password_var.get()),
        ).grid(row=5, column=1, sticky="w", pady=(2, 10))
        ttk.Button(frame, text="Login", command=self.handle_login).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(frame, text="Press Enter to sign in.", style="AuthHint.TLabel").grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(frame, textvariable=self.status_message_var, wraplength=520, justify="left").grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(14, 0),
        )
        focus_target = self.login_password_entry if self.login_id_var.get().strip() else self.login_id_entry
        self.root.after(25, focus_target.focus_set)

    def handle_bootstrap(self) -> None:
        if self.bootstrap_password_var.get() != self.bootstrap_confirm_var.get():
            self.set_status("Bootstrap passwords do not match.", error=True)
            messagebox.showwarning("Bootstrap Error", "Passwords do not match.")
            return
        try:
            self.current_user = self.services.auth_service.bootstrap_super_admin(
                self.bootstrap_login_var.get(),
                self.bootstrap_password_var.get(),
                self.bootstrap_display_name_var.get(),
            )
            self.set_status("Super Admin bootstrap completed.")
            self.build_dashboard_view()
        except Exception as exc:
            self.logger.exception("Failed to bootstrap super admin")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Bootstrap Error", str(exc))

    def handle_login(self) -> None:
        try:
            user = self.services.auth_service.authenticate(self.login_id_var.get(), self.login_password_var.get())
            self.current_user = user
            self.login_password_var.set("")
            self.session_state["last_login_id"] = str(user["login_id"])
            if str(user["password_state"]) != "ACTIVE":
                self.prompt_password_reset(user)
                user = self.services.user_service.get_user(int(user["user_id"])) or user
                self.current_user = user
            self.build_dashboard_view()
        except Exception as exc:
            self.logger.exception("Login failed")
            self.session_manager.record_error(str(exc))
            self.login_password_var.set("")
            self.set_status(str(exc), error=True)
            messagebox.showerror("Login Error", str(exc))

    def prompt_password_reset(self, user: dict[str, object]) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Reset Password")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        new_password_var = tk.StringVar()
        confirm_password_var = tk.StringVar()

        ttk.Label(dialog, text="Password reset required", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 12))
        ttk.Label(dialog, text="New Password").grid(row=1, column=0, sticky="w", padx=16, pady=6)
        ttk.Entry(dialog, textvariable=new_password_var, show="*").grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=6)
        ttk.Label(dialog, text="Confirm Password").grid(row=2, column=0, sticky="w", padx=16, pady=6)
        ttk.Entry(dialog, textvariable=confirm_password_var, show="*").grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=6)

        result = {"done": False}

        def submit() -> None:
            if new_password_var.get() != confirm_password_var.get():
                messagebox.showwarning("Reset Password", "Passwords do not match.", parent=dialog)
                return
            try:
                self.services.auth_service.change_password(
                    user,
                    new_password=new_password_var.get(),
                    bypass_current=True,
                )
                result["done"] = True
                dialog.destroy()
            except Exception as exc:
                self.logger.exception("Failed to reset password")
                messagebox.showerror("Reset Password", str(exc), parent=dialog)

        ttk.Button(dialog, text="Save Password", command=submit).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 16))
        dialog.bind("<Return>", lambda _event: submit())
        dialog.after(25, lambda: dialog.focus_force())
        dialog.wait_window()
        if not result["done"]:
            raise ValueError("Password reset is required before entering the dashboard.")

    def build_dashboard_view(self) -> None:
        if self.current_user is None:
            self.show_login_view()
            return

        self.root.minsize(1180, 760)
        self.clear_root()
        self.current_view = "dashboard"
        self.current_record_public_id = str(self.session_state.get("selected_record_public_id", "") or self.current_record_public_id or "")

        wrapper = ttk.Frame(self.root, padding=12)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(1, weight=1)

        header = ttk.Frame(wrapper)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        self.dashboard_title_var.set(self._build_dashboard_title())
        self.dashboard_path_var.set(self._build_user_path_label())
        ttk.Label(header, textvariable=self.dashboard_title_var, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.dashboard_path_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Logout", command=self.logout).grid(row=0, column=1, rowspan=2, sticky="e")

        self.notebook = ttk.Notebook(wrapper)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        self.records_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.records_tab, text="Records")
        self._build_records_tab()

        if str(self.current_user["role"]) != ROLE_CANDIDATE:
            self.users_tab = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(self.users_tab, text="Users")
            self._build_users_tab()

            self.hierarchy_tab = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(self.hierarchy_tab, text="Hierarchy")
            self._build_hierarchy_tab()

        if str(self.current_user["role"]) == ROLE_SUPER_ADMIN:
            self.source_tab = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(self.source_tab, text="Credential Source")
            self._build_source_tab()

            self.audit_tab = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(self.audit_tab, text="Audit / Recovery")
            self._build_audit_tab()

        footer = ttk.Frame(wrapper)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_message_var).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=f"Version {APP_VERSION}").grid(row=0, column=1, sticky="e")

        self.refresh_dashboard_data()
        if self.app_state.get("unclean_previous_shutdown"):
            messagebox.showwarning(
                "Recovered Previous Session",
                "The previous session did not shut down cleanly. Session preferences were restored where possible.",
            )

    def _build_dashboard_title(self) -> str:
        if self.current_user is None:
            return "Record Manager Dashboard"
        role = str(self.current_user["role"]).replace("_", " ").title()
        if str(self.current_user["role"]) == ROLE_CANDIDATE:
            return f"Candidate Dashboard: {self.current_user['display_name']}"
        return f"{role} Dashboard: {self.current_user['display_name']}"

    def _build_user_path_label(self) -> str:
        if self.current_user is None:
            return ""
        try:
            path = self.services.user_service.get_user_path(int(self.current_user["user_id"]))
        except Exception:
            self.logger.exception("Failed to build user path")
            return ""
        parts = [f"{node['display_name']} ({node['role']})" for node in path]
        if str(self.current_user["role"]) == ROLE_CANDIDATE:
            return "Candidate Context: " + " -> ".join(parts)
        return "Manager Path: " + " -> ".join(parts)

    def _build_records_tab(self) -> None:
        self.records_tab.columnconfigure(0, weight=3)
        self.records_tab.columnconfigure(1, weight=2)
        self.records_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.records_tab)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Candidate Name", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.record_context_var = tk.StringVar(value="")
        ttk.Label(controls, textvariable=self.record_context_var).grid(row=0, column=1, sticky="w")

        if str(self.current_user["role"]) != ROLE_CANDIDATE:
            ttk.Label(controls, text="Candidate").grid(row=1, column=0, sticky="w", pady=(8, 0))
            self.candidate_combo = ttk.Combobox(controls, textvariable=self.candidate_selection_var, state="readonly")
            self.candidate_combo.grid(row=1, column=1, sticky="ew", pady=(8, 0))
            self.candidate_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_candidate_changed())

        tree_frame = ttk.Frame(self.records_tab)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        if str(self.current_user["role"]) == ROLE_CANDIDATE:
            columns = ("public_id", "name", "phone_number", "created_at", "candidate_login_id")
            headings = {
                "public_id": "Record ID",
                "name": "Name",
                "phone_number": "Phone Number",
                "created_at": "Created At",
                "candidate_login_id": "Referral Number",
            }
        else:
            columns = ("public_id", "application_number", "candidate_login_id", "name", "status", "created_at", "updated_at")
            headings = {
                "public_id": "Record ID",
                "application_number": "Application Number",
                "candidate_login_id": "Referral Number",
                "name": "Name",
                "status": "Status",
                "created_at": "Created At",
                "updated_at": "Updated At",
            }

        self.record_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.record_tree.heading(column, text=headings[column])
            self.record_tree.column(column, width=145 if column not in {"name", "application_number"} else 180, anchor="w", stretch=column == "name")
        self.record_tree.grid(row=0, column=0, sticky="nsew")
        record_scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.record_tree.yview)
        record_scrollbar.grid(row=0, column=1, sticky="ns")
        self.record_tree.configure(yscrollcommand=record_scrollbar.set)
        self.record_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_record_selected())

        form = ttk.Frame(self.records_tab)
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(8, weight=1)

        ttk.Label(form, text="Record Details", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(form, text="Title").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        self.title_entry = ttk.Entry(form, textvariable=self.record_title_var)
        self.title_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Application Number").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(form, textvariable=self.record_application_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Name").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(form, textvariable=self.record_name_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Phone Number").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(form, textvariable=self.record_phone_var).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Status").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Combobox(form, textvariable=self.record_status_var, values=RECORD_STATUSES, state="readonly").grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Created At").grid(row=6, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Label(form, textvariable=self.record_created_at_var).grid(row=6, column=1, sticky="w", pady=4)
        ttk.Label(form, text="Updated At").grid(row=7, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Label(form, textvariable=self.record_updated_at_var).grid(row=7, column=1, sticky="w", pady=4)
        ttk.Label(form, text="Short Notes / Description").grid(row=8, column=0, sticky="nw", padx=(0, 12), pady=4)
        self.record_short_note = tk.Text(form, height=8, wrap="word")
        self.record_short_note.grid(row=8, column=1, sticky="nsew", pady=4)

        action_row = ttk.Frame(form)
        action_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for index in range(4):
            action_row.columnconfigure(index, weight=1)

        self.new_record_button = ttk.Button(action_row, text="New Record Report", command=self.prepare_new_record)
        self.new_record_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_row, text="Save Record", command=self.save_record).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(action_row, text="Archive Record", command=self.archive_record).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(action_row, text="Export CSV", command=self.export_visible_records).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        version_frame = ttk.LabelFrame(form, text="Version History", padding=8)
        version_frame.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        version_frame.columnconfigure(0, weight=1)
        version_frame.rowconfigure(0, weight=1)

        self.version_tree = ttk.Treeview(version_frame, columns=("version_number", "change_type", "changed_at"), show="headings", height=6, selectmode="browse")
        self.version_tree.heading("version_number", text="Version")
        self.version_tree.heading("change_type", text="Change")
        self.version_tree.heading("changed_at", text="Changed At")
        self.version_tree.column("version_number", width=80, anchor="w")
        self.version_tree.column("change_type", width=120, anchor="w")
        self.version_tree.column("changed_at", width=180, anchor="w")
        self.version_tree.grid(row=0, column=0, sticky="nsew")
        ttk.Button(version_frame, text="Restore Selected Version", command=self.restore_selected_version).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_users_tab(self) -> None:
        self.users_tab.columnconfigure(0, weight=3)
        self.users_tab.columnconfigure(1, weight=2)
        self.users_tab.rowconfigure(0, weight=1)

        tree_frame = ttk.Frame(self.users_tab)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.user_tree = ttk.Treeview(
            tree_frame,
            columns=("login_id", "role", "display_name", "parent_login_id", "active_flag"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in [
            ("login_id", "Login ID", 160),
            ("role", "Role", 160),
            ("display_name", "Candidate Name", 180),
            ("parent_login_id", "Parent", 160),
            ("active_flag", "Active", 80),
        ]:
            self.user_tree.heading(column, text=title)
            self.user_tree.column(column, width=width, anchor="w", stretch=column == "display_name")
        self.user_tree.grid(row=0, column=0, sticky="nsew")
        user_scroll = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.user_tree.yview)
        user_scroll.grid(row=0, column=1, sticky="ns")
        self.user_tree.configure(yscrollcommand=user_scroll.set)
        self.user_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_user_selected())

        form = ttk.Frame(self.users_tab)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Scoped User Management", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for row_index, (label, variable, widget_type) in enumerate(
            [
                ("Login ID", self.user_login_var, "entry"),
                ("Role", self.user_role_var, "combo"),
                ("Candidate Name", self.user_display_name_var, "entry"),
                ("Deployed Location", self.user_location_var, "entry"),
                ("Phone", self.user_phone_var, "entry"),
                ("Parent Login ID", self.user_parent_var, "parent_combo"),
                ("Password / Reset Password", self.user_password_var, "entry"),
            ],
            start=1,
        ):
            ttk.Label(form, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=4)
            if widget_type == "combo":
                self.user_role_combo = ttk.Combobox(form, textvariable=variable, values=ROLE_ORDER[1:], state="readonly")
                self.user_role_combo.grid(row=row_index, column=1, sticky="ew", pady=4)
                self.user_role_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_parent_choices())
            elif widget_type == "parent_combo":
                self.user_parent_combo = ttk.Combobox(form, textvariable=variable, state="readonly")
                self.user_parent_combo.grid(row=row_index, column=1, sticky="ew", pady=4)
            else:
                show = "*" if "Password" in label else None
                entry = ttk.Entry(form, textvariable=variable, show=show)
                entry.grid(row=row_index, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(form, text="Active", variable=self.user_active_var).grid(row=8, column=1, sticky="w", pady=(4, 12))
        ttk.Label(form, textvariable=self.user_parent_hint_var, style="AuthHint.TLabel", wraplength=320, justify="left").grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12),
        )

        action_row = ttk.Frame(form)
        action_row.grid(row=10, column=0, columnspan=2, sticky="ew")
        for index in range(3):
            action_row.columnconfigure(index, weight=1)
        ttk.Button(action_row, text="Create User", command=self.create_user).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_row, text="Update User", command=self.update_user).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(action_row, text="Reset Password", command=self.reset_user_password).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _build_hierarchy_tab(self) -> None:
        self.hierarchy_tab.columnconfigure(0, weight=1)
        self.hierarchy_tab.rowconfigure(0, weight=1)
        self.hierarchy_tree = ttk.Treeview(self.hierarchy_tab, columns=("role", "location", "records"), show="tree headings")
        self.hierarchy_tree.heading("#0", text="Node")
        self.hierarchy_tree.heading("role", text="Role")
        self.hierarchy_tree.heading("location", text="Location")
        self.hierarchy_tree.heading("records", text="Record Count")
        self.hierarchy_tree.column("#0", width=260, anchor="w")
        self.hierarchy_tree.column("role", width=180, anchor="w")
        self.hierarchy_tree.column("location", width=220, anchor="w")
        self.hierarchy_tree.column("records", width=100, anchor="w")
        self.hierarchy_tree.grid(row=0, column=0, sticky="nsew")

    def _build_source_tab(self) -> None:
        self.source_tab.columnconfigure(0, weight=1)
        self.source_tab.rowconfigure(2, weight=1)
        self.source_tab.rowconfigure(4, weight=1)

        config_frame = ttk.LabelFrame(self.source_tab, text="Credential Source Configuration", padding=8)
        config_frame.grid(row=0, column=0, sticky="ew")
        config_frame.columnconfigure(1, weight=1)

        ttk.Radiobutton(config_frame, text="Offline (Path)", variable=self.source_mode_var, value=SOURCE_MODE_OFFLINE).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(config_frame, text="Online (URL)", variable=self.source_mode_var, value=SOURCE_MODE_ONLINE).grid(row=0, column=1, sticky="w")
        ttk.Label(config_frame, text="Local Path").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(config_frame, textvariable=self.source_local_path_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(config_frame, text="Remote URL").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(config_frame, textvariable=self.source_remote_url_var).grid(row=2, column=1, sticky="ew", pady=4)

        action_row = ttk.Frame(config_frame)
        action_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for index in range(3):
            action_row.columnconfigure(index, weight=1)
        ttk.Button(action_row, text="Save Source", command=self.save_source_config).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_row, text="Preview Import", command=self.preview_source_import).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(action_row, text="Manual Sync / Refresh", command=self.commit_source_import).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        info_frame = ttk.Frame(self.source_tab)
        info_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=1)
        ttk.Label(info_frame, textvariable=self.source_health_var).grid(row=0, column=0, sticky="w")
        ttk.Label(info_frame, textvariable=self.source_last_sync_var).grid(row=0, column=1, sticky="w")
        ttk.Label(info_frame, textvariable=self.source_checksum_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        preview_frame = ttk.LabelFrame(self.source_tab, text="Preview", padding=8)
        preview_frame.grid(row=2, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.source_preview_tree = ttk.Treeview(
            preview_frame,
            columns=("row_number", "login_id", "role", "action", "accepted", "errors"),
            show="headings",
        )
        for column, title, width in [
            ("row_number", "Row", 70),
            ("login_id", "Login ID", 140),
            ("role", "Role", 150),
            ("action", "Action", 100),
            ("accepted", "Accepted", 80),
            ("errors", "Errors", 420),
        ]:
            self.source_preview_tree.heading(column, text=title)
            self.source_preview_tree.column(column, width=width, anchor="w", stretch=column == "errors")
        self.source_preview_tree.grid(row=0, column=0, sticky="nsew")

        snapshot_frame = ttk.LabelFrame(self.source_tab, text="Snapshot History", padding=8)
        snapshot_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        snapshot_frame.columnconfigure(0, weight=1)
        snapshot_frame.rowconfigure(0, weight=1)
        self.source_snapshot_tree = ttk.Treeview(
            snapshot_frame,
            columns=("snapshot_id", "source_mode", "source_reference", "imported_at", "sync_status", "accepted_row_count", "rejected_row_count"),
            show="headings",
        )
        for column, title, width in [
            ("snapshot_id", "Snapshot", 80),
            ("source_mode", "Mode", 90),
            ("source_reference", "Reference", 260),
            ("imported_at", "Imported At", 160),
            ("sync_status", "Status", 90),
            ("accepted_row_count", "Accepted", 80),
            ("rejected_row_count", "Rejected", 80),
        ]:
            self.source_snapshot_tree.heading(column, text=title)
            self.source_snapshot_tree.column(column, width=width, anchor="w", stretch=column == "source_reference")
        self.source_snapshot_tree.grid(row=0, column=0, sticky="nsew")

    def _build_audit_tab(self) -> None:
        self.audit_tab.columnconfigure(0, weight=1)
        self.audit_tab.rowconfigure(1, weight=1)
        self.audit_tab.rowconfigure(3, weight=1)

        ttk.Label(self.audit_tab, text="Audit Trail", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.audit_tree = ttk.Treeview(
            self.audit_tab,
            columns=("created_at", "action_type", "target_type", "target_id", "success_flag", "message"),
            show="headings",
        )
        for column, title, width in [
            ("created_at", "Created At", 160),
            ("action_type", "Action", 150),
            ("target_type", "Target Type", 120),
            ("target_id", "Target ID", 160),
            ("success_flag", "Success", 80),
            ("message", "Message", 360),
        ]:
            self.audit_tree.heading(column, text=title)
            self.audit_tree.column(column, width=width, anchor="w", stretch=column == "message")
        self.audit_tree.grid(row=1, column=0, sticky="nsew")

        ttk.Label(self.audit_tab, text="Recovery / Backup Registry", font=("Segoe UI", 12, "bold")).grid(row=2, column=0, sticky="w", pady=(12, 8))
        self.backup_tree = ttk.Treeview(
            self.audit_tab,
            columns=("created_at", "backup_type", "target_type", "target_id", "artifact_path", "restore_test_status"),
            show="headings",
        )
        for column, title, width in [
            ("created_at", "Created At", 160),
            ("backup_type", "Backup Type", 150),
            ("target_type", "Target Type", 120),
            ("target_id", "Target ID", 120),
            ("artifact_path", "Artifact Path", 360),
            ("restore_test_status", "Restore Status", 120),
        ]:
            self.backup_tree.heading(column, text=title)
            self.backup_tree.column(column, width=width, anchor="w", stretch=column == "artifact_path")
        self.backup_tree.grid(row=3, column=0, sticky="nsew")

    def refresh_dashboard_data(self) -> None:
        if self.current_user is None:
            return
        self.dashboard_title_var.set(self._build_dashboard_title())
        self.dashboard_path_var.set(self._build_user_path_label())
        self.refresh_records_tab()
        if str(self.current_user["role"]) != ROLE_CANDIDATE:
            self.refresh_users_tab()
            self.refresh_hierarchy_tab()
        if str(self.current_user["role"]) == ROLE_SUPER_ADMIN:
            self.refresh_source_tab()
            self.refresh_audit_tab()

    def refresh_records_tab(self) -> None:
        if self.current_user is None:
            return
        visible_records = self.services.record_service.list_records(self.current_user)
        self.visible_records = visible_records

        if str(self.current_user["role"]) == ROLE_CANDIDATE:
            self.record_context_var.set(f"{self.current_user['display_name']} | Referral / Login: {self.current_user['login_id']}")
            self.record_title_var.set(f"{self.current_user['display_name']} : {self.current_user['deployed_location']}".strip(" :"))
            self.title_entry.state(["readonly"])
        else:
            self.title_entry.state(["!readonly"])
            candidate_choices = self.services.user_service.list_candidate_choices(self.current_user)
            self.candidate_lookup = {
                candidate["login_id"]: candidate
                for candidate in candidate_choices
            }
            display_values = [
                f"{candidate['login_id']} | {candidate['display_name']}"
                for candidate in candidate_choices
            ]
            if hasattr(self, "candidate_combo"):
                self.candidate_combo["values"] = display_values
                selected_login = self.candidate_selection_var.get()
                if selected_login and selected_login in self.candidate_lookup:
                    self.candidate_combo.set(f"{selected_login} | {self.candidate_lookup[selected_login]['display_name']}")
                elif display_values:
                    self.candidate_combo.set(display_values[0])
                    self.candidate_selection_var.set(display_values[0].split(" | ", 1)[0])
                self.record_context_var.set(self._candidate_context_label(self.candidate_selection_var.get()))

        self.record_tree.delete(*self.record_tree.get_children())
        for record in visible_records:
            values = tuple(record.get(column, "") for column in self.record_tree["columns"])
            self.record_tree.insert("", END, iid=str(record["public_id"]), values=values)

        if self.current_record_public_id and self.record_tree.exists(self.current_record_public_id):
            self.record_tree.selection_set(self.current_record_public_id)
            self.record_tree.focus(self.current_record_public_id)
            self.on_record_selected()
        elif visible_records:
            self.current_record_public_id = str(visible_records[0]["public_id"])
            self.record_tree.selection_set(self.current_record_public_id)
            self.record_tree.focus(self.current_record_public_id)
            self.on_record_selected()
        else:
            self.prepare_new_record()

    def refresh_users_tab(self) -> None:
        if self.current_user is None or str(self.current_user["role"]) == ROLE_CANDIDATE:
            return
        users = self.services.user_service.list_visible_users(self.current_user)
        self.visible_users = users
        self.visible_user_lookup_by_login = {str(user["login_id"]): user for user in users}
        lookup = {int(user["user_id"]): user for user in users}
        self.user_tree.delete(*self.user_tree.get_children())
        for user in users:
            parent = lookup.get(int(user["parent_user_id"])) if user.get("parent_user_id") else None
            self.user_tree.insert(
                "",
                END,
                iid=str(user["login_id"]),
                values=(
                    user["login_id"],
                    user["role"],
                    user["display_name"],
                    parent["login_id"] if parent else "",
                    "Yes" if user["active_flag"] else "No",
                ),
            )
        self.refresh_parent_choices()

    def refresh_hierarchy_tab(self) -> None:
        if self.current_user is None or str(self.current_user["role"]) == ROLE_CANDIDATE:
            return
        self.hierarchy_tree.delete(*self.hierarchy_tree.get_children())
        roots = self.services.user_service.build_tree(self.current_user)

        def insert_node(parent_id: str, node: dict[str, object]) -> None:
            label = f"{node['display_name']} [{node['login_id']}]"
            item_id = self.hierarchy_tree.insert(
                parent_id,
                END,
                text=label,
                values=(node["role"], node["deployed_location"], node["record_count"]),
                open=True,
            )
            for child in node["children"]:
                insert_node(item_id, child)

        for root in roots:
            insert_node("", root)

    def refresh_source_tab(self) -> None:
        with self.services.db_manager.connection() as connection:
            config = self.services.source_repository.get_source_config(connection)
        self.source_mode_var.set(str(config["source_mode"]))
        self.source_local_path_var.set(str(config["local_path"]))
        self.source_remote_url_var.set(str(config["remote_url"]))
        self.source_health_var.set(f"Source health: {config['last_sync_status'] or 'unknown'}")
        self.source_last_sync_var.set(f"Last sync: {config['last_sync_at'] or 'never'}")
        self.source_checksum_var.set(f"Checksum: {config['last_checksum'] or '-'}")

        self.source_snapshot_tree.delete(*self.source_snapshot_tree.get_children())
        for snapshot in self.services.source_sync_service.list_snapshots():
            self.source_snapshot_tree.insert(
                "",
                END,
                values=(
                    snapshot["snapshot_id"],
                    snapshot["source_mode"],
                    snapshot["source_reference"],
                    snapshot["imported_at"],
                    snapshot["sync_status"],
                    snapshot["accepted_row_count"],
                    snapshot["rejected_row_count"],
                ),
            )

    def refresh_audit_tab(self) -> None:
        with self.services.db_manager.connection() as connection:
            audit_rows = self.services.audit_repository.list_recent(connection, limit=100)
            backups = self.services.backup_service.backup_repository.list_backups(connection, limit=100)

        self.audit_tree.delete(*self.audit_tree.get_children())
        for row in audit_rows:
            self.audit_tree.insert(
                "",
                END,
                values=(
                    row["created_at"],
                    row["action_type"],
                    row["target_type"],
                    row["target_id"],
                    "Yes" if row["success_flag"] else "No",
                    row["message"],
                ),
            )

        self.backup_tree.delete(*self.backup_tree.get_children())
        for backup in backups:
            self.backup_tree.insert(
                "",
                END,
                values=(
                    backup["created_at"],
                    backup["backup_type"],
                    backup["target_type"],
                    backup["target_id"],
                    backup["artifact_path"],
                    backup["restore_test_status"],
                ),
            )

    def on_candidate_changed(self) -> None:
        combo_value = self.candidate_combo.get().strip() if hasattr(self, "candidate_combo") else self.candidate_selection_var.get().strip()
        selected_login = combo_value.split(" | ", 1)[0] if combo_value else ""
        self.candidate_selection_var.set(selected_login)
        self.record_context_var.set(self._candidate_context_label(selected_login))
        self.prepare_new_record()
        self.schedule_state_save()

    def _candidate_context_label(self, candidate_login_id: str) -> str:
        candidate = getattr(self, "candidate_lookup", {}).get(candidate_login_id)
        if candidate is None:
            return "Candidate context: select a candidate"
        return f"{candidate['display_name']} | Referral / Login: {candidate['login_id']}"

    def on_record_selected(self) -> None:
        selection = self.record_tree.selection()
        if not selection:
            return
        public_id = str(selection[0])
        try:
            record = self.services.record_service.get_record(self.current_user, public_id)  # type: ignore[arg-type]
        except Exception as exc:
            self.logger.exception("Failed to load record")
            self.set_status(str(exc), error=True)
            return
        self.load_record_form(record)

    def load_record_form(self, record: dict[str, object]) -> None:
        self.current_record_public_id = str(record["public_id"])
        self.record_title_var.set(str(record["title_display"]))
        self.record_application_var.set(str(record["application_number"]))
        self.record_name_var.set(str(record["name"]))
        self.record_phone_var.set(str(record["phone_number"]))
        self.record_status_var.set(str(record["status"]))
        self.record_created_at_var.set(str(record["created_at"]))
        self.record_updated_at_var.set(str(record["updated_at"]))
        self.record_short_note.delete("1.0", END)
        self.record_short_note.insert("1.0", str(record.get("short_note", "")))
        if str(self.current_user["role"]) != ROLE_CANDIDATE and getattr(self, "candidate_combo", None) is not None:
            candidate_login_id = str(record.get("candidate_login_id", ""))
            self.candidate_selection_var.set(candidate_login_id)
            if candidate_login_id in getattr(self, "candidate_lookup", {}):
                self.candidate_combo.set(f"{candidate_login_id} | {self.candidate_lookup[candidate_login_id]['display_name']}")
            self.record_context_var.set(self._candidate_context_label(candidate_login_id))
        self.refresh_record_versions()
        self.schedule_state_save()

    def prepare_new_record(self) -> None:
        self.current_record_public_id = ""
        if self.current_user is not None and str(self.current_user["role"]) == ROLE_CANDIDATE:
            title_display = f"{self.current_user['display_name']} : {self.current_user['deployed_location']}".strip(" :")
        else:
            selected_login = self.candidate_selection_var.get()
            title_display = self.record_title_var.get()
            if selected_login in getattr(self, "candidate_lookup", {}):
                candidate = self.candidate_lookup[selected_login]
                title_display = f"{candidate['display_name']} : {candidate['deployed_location']}".strip(" :")
        self.record_title_var.set(title_display)
        self.record_application_var.set("")
        self.record_name_var.set("")
        self.record_phone_var.set("")
        self.record_status_var.set(RECORD_STATUSES[0])
        self.record_created_at_var.set("-")
        self.record_updated_at_var.set("-")
        self.record_short_note.delete("1.0", END)
        self.version_tree.delete(*self.version_tree.get_children())
        self.schedule_state_save()

    def save_record(self) -> None:
        if self.current_user is None:
            return
        candidate_login_id = None if str(self.current_user["role"]) == ROLE_CANDIDATE else (self.candidate_selection_var.get().strip() or None)
        try:
            saved = self.services.record_service.save_record(
                self.current_user,
                public_id=self.current_record_public_id or None,
                candidate_login_id=candidate_login_id,
                application_number=self.record_application_var.get(),
                name=self.record_name_var.get(),
                phone_number=self.record_phone_var.get(),
                status=self.record_status_var.get(),
                short_note=self.record_short_note.get("1.0", END).strip(),
                manual_title_display=self.record_title_var.get(),
            )
            self.current_record_public_id = str(saved["public_id"])
            self.refresh_records_tab()
            self.services.record_service.get_record(self.current_user, self.current_record_public_id)
            self.session_manager.record_successful_save(len(self.services.record_service.list_records(self.current_user)))
            self.set_status(f"Saved record {self.current_record_public_id}.")
        except Exception as exc:
            self.logger.exception("Failed to save record")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Save Record", str(exc))

    def archive_record(self) -> None:
        if self.current_user is None or not self.current_record_public_id:
            return
        archived_public_id = self.current_record_public_id
        if not messagebox.askyesno("Archive Record", f"Archive record {archived_public_id}?"):
            return
        try:
            self.services.record_service.archive_record(self.current_user, archived_public_id)
            self.prepare_new_record()
            self.refresh_records_tab()
            self.set_status(f"Archived record {archived_public_id}.")
        except Exception as exc:
            self.logger.exception("Failed to archive record")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Archive Record", str(exc))

    def refresh_record_versions(self) -> None:
        self.version_tree.delete(*self.version_tree.get_children())
        if self.current_user is None or not self.current_record_public_id:
            return
        try:
            versions = self.services.record_service.list_versions(self.current_user, self.current_record_public_id)
        except Exception as exc:
            self.logger.exception("Failed to list record versions")
            self.set_status(str(exc), error=True)
            return
        for version in versions:
            self.version_tree.insert(
                "",
                END,
                iid=str(version["version_id"]),
                values=(version["version_number"], version["change_type"], version["changed_at"]),
            )

    def restore_selected_version(self) -> None:
        if self.current_user is None:
            return
        selection = self.version_tree.selection()
        if not selection:
            messagebox.showinfo("Restore Version", "Select a version first.")
            return
        version_id = int(selection[0])
        try:
            restored = self.services.record_service.restore_version(self.current_user, version_id)
            self.current_record_public_id = str(restored["public_id"])
            self.refresh_records_tab()
            self.set_status(f"Restored version for record {self.current_record_public_id}.")
        except Exception as exc:
            self.logger.exception("Failed to restore version")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Restore Version", str(exc))

    def export_visible_records(self) -> None:
        if self.current_user is None:
            return
        try:
            records = self.services.record_service.list_records(self.current_user)
            export_path = self.data_dir / "backups" / "runtime" / f"records_export_{current_timestamp().replace(':', '-').replace(' ', '_')}.csv"
            path = self.services.record_service.csv_manager.export_records_csv(records, export_path)
            self.set_status(f"Exported records to {path}.")
        except Exception as exc:
            self.logger.exception("Failed to export records")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Export Records", str(exc))

    def on_user_selected(self) -> None:
        selection = self.user_tree.selection()
        if not selection:
            return
        login_id = str(selection[0])
        user = self.services.user_service.get_user_by_login(login_id)
        if user is None:
            return
        self.user_selection_var.set(login_id)
        self.user_login_var.set(str(user["login_id"]))
        self.user_role_var.set(str(user["role"]))
        self.user_display_name_var.set(str(user["display_name"]))
        self.user_location_var.set(str(user["deployed_location"]))
        self.user_phone_var.set(str(user["phone"]))
        parent_login_id = ""
        if user.get("parent_user_id"):
            parent = self.services.user_service.get_user(int(user["parent_user_id"]))
            parent_login_id = str(parent["login_id"]) if parent else ""
        self.user_parent_var.set(parent_login_id)
        self.refresh_parent_choices()
        self.user_active_var.set(bool(user["active_flag"]))
        self.user_password_var.set("")
        self.schedule_state_save()

    def refresh_parent_choices(self) -> None:
        if self.current_user is None or not hasattr(self, "user_parent_combo"):
            return

        selected_role = self.user_role_var.get().strip().upper()
        allowed_parent_roles = [
            parent_role
            for parent_role, child_roles in DIRECT_CHILD_ROLES.items()
            if selected_role in child_roles
        ]
        allowed_parents = [
            user
            for user in getattr(self, "visible_users", [])
            if str(user["role"]) in allowed_parent_roles
        ]
        parent_values = [
            f"{user['login_id']} | {user['role']} | {user['display_name']}"
            for user in allowed_parents
        ]
        self.user_parent_combo["values"] = parent_values

        current_parent_login = self.user_parent_var.get().strip().split(" | ", 1)[0]
        if current_parent_login and current_parent_login in {
            str(user["login_id"]) for user in allowed_parents
        }:
            selected_parent = next(user for user in allowed_parents if str(user["login_id"]) == current_parent_login)
            self.user_parent_var.set(f"{selected_parent['login_id']} | {selected_parent['role']} | {selected_parent['display_name']}")
        elif parent_values:
            preferred_login = str(self.current_user["login_id"])
            preferred = next(
                (
                    f"{user['login_id']} | {user['role']} | {user['display_name']}"
                    for user in allowed_parents
                    if str(user["login_id"]) == preferred_login
                ),
                parent_values[0],
            )
            self.user_parent_var.set(preferred)
        else:
            self.user_parent_var.set("")

        if allowed_parents:
            allowed_parent_logins = ", ".join(str(user["login_id"]) for user in allowed_parents[:4])
            suffix = "..." if len(allowed_parents) > 4 else ""
            self.user_parent_hint_var.set(
                f"Allowed parents for {selected_role or 'selected role'}: {allowed_parent_logins}{suffix}"
            )
        else:
            self.user_parent_hint_var.set(
                f"No valid parent found for role {selected_role or '-'} in your visible scope."
            )

    def create_user(self) -> None:
        if self.current_user is None:
            return
        parent_login_id = self.user_parent_var.get().strip().split(" | ", 1)[0]
        try:
            created = self.services.user_service.create_user(
                self.current_user,
                login_id=self.user_login_var.get(),
                role=self.user_role_var.get(),
                password=self.user_password_var.get(),
                display_name=self.user_display_name_var.get(),
                deployed_location=self.user_location_var.get(),
                phone=self.user_phone_var.get(),
                parent_login_id=parent_login_id,
                active_flag=self.user_active_var.get(),
            )
            self.user_selection_var.set(str(created["login_id"]))
            self.refresh_dashboard_data()
            self.set_status(f"Created user {created['login_id']}.")
        except Exception as exc:
            self.logger.exception("Failed to create user")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Create User", str(exc))

    def update_user(self) -> None:
        if self.current_user is None:
            return
        target_login_id = self.user_selection_var.get().strip() or self.user_login_var.get().strip()
        parent_login_id = self.user_parent_var.get().strip().split(" | ", 1)[0]
        if not target_login_id:
            messagebox.showinfo("Update User", "Select a user first.")
            return
        try:
            updated = self.services.user_service.update_user(
                self.current_user,
                target_login_id=target_login_id,
                display_name=self.user_display_name_var.get(),
                deployed_location=self.user_location_var.get(),
                phone=self.user_phone_var.get(),
                parent_login_id=parent_login_id,
                active_flag=self.user_active_var.get(),
            )
            self.user_selection_var.set(str(updated["login_id"]))
            self.refresh_dashboard_data()
            self.set_status(f"Updated user {updated['login_id']}.")
        except Exception as exc:
            self.logger.exception("Failed to update user")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Update User", str(exc))

    def reset_user_password(self) -> None:
        if self.current_user is None:
            return
        target_login_id = self.user_selection_var.get().strip() or self.user_login_var.get().strip()
        if not target_login_id:
            messagebox.showinfo("Reset Password", "Select a user first.")
            return
        if not self.user_password_var.get():
            messagebox.showinfo("Reset Password", "Enter the new password in the password field.")
            return
        try:
            self.services.user_service.reset_password(
                self.current_user,
                target_login_id=target_login_id,
                new_password=self.user_password_var.get(),
                force_reset=True,
            )
            self.user_password_var.set("")
            self.set_status(f"Password reset for {target_login_id}.")
        except Exception as exc:
            self.logger.exception("Failed to reset password")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Reset Password", str(exc))

    def save_source_config(self) -> None:
        if self.current_user is None:
            return
        try:
            self.services.source_sync_service.update_source_config(
                self.current_user,
                source_mode=self.source_mode_var.get(),
                local_path=self.source_local_path_var.get(),
                remote_url=self.source_remote_url_var.get(),
            )
            self.refresh_source_tab()
            self.set_status("Credential source configuration saved.")
        except Exception as exc:
            self.logger.exception("Failed to save source config")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Credential Source", str(exc))

    def preview_source_import(self) -> None:
        if self.current_user is None:
            return
        try:
            preview = self.services.source_sync_service.preview_source(
                self.current_user,
                source_mode=self.source_mode_var.get(),
                local_path=self.source_local_path_var.get(),
                remote_url=self.source_remote_url_var.get(),
            )
            self.current_source_preview = preview
            self.source_preview_tree.delete(*self.source_preview_tree.get_children())
            for row in preview["rows"]:
                self.source_preview_tree.insert(
                    "",
                    END,
                    values=(
                        row["row_number"],
                        row.get("login_id", ""),
                        row.get("role", ""),
                        row.get("action", ""),
                        "Yes" if row.get("accepted") else "No",
                        "; ".join(row.get("errors", [])),
                    ),
                )
            self.source_checksum_var.set(f"Checksum: {preview['checksum']}")
            self.set_status(
                f"Preview ready. Accepted {preview['accepted_row_count']}, rejected {preview['rejected_row_count']}."
            )
        except Exception as exc:
            self.logger.exception("Failed to preview source import")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Credential Source Preview", str(exc))

    def commit_source_import(self) -> None:
        if self.current_user is None:
            return
        if self.current_source_preview is None:
            self.preview_source_import()
            if self.current_source_preview is None:
                return
        try:
            result = self.services.source_sync_service.commit_preview(self.current_user, self.current_source_preview)
            self.current_source_preview = None
            self.refresh_dashboard_data()
            self.set_status(
                f"Credential sync committed. Accepted {result['accepted_row_count']}, rejected {result['rejected_row_count']}."
            )
        except Exception as exc:
            self.logger.exception("Failed to commit source import")
            self.session_manager.record_error(str(exc))
            self.set_status(str(exc), error=True)
            messagebox.showerror("Credential Source Sync", str(exc))

    def logout(self) -> None:
        self.current_user = None
        self.current_record_public_id = ""
        self.login_password_var.set("")
        self.login_show_password_var.set(False)
        self.show_login_view()
        self.set_status("Logged out.")

    def set_status(self, message: str, error: bool = False) -> None:
        self.status_message_var.set(message)

    def build_shutdown_session_state(self) -> dict[str, Any]:
        geometry = self.session_state.get("window_geometry", "")
        if self.root.state() not in {"zoomed", "withdrawn"}:
            geometry = self.root.winfo_geometry()
        return {
            "window_geometry": geometry,
            "window_state": self.root.state(),
            "last_login_id": self.login_id_var.get() or self.session_state.get("last_login_id", ""),
            "selected_record_public_id": self.current_record_public_id,
            "selected_candidate_login_id": self.candidate_selection_var.get(),
            "selected_user_login_id": self.user_selection_var.get(),
            "current_view": self.current_view,
            "last_opened_at": self.session_state.get("last_opened_at", ""),
            "record_form": {
                "title_display": self.record_title_var.get(),
                "application_number": self.record_application_var.get(),
                "name": self.record_name_var.get(),
                "phone_number": self.record_phone_var.get(),
                "status": self.record_status_var.get(),
                "short_note": self.record_short_note.get("1.0", END).strip() if hasattr(self, "record_short_note") else "",
            },
        }

    def schedule_state_save(self) -> None:
        if self.pending_state_save_job:
            self.root.after_cancel(self.pending_state_save_job)
        self.pending_state_save_job = self.root.after(250, self.persist_session_state)

    def persist_session_state(self) -> None:
        self.pending_state_save_job = None
        try:
            state = self.build_shutdown_session_state()
            self.session_state = state
            self.session_manager.save_session_state(state)
        except Exception:
            self.logger.exception("Failed to persist session state")

    def on_close(self) -> None:
        try:
            self.session_manager.mark_clean_shutdown(self.build_shutdown_session_state())
        except Exception:
            self.logger.exception("Failed during clean shutdown")
        finally:
            self.root.destroy()

    def open_data_folder(self) -> None:
        try:
            os.startfile(str(self.data_dir))
        except Exception as exc:
            self.logger.exception("Failed to open data folder")
            messagebox.showerror("Open Data Folder", str(exc))
