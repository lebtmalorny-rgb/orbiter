from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np

REFERENCE_FRAME = "Геоцентрическая инерциальная Cartesian-система, оси X/Y/Z."
TIME_SCALE = "Относительное модельное время от t=0; UTC/TT/TDB не используются."
UNITS = "Положение: км; скорость: км/с; время: с и мин; углы: градусы."
TWO_BODY_MODEL = "two_body"
J2_MODEL = "j2"
FORCE_MODEL_LABELS = {
    TWO_BODY_MODEL: "Двухтельная модель: точечная Земля, без J2, атмосферы и третьих тел.",
    J2_MODEL: "Двухтельная модель + J2 Земли, без атмосферы, тяги и третьих тел.",
}
FORCE_MODEL = FORCE_MODEL_LABELS[TWO_BODY_MODEL]

R_EARTH = 6371.0
MU = 398600.4418
J2 = 1.08262668e-3
J2_REFERENCE_RADIUS = 6378.1363
DEFAULT_RADIUS = 7000.0
DEFAULT_SPEED = float(np.sqrt(MU / DEFAULT_RADIUS))
MAX_STEPS = 200_000
MOSCOW_LATITUDE_DEG = 55.7558
MOSCOW_LONGITUDE_DEG = 37.6173
EARTH_HOME_POINT = (
    f"Москва: {MOSCOW_LATITUDE_DEG:.4f} deg N, {MOSCOW_LONGITUDE_DEG:.4f} deg E. "
    "Static spherical Earth visual reference."
)


@dataclass
class SimulationConfig:
    """Initial Cartesian state and integration settings.

    Frame: geocentric inertial Cartesian. Units: km, km/s, seconds, minutes.
    Force model: two-body Earth point mass.
    """

    x0: float = DEFAULT_RADIUS
    y0: float = 0.0
    z0: float = 0.0
    vx0: float = 0.0
    vy0: float = DEFAULT_SPEED
    vz0: float = 1.0
    dt: float = 2.0
    duration_min: float = 180.0
    force_model: str = TWO_BODY_MODEL

    @property
    def initial_state(self) -> np.ndarray:
        return np.array(
            [self.x0, self.y0, self.z0, self.vx0, self.vy0, self.vz0],
            dtype=float,
        )


@dataclass(frozen=True)
class OrbitPreset:
    """Classical Keplerian orbit preset.

    Angles are degrees, semi-major axis is km, dt is seconds, duration is minutes.
    """

    name: str
    semi_major_axis: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float = 0.0
    arg_perigee_deg: float = 0.0
    true_anomaly_deg: float = 0.0
    dt: float = 2.0
    duration_min: float = 180.0
    description: str = ""

    def to_config(self) -> SimulationConfig:
        state = orbital_elements_to_state(
            self.semi_major_axis,
            self.eccentricity,
            self.inclination_deg,
            self.raan_deg,
            self.arg_perigee_deg,
            self.true_anomaly_deg,
        )
        return SimulationConfig(
            x0=state[0],
            y0=state[1],
            z0=state[2],
            vx0=state[3],
            vy0=state[4],
            vz0=state[5],
            dt=self.dt,
            duration_min=self.duration_min,
        )

    def summary(self) -> str:
        perigee_alt = self.semi_major_axis * (1.0 - self.eccentricity) - R_EARTH
        apogee_alt = self.semi_major_axis * (1.0 + self.eccentricity) - R_EARTH
        return (
            f"{self.description}\n"
            f"a = {self.semi_major_axis:.1f} км, e = {self.eccentricity:.4f}\n"
            f"i = {self.inclination_deg:.2f} град, "
            f"высота = {perigee_alt:.0f}-{apogee_alt:.0f} км\n"
            f"dt = {self.dt:g} с, расчет = {self.duration_min:g} мин"
        )


def geodetic_surface_point(
    latitude_deg: float,
    longitude_deg: float,
    radius: float = R_EARTH,
) -> np.ndarray:
    """Spherical Earth surface point in the project Cartesian frame.

    Frame: geocentric inertial Cartesian visualization frame with +Z north.
    Time scale: static visual reference, no UTC/TT/TDB and no Earth rotation.
    Units: latitude/longitude in degrees, radius and returned position in km.
    Force model: not applicable; this is a coordinate helper for rendering.
    """
    latitude = np.radians(latitude_deg)
    longitude = np.radians(longitude_deg)
    ring_radius = radius * np.cos(latitude)
    return np.array(
        [
            ring_radius * np.cos(longitude),
            ring_radius * np.sin(longitude),
            radius * np.sin(latitude),
        ],
        dtype=float,
    )


