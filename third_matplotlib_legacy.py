from __future__ import annotations

import os
from math import ceil
from pathlib import Path
from typing import Dict, Tuple


def configure_tcl_tk_paths() -> None:
    """Помогает tkinter найти Tcl/Tk в окружениях, где Python установлен неполно."""
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    candidates = (
        Path(r"C:\Program Files\Git\mingw64\lib"),
        Path(r"C:\Program Files (x86)\Git\mingw64\lib"),
    )

    for root in candidates:
        tcl_path = root / "tcl8.6"
        tk_path = root / "tk8.6"
        if (tcl_path / "init.tcl").exists() and (tk_path / "tk.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(tcl_path))
            os.environ.setdefault("TK_LIBRARY", str(tk_path))
            return


configure_tcl_tk_paths()

import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.image import imread

from orbiter.dynamics import (
    DEFAULT_RADIUS,
    ORBIT_PRESETS,
    R_EARTH,
    OrbitPreset,
    SimulationConfig,
    orbital_elements_to_state,
    orbital_summary,
    simulate_orbit,
)

# ========================
# 1. МЕТАДАННЫЕ И ПОЛЯ UI
# ========================
EARTH_TEXTURE_PATH = Path(__file__).resolve().parent / "assets" / "earth_blue_marble_2048.jpg"
EARTH_TEXTURE_LONGITUDE_POINTS = 256
EARTH_TEXTURE_LATITUDE_POINTS = 128
EARTH_TEXTURE_ALPHA = 0.52
CUSTOM_PRESET_NAME = "Пользовательская"
ORBIT_ELEMENT_FIELDS = (
    ("semi_major_axis", "a, км", DEFAULT_RADIUS),
    ("eccentricity", "e", 0.0),
    ("inclination_deg", "i, град", 7.5),
    ("raan_deg", "Omega, град", 0.0),
    ("arg_perigee_deg", "omega, град", 0.0),
    ("true_anomaly_deg", "nu, град", 0.0),
)


def load_earth_texture() -> np.ndarray:
    """Загружает текстуру глобуса и приводит цвета к диапазону 0..1."""
    texture = imread(EARTH_TEXTURE_PATH)
    if texture.dtype.kind in ("u", "i"):
        texture = texture.astype(float) / 255.0
    return texture[:, :, :3]

# ========================
# 2. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС
# ========================
class OrbitApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("3D визуализация движения спутника")
        self.root.geometry("1220x820")
        self.root.minsize(900, 560)

        self.entries: Dict[str, tk.Entry] = {}
        self.orbit_entries: Dict[str, tk.Entry] = {}
        self.speed_entry = None
        self.controls_canvas = None
        self.controls_window = None
        self.earth_texture = None
        self.animation = None
        self.trail_line = None
        self.trail_halo = None
        self.satellite = None
        self.satellite_halo = None
        self.time_label = None
        self.current_x = None
        self.current_y = None
        self.current_z = None
        self.current_speeds = None
        self.current_times = None
        self.preset_var = tk.StringVar(value=CUSTOM_PRESET_NAME)
        self.preset_info_text = tk.StringVar(
            value="Выберите готовую орбиту или задайте координаты и скорости вручную."
        )
        self.status_text = tk.StringVar(value="")

        if EARTH_TEXTURE_PATH.exists():
            try:
                self.earth_texture = load_earth_texture()
            except OSError:
                self.earth_texture = None

        self._build_layout()
        self.run_simulation()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        controls = self._build_scrollable_controls()

        plot_area = ttk.Frame(self.root, padding=(0, 12, 12, 12))
        plot_area.grid(row=0, column=1, sticky="nsew")
        plot_area.columnconfigure(0, weight=1)
        plot_area.rowconfigure(0, weight=1)

        self._build_inputs(controls)

        self.figure = Figure(figsize=(8, 7), dpi=100)
        self.ax = self.figure.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_area)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        toolbar_frame = ttk.Frame(plot_area)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.grid(row=0, column=0, sticky="w")

    def _build_scrollable_controls(self) -> ttk.Frame:
        controls_shell = ttk.Frame(self.root, padding=(12, 12, 6, 12))
        controls_shell.grid(row=0, column=0, sticky="ns")
        controls_shell.rowconfigure(0, weight=1)
        controls_shell.columnconfigure(0, weight=1)

        self.controls_canvas = tk.Canvas(
            controls_shell,
            width=310,
            highlightthickness=0,
            borderwidth=0,
        )
        controls_scrollbar = ttk.Scrollbar(
            controls_shell,
            orient="vertical",
            command=self.controls_canvas.yview,
        )
        controls = ttk.Frame(self.controls_canvas)

        self.controls_window = self.controls_canvas.create_window(
            (0, 0),
            window=controls,
            anchor="nw",
        )
        self.controls_canvas.configure(yscrollcommand=controls_scrollbar.set)

        self.controls_canvas.grid(row=0, column=0, sticky="ns")
        controls_scrollbar.grid(row=0, column=1, sticky="ns")

        controls.bind("<Configure>", self._update_controls_scrollregion)
        self.controls_canvas.bind("<Configure>", self._resize_controls_window)
        self.controls_canvas.bind("<Enter>", self._bind_controls_mousewheel)
        self.controls_canvas.bind("<Leave>", self._unbind_controls_mousewheel)

        return controls

    def _update_controls_scrollregion(self, _event: object = None) -> None:
        if self.controls_canvas is not None:
            self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _resize_controls_window(self, event: tk.Event) -> None:
        if self.controls_canvas is not None and self.controls_window is not None:
            self.controls_canvas.itemconfigure(self.controls_window, width=event.width)

    def _bind_controls_mousewheel(self, _event: object = None) -> None:
        if self.controls_canvas is None:
            return
        self.controls_canvas.bind_all("<MouseWheel>", self._scroll_controls_with_mousewheel)
        self.controls_canvas.bind_all("<Button-4>", self._scroll_controls_with_mousewheel)
        self.controls_canvas.bind_all("<Button-5>", self._scroll_controls_with_mousewheel)

    def _unbind_controls_mousewheel(self, _event: object = None) -> None:
        if self.controls_canvas is None:
            return
        self.controls_canvas.unbind_all("<MouseWheel>")
        self.controls_canvas.unbind_all("<Button-4>")
        self.controls_canvas.unbind_all("<Button-5>")

    def _scroll_controls_with_mousewheel(self, event: tk.Event) -> None:
        if self.controls_canvas is None:
            return

        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            direction = -1 if event.delta > 0 else 1

        self.controls_canvas.yview_scroll(direction, "units")

    def _build_inputs(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Начальные условия", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        preset_frame = ttk.LabelFrame(parent, text="Готовая орбита", padding=10)
        preset_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        orbit_params = ttk.LabelFrame(parent, text="Параметры орбиты", padding=10)
        orbit_params.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        coordinates = ttk.LabelFrame(parent, text="Координаты, км", padding=10)
        coordinates.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        velocities = ttk.LabelFrame(parent, text="Скорости, км/с", padding=10)
        velocities.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        calculation = ttk.LabelFrame(parent, text="Расчет", padding=10)
        calculation.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        self._build_preset_selector(preset_frame)
        self._build_orbit_inputs(orbit_params)

        self._add_entry(coordinates, "x0", "X0", SimulationConfig.x0, 0)
        self._add_entry(coordinates, "y0", "Y0", SimulationConfig.y0, 1)
        self._add_entry(coordinates, "z0", "Z0", SimulationConfig.z0, 2)

        self._add_entry(velocities, "vx0", "Vx0", SimulationConfig.vx0, 0)
        self._add_entry(velocities, "vy0", "Vy0", SimulationConfig.vy0, 1)
        self._add_entry(velocities, "vz0", "Vz0", SimulationConfig.vz0, 2)
        self._add_speed_entry(velocities, 3)

        self._add_entry(calculation, "dt", "Шаг dt, с", SimulationConfig.dt, 0)
        self._add_entry(
            calculation,
            "duration_min",
            "Длительность, мин",
            SimulationConfig.duration_min,
            1,
        )

        button_row = ttk.Frame(parent)
        button_row.grid(row=6, column=0, sticky="ew", pady=(4, 12))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=1)

        ttk.Button(button_row, text="Построить", command=self.run_simulation).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(button_row, text="Стоп", command=self.stop_simulation).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(button_row, text="Сброс", command=self.reset_to_start).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

        summary = ttk.LabelFrame(parent, text="Сводка", padding=10)
        summary.grid(row=7, column=0, sticky="nsew")
        parent.rowconfigure(7, weight=1)

        ttk.Label(summary, textvariable=self.status_text, justify="left", wraplength=260).grid(
            row=0, column=0, sticky="nw"
        )

    def _build_preset_selector(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Орбита").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.preset_combo = ttk.Combobox(
            parent,
            textvariable=self.preset_var,
            values=(CUSTOM_PRESET_NAME, *ORBIT_PRESETS.keys()),
            state="readonly",
            width=26,
        )
        self.preset_combo.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.preset_combo.bind("<<ComboboxSelected>>", self.apply_selected_preset)
        parent.columnconfigure(0, weight=1)

        ttk.Label(
            parent,
            textvariable=self.preset_info_text,
            justify="left",
            wraplength=260,
        ).grid(row=2, column=0, sticky="w")

    def _build_orbit_inputs(self, parent: ttk.LabelFrame) -> None:
        for index, (key, label, value) in enumerate(ORBIT_ELEMENT_FIELDS):
            row = index // 2
            column = (index % 2) * 2
            ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=3)

            entry = ttk.Entry(parent, width=11)
            entry.insert(0, f"{value:.6g}")
            entry.grid(row=row, column=column + 1, sticky="ew", padx=(6, 10), pady=3)
            self.orbit_entries[key] = entry

        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        ttk.Button(
            parent,
            text="Применить параметры орбиты",
            command=self.apply_orbital_parameters,
        ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _add_entry(
        self,
        parent: ttk.LabelFrame,
        key: str,
        label: str,
        value: float,
        row: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=14)
        entry.insert(0, f"{value:.6g}")
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        parent.columnconfigure(1, weight=1)
        self.entries[key] = entry
        if key in ("vx0", "vy0", "vz0"):
            entry.bind("<KeyRelease>", self.update_speed_from_velocity_fields)
            entry.bind("<FocusOut>", self.update_speed_from_velocity_fields)

    def _add_speed_entry(self, parent: ttk.LabelFrame, row: int) -> None:
        initial_speed = np.linalg.norm(
            [SimulationConfig.vx0, SimulationConfig.vy0, SimulationConfig.vz0]
        )
        ttk.Label(parent, text="V, км/с").grid(row=row, column=0, sticky="w", pady=3)
        self.speed_entry = ttk.Entry(parent, width=14)
        self.speed_entry.insert(0, f"{initial_speed:.6g}")
        self.speed_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Button(
            parent,
            text="Применить V",
            command=self.apply_speed_to_velocity,
        ).grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _set_entry_value(self, key: str, value: float) -> None:
        entry = self.entries[key]
        entry.delete(0, tk.END)
        entry.insert(0, f"{value:.8g}")

    def _set_speed_value(self, value: float) -> None:
        if self.speed_entry is None:
            return
        self.speed_entry.delete(0, tk.END)
        self.speed_entry.insert(0, f"{value:.8g}")

    def _set_orbit_entry_value(self, key: str, value: float) -> None:
        entry = self.orbit_entries[key]
        entry.delete(0, tk.END)
        entry.insert(0, f"{value:.8g}")

    def _fill_config_fields(self, config: SimulationConfig) -> None:
        for key in self.entries:
            self._set_entry_value(key, getattr(config, key))
        self._set_speed_value(np.linalg.norm(config.initial_state[3:]))

    def _fill_orbit_fields(self, preset: OrbitPreset) -> None:
        for key, _label, _value in ORBIT_ELEMENT_FIELDS:
            self._set_orbit_entry_value(key, getattr(preset, key))

    def read_orbit_elements(self) -> Dict[str, float]:
        values = {}
        labels = {key: label for key, label, _value in ORBIT_ELEMENT_FIELDS}
        for key, entry in self.orbit_entries.items():
            raw_value = entry.get().strip().replace(",", ".")
            try:
                values[key] = float(raw_value)
            except ValueError as exc:
                raise ValueError(f"Поле {labels[key]}: введите число.") from exc

        return values

    def read_velocity_vector(self) -> np.ndarray:
        return np.array(
            [
                float(self.entries["vx0"].get().strip().replace(",", ".")),
                float(self.entries["vy0"].get().strip().replace(",", ".")),
                float(self.entries["vz0"].get().strip().replace(",", ".")),
            ],
            dtype=float,
        )

    def update_speed_from_velocity_fields(self, _event: object = None) -> None:
        try:
            velocity = self.read_velocity_vector()
        except ValueError:
            return
        self._set_speed_value(np.linalg.norm(velocity))

    def apply_speed_to_velocity(self) -> None:
        try:
            if self.speed_entry is None:
                return
            speed = float(self.speed_entry.get().strip().replace(",", "."))
            velocity = self.read_velocity_vector()
        except ValueError:
            messagebox.showerror("Ошибка скорости", "Введите числовые значения скорости.")
            return

        if speed < 0:
            messagebox.showerror(
                "Ошибка скорости",
                "Полная скорость V не может быть отрицательной.",
            )
            return

        current_speed = np.linalg.norm(velocity)
        if current_speed <= 1e-12:
            messagebox.showerror(
                "Ошибка скорости",
                "Нельзя применить V: направление скорости нулевое. "
                "Сначала задайте Vx, Vy или Vz.",
            )
            return

        scaled_velocity = velocity * (speed / current_speed)
        for key, value in zip(("vx0", "vy0", "vz0"), scaled_velocity):
            self._set_entry_value(key, value)

        self.preset_var.set(CUSTOM_PRESET_NAME)
        self.preset_info_text.set("Полная скорость V применена: проекции скорости масштабированы.")
        self.run_simulation()

    def apply_orbital_parameters(self) -> None:
        try:
            elements = self.read_orbit_elements()
            state = orbital_elements_to_state(**elements)
        except ValueError as error:
            messagebox.showerror("Ошибка параметров орбиты", str(error))
            return

        for key, value in zip(("x0", "y0", "z0", "vx0", "vy0", "vz0"), state):
            self._set_entry_value(key, value)
        self._set_speed_value(np.linalg.norm(state[3:]))

        self.preset_var.set(CUSTOM_PRESET_NAME)
        self.preset_info_text.set(
            "Параметры орбиты применены: координаты и скорости пересчитаны."
        )
        self.run_simulation()

    def apply_selected_preset(self, _event: object = None) -> None:
        preset_name = self.preset_var.get()
        if preset_name == CUSTOM_PRESET_NAME:
            self.preset_info_text.set(
                "Ручной режим: можно менять координаты, скорости, шаг и длительность."
            )
            return

        preset = ORBIT_PRESETS[preset_name]
        self._fill_orbit_fields(preset)
        self._fill_config_fields(preset.to_config())
        self.preset_info_text.set(preset.summary())
        self.run_simulation()

    def stop_simulation(self) -> None:
        self._stop_animation()

    def reset_to_start(self) -> None:
        self._stop_animation()

        if self.current_x is None:
            try:
                config = self.read_config()
                history, times, stopped_by_collision = simulate_orbit(config)
            except ValueError as error:
                messagebox.showerror("Ошибка ввода", str(error))
                return
            self.status_text.set(orbital_summary(history, stopped_by_collision))
            self.draw_scene(history, times, stopped_by_collision, start_animation=False)
            return

        self._set_animation_frame(
            0,
            self.current_x,
            self.current_y,
            self.current_z,
            self.current_times,
            self.current_speeds,
        )
        self.canvas.draw_idle()

    def read_config(self) -> SimulationConfig:
        values = {}
        for key, entry in self.entries.items():
            raw_value = entry.get().strip().replace(",", ".")
            try:
                values[key] = float(raw_value)
            except ValueError as exc:
                raise ValueError(f"Поле {key}: введите число.") from exc

        config = SimulationConfig(**values)

        if config.dt <= 0:
            raise ValueError("Шаг dt должен быть больше нуля.")
        if config.duration_min <= 0:
            raise ValueError("Длительность расчета должна быть больше нуля.")

        start_radius = np.linalg.norm(config.initial_state[:3])
        if start_radius <= R_EARTH:
            raise ValueError(
                f"Начальная точка находится внутри Земли. "
                f"Радиус должен быть больше {R_EARTH:.0f} км."
            )

        return config

    def run_simulation(self) -> None:
        try:
            config = self.read_config()
            history, times, stopped_by_collision = simulate_orbit(config)
        except ValueError as error:
            messagebox.showerror("Ошибка ввода", str(error))
            return

        self.status_text.set(orbital_summary(history, stopped_by_collision))
        self.draw_scene(history, times, stopped_by_collision)

    def draw_scene(
        self,
        history: np.ndarray,
        times: np.ndarray,
        stopped_by_collision: bool,
        start_animation: bool = True,
    ) -> None:
        self._stop_animation()

        self.ax.clear()
        positions = history[:, :3]
        speeds = np.linalg.norm(history[:, 3:], axis=1)
        x, y, z = positions.T
        self.current_x = x
        self.current_y = y
        self.current_z = z
        self.current_speeds = speeds
        self.current_times = times

        self._plot_earth()
        self.ax.plot(
            x,
            y,
            z,
            color="#101820",
            linewidth=3.0,
            alpha=0.45,
            zorder=20,
            label="_nolegend_",
        )
        self.ax.plot(
            x,
            y,
            z,
            color="#f8f9fa",
            linewidth=1.35,
            alpha=0.9,
            zorder=21,
            label="Траектория",
        )
        self.trail_halo, = self.ax.plot(
            [],
            [],
            [],
            color="#111111",
            linewidth=5.0,
            alpha=0.95,
            zorder=30,
            label="_nolegend_",
        )
        self.trail_line, = self.ax.plot(
            [],
            [],
            [],
            color="#ff2d2d",
            linewidth=2.6,
            zorder=31,
            label="Пройденный путь",
        )
        self.satellite_halo, = self.ax.plot(
            [],
            [],
            [],
            marker="o",
            markersize=18,
            color="#111111",
            linestyle="None",
            zorder=40,
            label="_nolegend_",
        )
        self.satellite, = self.ax.plot(
            [],
            [],
            [],
            marker="o",
            markersize=12,
            color="#fff200",
            markeredgecolor="#111111",
            markeredgewidth=1.4,
            linestyle="None",
            zorder=41,
            label="Спутник",
        )
        self.ax.scatter([x[0]], [y[0]], [z[0]], color="#2a9d8f", s=36, label="Старт")

        if stopped_by_collision:
            self.ax.scatter(
                [x[-1]],
                [y[-1]],
                [z[-1]],
                color="#b00020",
                s=44,
                label="Пересечение Земли",
            )

        self.time_label = self.ax.text2D(
            0.02,
            0.94,
            "",
            transform=self.ax.transAxes,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.75},
        )
        self._format_axes(positions)

        frame_step = max(1, int(ceil(len(history) / 900)))
        frames = np.arange(0, len(history), frame_step)
        if frames[-1] != len(history) - 1:
            frames = np.append(frames, len(history) - 1)

        self._set_animation_frame(0, x, y, z, times, speeds)

        if start_animation:
            self.animation = FuncAnimation(
                self.figure,
                self._animate,
                frames=frames,
                fargs=(x, y, z, times, speeds),
                interval=20,
                blit=False,
                repeat=True,
            )
        self.canvas.draw_idle()

    def _stop_animation(self) -> None:
        if self.animation is not None:
            self.animation.event_source.stop()
            self.animation = None

    def _plot_earth(self) -> None:
        longitude = np.linspace(-np.pi, np.pi, EARTH_TEXTURE_LONGITUDE_POINTS)
        latitude = np.linspace(-0.5 * np.pi, 0.5 * np.pi, EARTH_TEXTURE_LATITUDE_POINTS)
        lon_grid, lat_grid = np.meshgrid(longitude, latitude)

        x_earth = R_EARTH * np.cos(lat_grid) * np.cos(lon_grid)
        y_earth = R_EARTH * np.cos(lat_grid) * np.sin(lon_grid)
        z_earth = R_EARTH * np.sin(lat_grid)

        if self.earth_texture is not None:
            texture_height, texture_width, _ = self.earth_texture.shape
            lon_indices = np.linspace(0, texture_width - 1, longitude.size).astype(int)
            lat_indices = np.linspace(texture_height - 1, 0, latitude.size).astype(int)
            rgb = self.earth_texture[np.ix_(lat_indices, lon_indices)]
            rgb = np.clip(rgb * 1.08, 0.0, 1.0)
            facecolors = np.empty((*rgb.shape[:2], 4), dtype=float)
            facecolors[:, :, :3] = rgb
            facecolors[:, :, 3] = EARTH_TEXTURE_ALPHA

            self.ax.plot_surface(
                x_earth,
                y_earth,
                z_earth,
                facecolors=facecolors,
                rstride=1,
                cstride=1,
                linewidth=0,
                shade=False,
                antialiased=True,
                zorder=1,
            )
        else:
            self.ax.plot_surface(
                x_earth,
                y_earth,
                z_earth,
                color="#2f80ed",
                alpha=0.42,
                rstride=1,
                cstride=1,
                linewidth=0,
                shade=True,
                zorder=1,
            )
            self.ax.plot_wireframe(
                x_earth,
                y_earth,
                z_earth,
                color="#ffffff",
                linewidth=0.25,
                alpha=0.12,
            )

    def _format_axes(self, positions: np.ndarray) -> None:
        limit = max(float(np.max(np.abs(positions))) * 1.12, R_EARTH * 1.25)
        self.ax.set_xlim(-limit, limit)
        self.ax.set_ylim(-limit, limit)
        self.ax.set_zlim(-limit, limit)
        self.ax.set_box_aspect((1, 1, 1))

        self.ax.set_xlabel("X, км")
        self.ax.set_ylabel("Y, км")
        self.ax.set_zlabel("Z, км")
        self.ax.set_title("Движение спутника в 3D")
        self.ax.legend(loc="upper right")
        self.ax.view_init(elev=24, azim=38)

        for axis in (self.ax.xaxis, self.ax.yaxis, self.ax.zaxis):
            axis._axinfo["grid"].update(
                {"linestyle": "--", "linewidth": 0.5, "color": "#b8c0cc"}
            )

    def _animate(
        self,
        index: int,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        times: np.ndarray,
        speeds: np.ndarray,
    ) -> Tuple[object, ...]:
        return self._set_animation_frame(index, x, y, z, times, speeds)

    def _set_animation_frame(
        self,
        index: int,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        times: np.ndarray,
        speeds: np.ndarray,
    ) -> Tuple[object, ...]:
        self.trail_line.set_data(x[: index + 1], y[: index + 1])
        self.trail_line.set_3d_properties(z[: index + 1])
        self.trail_halo.set_data(x[: index + 1], y[: index + 1])
        self.trail_halo.set_3d_properties(z[: index + 1])

        self.satellite.set_data([x[index]], [y[index]])
        self.satellite.set_3d_properties([z[index]])
        self.satellite_halo.set_data([x[index]], [y[index]])
        self.satellite_halo.set_3d_properties([z[index]])

        self.time_label.set_text(
            f"t = {times[index] / 60.0:.1f} мин\n"
            f"V = {speeds[index]:.3f} км/с"
        )
        return self.trail_halo, self.trail_line, self.satellite_halo, self.satellite


if __name__ == "__main__":
    root = tk.Tk()
    app = OrbitApp(root)
    root.mainloop()
