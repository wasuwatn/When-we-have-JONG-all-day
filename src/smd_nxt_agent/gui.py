"""Desktop GUI for smd-nxt-agent.

A thin Tkinter front end over `pipeline.run_single`. It never makes
extraction or mapping decisions itself - it collects one part number plus
its datasheet PDF, runs the pipeline, and displays the same
parts.json/parts.csv/review_queue.json the CLI produces. Anything unsafe or
ambiguous is surfaced as a modal for human confirmation. Folder/batch runs
stay on the CLI (`smd-nxt extract`).
"""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yaml

from smd_nxt_agent.extract import ALLOWED_MODELS, DEFAULT_MODEL
from smd_nxt_agent.reference_rules import load_reference

ENV_FILE = Path(".env")
CONFIG_DIR = Path("config")
MACHINE_YAML = CONFIG_DIR / "machine.yaml"


def _load_saved_api_key() -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _save_api_key(key: str) -> None:
    lines = []
    found = False
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                lines.append(f"GEMINI_API_KEY={key}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"GEMINI_API_KEY={key}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def _load_configured_heads() -> list[str]:
    if not MACHINE_YAML.exists():
        return []
    machine = yaml.safe_load(MACHINE_YAML.read_text())
    heads = machine.get("heads") if machine else None
    return list(heads) if heads else []


def _save_configured_heads(head_ids: list[str]) -> None:
    if not MACHINE_YAML.exists():
        return
    lines = MACHINE_YAML.read_text().splitlines()
    new_value = "[" + ", ".join(head_ids) + "]"
    for i, line in enumerate(lines):
        if line.strip().startswith("heads:"):
            lines[i] = f"heads: {new_value}"
            break
    MACHINE_YAML.write_text("\n".join(lines) + "\n")


class App(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        master.title("SMD NXT Agent")
        master.geometry("700x560")
        self.pack(fill="both", expand=True)

        self._result_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        analyze_tab = ttk.Frame(notebook, padding=12)
        reference_tab = ttk.Frame(notebook, padding=12)
        notebook.add(analyze_tab, text="Analyze a part")
        notebook.add(reference_tab, text="Nozzle & Vision Reference")

        self._build_setup_section(analyze_tab)
        self._build_run_section(analyze_tab)
        self._build_results_section(analyze_tab)
        self._build_reference_section(reference_tab)

        self.api_key_var.set(_load_saved_api_key())

    # -- Setup -----------------------------------------------------------
    def _build_setup_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="1. Setup", padding=10)
        box.pack(fill="x", pady=(0, 10))

        ttk.Label(box, text="Gemini API key:").grid(row=0, column=0, sticky="w")
        self.api_key_var = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.api_key_var, show="*", width=50)
        entry.grid(row=0, column=1, sticky="we", padx=6)

        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            box, text="show", variable=self.show_key_var, command=lambda: entry.config(
                show="" if self.show_key_var.get() else "*"
            )
        ).grid(row=0, column=2)

        ttk.Button(box, text="Save key", command=self._on_save_key).grid(
            row=0, column=3, padx=(6, 0)
        )
        ttk.Button(
            box, text="Get a free API key",
            command=lambda: webbrowser.open("https://aistudio.google.com/apikey"),
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))

        box.columnconfigure(1, weight=1)

    def _on_save_key(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Missing key", "Paste your Gemini API key first.")
            return
        _save_api_key(key)
        messagebox.showinfo("Saved", "API key saved to .env for next time.")

    # -- Run ---------------------------------------------------------------
    def _build_run_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="2. Analyze a part", padding=10)
        box.pack(fill="x", pady=(0, 10))

        # Step 1: part number
        ttk.Label(box, text="Part number:").grid(row=0, column=0, sticky="w")
        self.part_number_var = tk.StringVar()
        self.part_number_entry = ttk.Entry(box, textvariable=self.part_number_var, width=50)
        self.part_number_entry.grid(row=0, column=1, sticky="we", padx=6)
        ttk.Label(box, text="e.g. B57232V5103F360", foreground="gray").grid(
            row=1, column=1, sticky="w", padx=6
        )

        # Step 2: datasheet PDF
        ttk.Label(box, text="Datasheet PDF:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.input_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.input_var, width=50, state="readonly").grid(
            row=2, column=1, sticky="we", padx=6, pady=(6, 0)
        )
        ttk.Button(box, text="Browse...", command=self._pick_single_pdf).grid(
            row=2, column=2, pady=(6, 0)
        )

        # Low-prominence model choice; defaults so nothing extra is needed
        ttk.Label(box, text="Model:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(
            box, textvariable=self.model_var, values=sorted(ALLOWED_MODELS), state="readonly"
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))

        box.columnconfigure(1, weight=1)

        # Output is fixed; no picker. Auto-created by run_single().
        self.output_dir = Path("out")

        # Step 3: analyze
        self.run_button = ttk.Button(parent, text="Analyze", command=self._on_run)
        self.run_button.pack(pady=(0, 10))

        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

    def _pick_single_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose this part's datasheet PDF", filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            self.input_var.set(path)

    def _on_run(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Missing key", "Enter and save your Gemini API key first.")
            return

        part_number = self.part_number_var.get().strip()
        if not part_number:
            messagebox.showwarning("Missing part number", "Enter the part number first.")
            return

        pdf_path = Path(self.input_var.get())
        if not self.input_var.get() or not pdf_path.is_file():
            messagebox.showerror("File not found", "Choose this part's datasheet PDF first.")
            return

        os.environ["GEMINI_API_KEY"] = key
        self.run_button.config(state="disabled")
        self.status_var.set("Analyzing...")
        self.results_text.delete("1.0", "end")
        self.progress.start(12)

        model = self.model_var.get()
        thread = threading.Thread(
            target=self._run_pipeline_single,
            args=(pdf_path, self.output_dir, model, part_number),
            daemon=True,
        )
        thread.start()
        self.master.after(200, self._poll_queue)

    def _run_pipeline_single(
        self, pdf_path: Path, output_dir: Path, model: str, part_number: str
    ) -> None:
        try:
            from smd_nxt_agent.pipeline import run_single

            records = run_single(pdf_path, output_dir, model=model, config_dir=Path("config"))
            extracted = records[0].spec.part_number
            mismatch = None
            if extracted and extracted.strip().lower() != part_number.strip().lower():
                mismatch = (
                    f"You entered '{part_number}' but the datasheet shows "
                    f"'{extracted}'.\n\nUse this file anyway?"
                )
            # Single terminal event so the mismatch confirm can cancel cleanly.
            self._result_queue.put(("done", (records, output_dir, mismatch)))
        except Exception as exc:  # noqa: BLE001
            self._result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.master.after(200, self._poll_queue)
            return

        self.progress.stop()
        self.run_button.config(state="normal")

        if kind == "error":
            self.status_var.set("Failed.")
            messagebox.showerror("Extraction failed", str(payload))
            return

        records, output_dir, mismatch = payload
        if mismatch and not messagebox.askyesno("Part number mismatch", mismatch):
            self.status_var.set("Cancelled - part number mismatch.")
            return

        ok_count = sum(1 for r in records if r.validation.ok)
        review_count = len(records) - ok_count
        self.status_var.set(
            f"Done: {len(records)} part(s) -> {ok_count} OK, {review_count} need review."
        )
        self._show_results(records, output_dir)

        review_records = [r for r in records if r.validation.needs_review]
        if review_records:
            self._show_review_modal(review_records, output_dir)

    # -- Results -------------------------------------------------------
    def _build_results_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="3. Results", padding=10)
        box.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Not run yet.")
        ttk.Label(box, textvariable=self.status_var).pack(anchor="w")

        self.results_text = tk.Text(box, height=14, wrap="word")
        self.results_text.pack(fill="both", expand=True, pady=(6, 6))

        btn_row = ttk.Frame(box)
        btn_row.pack(fill="x")
        ttk.Button(
            btn_row, text="Open output folder",
            command=lambda: webbrowser.open(str(self.output_dir.resolve())),
        ).pack(side="left")

    def _show_review_modal(self, review_records: list, output_dir: Path) -> None:
        modal = tk.Toplevel(self.master)
        modal.title("Human review required")
        modal.geometry("560x480")
        modal.transient(self.master)
        modal.grab_set()

        ttk.Label(
            modal,
            text=(
                f"{len(review_records)} part(s) need a human check before being used "
                "on the machine. A wrong height can crash a nozzle; a wrong polarity "
                "reverses the part on the board."
            ),
            wraplength=520, justify="left",
        ).pack(fill="x", padx=12, pady=(12, 6))

        canvas_frame = ttk.Frame(modal)
        canvas_frame.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(canvas_frame, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        rows_frame = ttk.Frame(canvas)
        rows_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        decisions: dict[str, str] = {}

        for record in review_records:
            row = ttk.LabelFrame(rows_frame, text=record.source_file, padding=8)
            row.pack(fill="x", pady=4, padx=2)

            details = (
                f"Package: {record.spec.package_name}\n"
                f"Height: {record.spec.body_height_mm} mm "
                f"(confidence: {record.spec.height_confidence})\n"
                f"Polarized: {record.spec.is_polarized} "
                f"(confidence: {record.spec.polarity_confidence})\n"
                f"Nozzle: {record.mapping.nozzle}  Vision: {record.mapping.vision_type}\n"
                f"Warnings: {', '.join(record.validation.warnings) or 'none'}\n"
                f"Notes: {record.spec.source_notes}"
            )
            ttk.Label(row, text=details, wraplength=480, justify="left").pack(
                anchor="w", fill="x"
            )

            status_var = tk.StringVar(value="Pending")
            ttk.Label(row, textvariable=status_var).pack(anchor="w", pady=(4, 0))

            btn_row = ttk.Frame(row)
            btn_row.pack(anchor="w", pady=(4, 0))

            def make_handler(key: str, var: tk.StringVar, label: str) -> object:
                def handler() -> None:
                    decisions[key] = label
                    var.set(f"Marked: {label}")
                return handler

            ttk.Button(
                btn_row, text="Confirm OK to use",
                command=make_handler(record.source_file, status_var, "confirmed"),
            ).pack(side="left")
            ttk.Button(
                btn_row, text="Reject - do not use",
                command=make_handler(record.source_file, status_var, "rejected"),
            ).pack(side="left", padx=(6, 0))

        def on_close() -> None:
            (output_dir / "human_review_decisions.json").write_text(
                json.dumps(decisions, indent=2)
            )
            modal.destroy()

        ttk.Button(modal, text="Save decisions and close", command=on_close).pack(pady=10)
        modal.protocol("WM_DELETE_WINDOW", on_close)

    def _show_results(self, records: list, output_dir: Path) -> None:
        lines = []
        for r in records:
            flag = "OK" if r.validation.ok else "REVIEW"
            lines.append(
                f"[{flag}] {r.source_file}: {r.spec.package_name} -> "
                f"nozzle={r.mapping.nozzle}, vision={r.mapping.vision_type}"
            )
        review_path = output_dir / "review_queue.json"
        if review_path.exists():
            review = json.loads(review_path.read_text())
            if review:
                lines.append("")
                lines.append(f"⚠ {len(review)} part(s) need human review before machine use.")
        self.results_text.insert("1.0", "\n".join(lines) or "No result.")

    # -- Reference tables ------------------------------------------------
    def _build_reference_section(self, parent: ttk.Frame) -> None:
        self._reference = load_reference(CONFIG_DIR)
        unverified = not (
            self._reference.nozzle_compat_verified and self._reference.vision_table_verified
        )

        if unverified:
            ttk.Label(
                parent,
                text=(
                    "⚠ This data was transcribed from a screenshot and is NOT yet verified "
                    "against the official Fuji guide. Any nozzle/vision choice derived from "
                    "it is forced into needs_review until verified: true is set in "
                    "config/reference/*.yaml."
                ),
                foreground="#a05a00", wraplength=620, justify="left",
            ).pack(fill="x", pady=(0, 10))

        head_row = ttk.Frame(parent)
        head_row.pack(fill="x", pady=(0, 10))
        ttk.Label(
            head_row,
            text="Machine head(s) mounted (checked = used for nozzle lookups, in order):",
        ).pack(side="left")
        configured = set(_load_configured_heads())
        self._head_vars: dict[str, tk.BooleanVar] = {}
        for head_id in self._reference.available_heads():
            var = tk.BooleanVar(value=head_id in configured)
            self._head_vars[head_id] = var
            ttk.Checkbutton(
                head_row, text=head_id, variable=var, command=self._on_head_selected
            ).pack(side="left", padx=6)

        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        nozzle_tab = ttk.Frame(notebook, padding=6)
        vision_tab = ttk.Frame(notebook, padding=6)
        notebook.add(nozzle_tab, text="Nozzle compatibility")
        notebook.add(vision_tab, text="Vision types")

        self._build_nozzle_table(nozzle_tab)
        self._build_vision_table(vision_tab)

    def _on_head_selected(self) -> None:
        checked = [
            head_id
            for head_id in self._reference.available_heads()
            if self._head_vars[head_id].get()
        ]
        _save_configured_heads(checked)

    def _build_nozzle_table(self, parent: ttk.Frame) -> None:
        columns = ("category", "diameter_mm", *self._reference.available_heads())
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=14)
        tree.heading("category", text="Package")
        tree.heading("diameter_mm", text="Diameter (mm)")
        for head_id in self._reference.available_heads():
            tree.heading(head_id, text=head_id)
            tree.column(head_id, width=100, anchor="center")
        tree.column("category", width=100)
        tree.column("diameter_mm", width=90, anchor="center")

        categories = (
            self._reference.nozzle_compat.get("package_categories", [])
            if self._reference.nozzle_compat
            else []
        )
        heads = (
            self._reference.nozzle_compat.get("heads", {}) if self._reference.nozzle_compat else {}
        )
        for category in categories:
            row = [category["id"], category.get("diameter_mm") or "-"]
            for head_id in self._reference.available_heads():
                row.append(heads.get(head_id, {}).get(category["id"], "-"))
            tree.insert("", "end", values=row)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_vision_table(self, parent: ttk.Frame) -> None:
        columns = ("part_type", "vision_type", "remarks")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=14)
        tree.heading("part_type", text="Part type")
        tree.heading("vision_type", text="Vision type")
        tree.heading("remarks", text="Remarks")
        tree.column("part_type", width=200)
        tree.column("vision_type", width=90, anchor="center")
        tree.column("remarks", width=300)

        entries = (
            self._reference.vision_table.get("entries", []) if self._reference.vision_table else []
        )
        for entry in entries:
            tree.insert(
                "", "end",
                values=(entry["part_type_id"], entry["vision_type"], entry.get("remarks", "")),
            )

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