def orbital_elements_to_state(
    semi_major_axis: float,
    eccentricity: float,
    inclination_deg: float,
    raan_deg: float,
    arg_perigee_deg: float,
    true_anomaly_deg: float,
) -> np.ndarray:
    """Convert Keplerian elements to [x, y, z, vx, vy, vz].

    Frame: geocentric inertial Cartesian. Units: km, km/s, degrees.
    """
    if semi_major_axis <= R_EARTH:
        raise ValueError("Большая полуось должна быть больше радиуса Земли.")
    if not 0 <= eccentricity < 1:
        raise ValueError("Эксцентриситет должен быть в диапазоне [0, 1).")
    if semi_major_axis * (1.0 - eccentricity) <= R_EARTH:
        raise ValueError("Перигей орбиты находится внутри Земли. Уменьшите e или увеличьте a.")

    p = semi_major_axis * (1.0 - eccentricity**2)
    nu = np.radians(true_anomaly_deg)
    radius = p / (1.0 + eccentricity * np.cos(nu))

    position_orbital = np.array([radius * np.cos(nu), radius * np.sin(nu), 0.0])
    velocity_orbital = np.sqrt(MU / p) * np.array(
        [-np.sin(nu), eccentricity + np.cos(nu), 0.0]
    )

    rotation = rotation_z(raan_deg) @ rotation_x(inclination_deg) @ rotation_z(arg_perigee_deg)
    position = rotation @ position_orbital
    velocity = rotation @ velocity_orbital
    return np.concatenate((position, velocity))


def rotation_x(angle_deg: float) -> np.ndarray:
    angle = np.radians(angle_deg)
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    return np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, cos_a, -sin_a],
            [0.0, sin_a, cos_a],
        ]
    )


