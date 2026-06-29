"""Desktop GUI for smd-nxt-agent.

A thin Tkinter front end over `pipeline.run`. It never makes extraction or
mapping decisions itself - it only collects inputs (API key, folders, model
choice) and displays the same parts.json/parts.csv/review_queue.json the CLI
produces.
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

from smd_nxt_agent.extract import ALLOWED_MODELS, DEFAULT_MODEL

ENV_FILE = Path(".env")


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


class App(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        master.title("SMD NXT Agent")
        master.geometry("640x520")
        self.pack(fill="both", expand=True)

        self._result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build_setup_section()
        self._build_run_section()
        self._build_results_section()

        self.api_key_var.set(_load_saved_api_key())

    # -- Setup -----------------------------------------------------------
    def _build_setup_section(self) -> None:
        box = ttk.LabelFrame(self, text="1. Setup", padding=10)
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
    def _build_run_section(self) -> None:
        box = ttk.LabelFrame(self, text="2. Run", padding=10)
        box.pack(fill="x", pady=(0, 10))

        self.mode_var = tk.StringVar(value="folder")
        mode_row = ttk.Frame(box)
        mode_row.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Radiobutton(
            mode_row, text="Whole folder of datasheets", variable=self.mode_var,
            value="folder", command=self._on_mode_change,
        ).pack(side="left")
        ttk.Radiobutton(
            mode_row, text="One part number (single PDF)", variable=self.mode_var,
            value="single", command=self._on_mode_change,
        ).pack(side="left", padx=(12, 0))

        self.part_number_label = ttk.Label(box, text="Part number:")
        self.part_number_var = tk.StringVar()
        self.part_number_entry = ttk.Entry(box, textvariable=self.part_number_var, width=50)

        self.input_label = ttk.Label(box, text="Datasheets folder:")
        self.input_var = tk.StringVar(value=str(Path("examples").resolve()))
        self.input_entry = ttk.Entry(box, textvariable=self.input_var, width=50)
        self.input_browse = ttk.Button(box, text="Browse...", command=self._pick_input)

        self.input_label.grid(row=1, column=0, sticky="w")
        self.input_entry.grid(row=1, column=1, sticky="we", padx=6)
        self.input_browse.grid(row=1, column=2)

        ttk.Label(box, text="Output folder:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.output_var = tk.StringVar(value=str(Path("out").resolve()))
        ttk.Entry(box, textvariable=self.output_var, width=50).grid(
            row=2, column=1, sticky="we", padx=6, pady=(6, 0)
        )
        ttk.Button(box, text="Browse...", command=self._pick_output).grid(
            row=2, column=2, pady=(6, 0)
        )

        ttk.Label(box, text="Model:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(
            box, textvariable=self.model_var, values=sorted(ALLOWED_MODELS), state="readonly"
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))

        box.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(self, text="Run extraction", command=self._on_run)
        self.run_button.pack(pady=(0, 10))

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

    def _on_mode_change(self) -> None:
        if self.mode_var.get() == "single":
            self.input_label.config(text="Datasheet PDF:")
            self.input_browse.config(command=self._pick_single_pdf)
            self.part_number_label.grid(row=1, column=0, sticky="w", pady=(0, 6))
            self.part_number_entry.grid(row=1, column=1, sticky="we", padx=6, pady=(0, 6))
            self.input_label.grid(row=2, column=0, sticky="w")
            self.input_entry.grid(row=2, column=1, sticky="we", padx=6)
            self.input_browse.grid(row=2, column=2)
        else:
            self.input_label.config(text="Datasheets folder:")
            self.input_browse.config(command=self._pick_input)
            self.part_number_label.grid_forget()
            self.part_number_entry.grid_forget()
            self.input_label.grid(row=1, column=0, sticky="w")
            self.input_entry.grid(row=1, column=1, sticky="we", padx=6)
            self.input_browse.grid(row=1, column=2)

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="Choose datasheets folder")
        if path:
            self.input_var.set(path)

    def _pick_single_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose this part's datasheet PDF", filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            self.input_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_var.set(path)

    def _on_run(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Missing key", "Enter and save your Gemini API key first.")
            return

        single_mode = self.mode_var.get() == "single"
        output_dir = Path(self.output_var.get())

        if single_mode:
            part_number = self.part_number_var.get().strip()
            if not part_number:
                messagebox.showwarning("Missing part number", "Enter the part number first.")
                return
            pdf_path = Path(self.input_var.get())
            if not pdf_path.is_file():
                messagebox.showerror("File not found", f"No such file:\n{pdf_path}")
                return
        else:
            input_dir = Path(self.input_var.get())
            if not input_dir.is_dir():
                messagebox.showerror("Folder not found", f"No such folder:\n{input_dir}")
                return

        os.environ["GEMINI_API_KEY"] = key
        self.run_button.config(state="disabled")
        self.status_var.set("Running...")
        self.results_text.delete("1.0", "end")
        self.progress.start(12)

        model = self.model_var.get()
        if single_mode:
            thread = threading.Thread(
                target=self._run_pipeline_single,
                args=(pdf_path, output_dir, model, self.part_number_var.get().strip()),
                daemon=True,
            )
        else:
            thread = threading.Thread(
                target=self._run_pipeline, args=(input_dir, output_dir, model), daemon=True
            )
        thread.start()
        self.master.after(200, self._poll_queue)

    def _run_pipeline(self, input_dir: Path, output_dir: Path, model: str) -> None:
        try:
            from smd_nxt_agent.pipeline import run

            records = run(input_dir, output_dir, model=model, config_dir=Path("config"))
            self._result_queue.put(("done", (records, output_dir)))
        except Exception as exc:  # noqa: BLE001
            self._result_queue.put(("error", str(exc)))

    def _run_pipeline_single(
        self, pdf_path: Path, output_dir: Path, model: str, part_number: str
    ) -> None:
        try:
            from smd_nxt_agent.pipeline import run_single

            records = run_single(pdf_path, output_dir, model=model, config_dir=Path("config"))
            extracted = records[0].spec.part_number
            if extracted and extracted.strip().lower() != part_number.strip().lower():
                self._result_queue.put(
                    (
                        "warn_part_number",
                        f"You entered '{part_number}' but the datasheet shows "
                        f"'{extracted}'. Double-check this is the right file.",
                    )
                )
            self._result_queue.put(("done", (records, output_dir)))
        except Exception as exc:  # noqa: BLE001
            self._result_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.master.after(200, self._poll_queue)
            return

        if kind == "warn_part_number":
            messagebox.showwarning("Part number mismatch", str(payload))
            self.master.after(200, self._poll_queue)
            return

        self.progress.stop()
        self.run_button.config(state="normal")

        if kind == "error":
            self.status_var.set("Failed.")
            messagebox.showerror("Extraction failed", str(payload))
            return

        records, output_dir = payload
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
    def _build_results_section(self) -> None:
        box = ttk.LabelFrame(self, text="3. Results", padding=10)
        box.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Not run yet.")
        ttk.Label(box, textvariable=self.status_var).pack(anchor="w")

        self.results_text = tk.Text(box, height=14, wrap="word")
        self.results_text.pack(fill="both", expand=True, pady=(6, 6))

        btn_row = ttk.Frame(box)
        btn_row.pack(fill="x")
        ttk.Button(
            btn_row, text="Open output folder",
            command=lambda: webbrowser.open(self.output_var.get()),
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
        self.results_text.insert("1.0", "\n".join(lines) or "No PDFs found in that folder.")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
