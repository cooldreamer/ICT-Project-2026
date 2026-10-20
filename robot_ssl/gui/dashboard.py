"""Minimal Tkinter live dashboard for the robot audio-perception pipeline."""
from __future__ import annotations
import queue
import tkinter as tk
from tkinter import ttk


class Dashboard:
    def __init__(self, event_queue: queue.Queue, stop_event) -> None:
        self.events = event_queue
        self.stop_event = stop_event
        self.root = tk.Tk()
        self.root.title("Robot Sound Localisation & Attention")
        self.root.geometry("790x560")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Robot audio perception", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")

        self.status_var = tk.StringVar(value="Starting audio pipeline…")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(3, 12))

        metrics = ttk.LabelFrame(outer, text="Live signals", padding=10)
        metrics.pack(fill="x")
        self.azimuth_var = tk.StringVar(value="—")
        self.confidence_var = tk.StringVar(value="—")
        self.rms_var = tk.StringVar(value="—")
        self.wake_var = tk.StringVar(value="—")
        self.attention_var = tk.StringVar(value="—")
        self.health_var = tk.StringVar(value="—")
        for label, variable in [
            ("Estimated azimuth (0° = front, + = left)", self.azimuth_var),
            ("DoA confidence (relative score)", self.confidence_var),
            ("Input level", self.rms_var),
            ("Wake-word score / availability", self.wake_var),
            ("Attention session", self.attention_var),
            ("Performance / health", self.health_var),
        ]:
            row = ttk.Frame(metrics)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=38).pack(side="left", anchor="w")
            ttk.Label(row, textvariable=variable).pack(side="left", anchor="w")

        ttk.Label(outer, text="Latest utterances", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(12, 4))
        self.output = tk.Text(outer, height=15, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        self.root.after(100, self._poll_events)

    def _append(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _poll_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            event_type = event.get("type")
            if event_type == "status":
                self.status_var.set(event.get("message", "Ready"))
            elif event_type == "error":
                self.status_var.set("Warning: " + event.get("message", "unknown error"))
                self._append("WARNING: " + event.get("message", "unknown error"))
            elif event_type == "telemetry":
                angle = event.get("azimuth_degrees")
                self.azimuth_var.set(f"{angle:+.1f}°" if angle is not None else "unknown / insufficient signal")
                self.confidence_var.set(f"{event.get('doa_confidence', 0.0):.2f}")
                self.rms_var.set(f"{event.get('rms_dbfs', -120.0):.1f} dBFS")
                self.wake_var.set(f"{event.get('wakeword_score', 0.0):.2f} / {'enabled' if event.get('wakeword_enabled') else 'text fallback'}")
                self.attention_var.set("active" if event.get("attention_active") else "idle")
                health = event.get("health", {})
                self.health_var.set(
                    f"{health.get('frames_per_second', 0)} fps; overflows={health.get('audio_overflows', 0)}; "
                    f"dropped segments={health.get('dropped_segments', 0)}"
                )
            elif event_type == "segment":
                angle = event.get("azimuth_degrees")
                angle_text = f"{angle:+.1f}°" if angle is not None else "unknown direction"
                traits = event.get("voice_traits", {})
                self._append(
                    f"Transcript: {event.get('transcript') or '[no STT transcript]'}\n"
                    f"Direction: {angle_text} (score {event.get('doa_confidence', 0.0):.2f})\n"
                    f"Wake word: {event.get('wakeword_detected')} | Addressed robot: {event.get('addressed_robot')} "
                    f"| Attention score: {event.get('attention_score', 0.0):.2f}\n"
                    f"Language: {event.get('language') or 'unknown'} | Accent: {traits.get('accent_guess', 'unknown')}\n"
                    f"Traits: pitch={traits.get('pitch_median_hz')} Hz, centroid={traits.get('spectral_centroid_hz')} Hz"
                )
        if not self.stop_event.is_set():
            self.root.after(100, self._poll_events)

    def close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