def rotation_z(angle_deg: float) -> np.ndarray:
    angle = np.radians(angle_deg)
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    return np.array(
        [
            [cos_a, -sin_a, 0.0],
            [sin_a, cos_a, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )


def acceleration(position: np.ndarray, force_model: str = TWO_BODY_MODEL) -> np.ndarray:
    """Acceleration in km/s^2 for the selected Earth gravity model."""
    radius = np.linalg.norm(position)

    if radius <= 0:
        raise ValueError("Радиус-вектор не может быть нулевым.")

    central = -MU * position / radius**3
    if force_model == TWO_BODY_MODEL:
        return central
    if force_model != J2_MODEL:
        raise ValueError(f"Неизвестная модель сил: {force_model}.")

    x, y, z = position
    radius2 = radius * radius
    z2_ratio = z * z / radius2
    factor = 1.5 * J2 * MU * J2_REFERENCE_RADIUS**2 / radius**5
    j2_acceleration = factor * np.array(
        [
            x * (5.0 * z2_ratio - 1.0),
            y * (5.0 * z2_ratio - 1.0),
            z * (5.0 * z2_ratio - 3.0),
        ]
    )
    return central + j2_acceleration


def deriv(state: np.ndarray, force_model: str = TWO_BODY_MODEL) -> np.ndarray:
    """State derivative for the selected force model."""
    position = state[:3]
    velocity = state[3:]
    return np.concatenate((velocity, acceleration(position, force_model)))


def rk4_step(state: np.ndarray, dt: float, force_model: str = TWO_BODY_MODEL) -> np.ndarray:
    """One fourth-order Runge-Kutta step. State units are km and km/s."""
    k1 = deriv(state, force_model)
    k2 = deriv(state + 0.5 * dt * k1, force_model)
    k3 = deriv(state + 0.5 * dt * k2, force_model)
    k4 = deriv(state + dt * k3, force_model)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate_orbit(config: SimulationConfig) -> tuple[np.ndarray, np.ndarray, bool]:
    """Propagate the orbit and return history, times, collision flag."""
    if config.dt <= 0:
        raise ValueError("Шаг dt должен быть больше нуля.")
    if config.duration_min <= 0:
        raise ValueError("Длительность расчета должна быть больше нуля.")
    if np.linalg.norm(config.initial_state[:3]) <= R_EARTH:
        raise ValueError(f"Начальная точка находится внутри Земли. Радиус > {R_EARTH:.0f} км.")
    if config.force_model not in FORCE_MODEL_LABELS:
        raise ValueError(f"Неизвестная модель сил: {config.force_model}.")

    steps = int(ceil(config.duration_min * 60.0 / config.dt))
    if steps > MAX_STEPS:
        raise ValueError(
            f"Слишком много шагов расчета: {steps}. "
            "Увеличьте шаг dt или уменьшите длительность."
        )

    history = np.empty((steps + 1, 6), dtype=float)
    times = np.arange(steps + 1, dtype=float) * config.dt
    state = config.initial_state.copy()
    history[0] = state

    stopped_by_collision = False
    last_index = steps

    for index in range(1, steps + 1):
        state = rk4_step(state, config.dt, config.force_model)
        history[index] = state

        if np.linalg.norm(state[:3]) <= R_EARTH:
            stopped_by_collision = True
            last_index = index
            break

    return history[: last_index + 1], times[: last_index + 1], stopped_by_collision


def orbital_summary(
    history: np.ndarray,
    stopped_by_collision: bool,
    force_model: str = TWO_BODY_MODEL,
) -> str:
    """Short trajectory summary with frame, time scale, units and force model."""
    state0 = history[0]
    position = state0[:3]
    velocity = state0[3:]
    radius = np.linalg.norm(position)
    speed = np.linalg.norm(velocity)
    altitude = radius - R_EARTH

    energy = speed**2 / 2.0 - MU / radius
    angular_momentum = np.cross(position, velocity)
    h_norm = np.linalg.norm(angular_momentum)
    e_vector = ((speed**2 - MU / radius) * position - np.dot(position, velocity) * velocity) / MU
    eccentricity = np.linalg.norm(e_vector)

    lines = [
        f"Frame: {REFERENCE_FRAME}",
        f"Time scale: {TIME_SCALE}",
        f"Units: {UNITS}",
        f"Force model: {FORCE_MODEL_LABELS.get(force_model, force_model)}",
        f"Earth home: {EARTH_HOME_POINT}",
        "",
        f"Высота старта: {altitude:.1f} км",
        f"Скорость старта: {speed:.3f} км/с",
        f"Эксцентриситет: {eccentricity:.4f}",
    ]

    if energy < 0:
        semi_major_axis = -MU / (2.0 * energy)
        period_min = 2.0 * np.pi * np.sqrt(semi_major_axis**3 / MU) / 60.0
        lines.append(f"Большая полуось: {semi_major_axis:.1f} км")
        lines.append(f"Период: {period_min:.1f} мин")
    else:
        lines.append("Орбита: незамкнутая")

    if h_norm > 1e-9:
        inclination = np.degrees(np.arccos(np.clip(angular_momentum[2] / h_norm, -1.0, 1.0)))
        lines.append(f"Наклонение: {inclination:.2f} град")
    else:
        lines.append("Наклонение: не определено")

    if stopped_by_collision:
        lines.append("Расчет остановлен: пересечение поверхности Земли.")

    return "\n".join(lines)


ORBIT_PRESETS: dict[str, OrbitPreset] = {
    "МКС": OrbitPreset(
        name="МКС",
        semi_major_axis=R_EARTH + 420.0,
        eccentricity=0.0007,
        inclination_deg=51.64,
        raan_deg=25.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=2.0,
        duration_min=180.0,
        description="Примерная низкая орбита Международной космической станции.",
    ),
    "Низкая круговая орбита": OrbitPreset(
        name="Низкая круговая орбита",
        semi_major_axis=R_EARTH + 500.0,
        eccentricity=0.0,
        inclination_deg=28.5,
        raan_deg=0.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=2.0,
        duration_min=180.0,
        description="Типовая круговая НОО для демонстрации быстрого витка.",
    ),
    "Полярная орбита": OrbitPreset(
        name="Полярная орбита",
        semi_major_axis=R_EARTH + 800.0,
        eccentricity=0.001,
        inclination_deg=98.6,
        raan_deg=35.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=3.0,
        duration_min=220.0,
        description="Солнечно-синхронная орбита для спутников наблюдения Земли.",
    ),
    "Метеор-М": OrbitPreset(
        name="Метеор-М",
        semi_major_axis=7202.0,
        eccentricity=0.00055,
        inclination_deg=98.8,
        raan_deg=45.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=3.0,
        duration_min=220.0,
        description="Примерная солнечно-синхронная орбита метеорологического спутника.",
    ),
    "Канопус-В": OrbitPreset(
        name="Канопус-В",
        semi_major_axis=R_EARTH + 510.0,
        eccentricity=0.001,
        inclination_deg=97.4,
        raan_deg=20.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=2.0,
        duration_min=190.0,
        description="Примерная солнечно-синхронная орбита спутника дистанционного зондирования.",
    ),
    "GPS": OrbitPreset(
        name="GPS",
        semi_major_axis=26560.0,
        eccentricity=0.01,
        inclination_deg=55.0,
        raan_deg=10.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=20.0,
        duration_min=760.0,
        description="Средневысотная навигационная орбита.",
    ),
    "Геостационарная": OrbitPreset(
        name="Геостационарная",
        semi_major_axis=42164.0,
        eccentricity=0.0,
        inclination_deg=0.0,
        raan_deg=0.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
        dt=60.0,
        duration_min=1440.0,
        description="Круговая экваториальная орбита с периодом около суток.",
    ),
    "Молния": OrbitPreset(
        name="Молния",
        semi_major_axis=26562.0,
        eccentricity=0.74,
        inclination_deg=63.4,
        raan_deg=0.0,
        arg_perigee_deg=270.0,
        true_anomaly_deg=0.0,
        dt=20.0,
        duration_min=760.0,
        description="Вытянутая высокоэллиптическая орбита.",
    ),
}
