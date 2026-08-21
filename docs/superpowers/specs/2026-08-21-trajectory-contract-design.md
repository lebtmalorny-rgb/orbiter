# Дизайн контракта траектории Orbiter

Дата: 2026-08-21

## Цель

Ввести версионированный контракт траектории, который явно разделяет
инерциальную 3D-орбиту и Earth-fixed ground track, задаёт frame, time scale,
units и force model рядом с данными и может в дальнейшем одинаково описывать
учебную RK4-траекторию, SGP4/UTC и импортированные эфемериды.

Первый этап добавляет контракт к существующему SGP4 API без немедленного
перевода браузера на новую структуру. Текущие поля ответа сохраняются на время
миграции, поэтому manual и real-time сценарии продолжают работать.

## Причина изменения

Сейчас `RealtimeSatelliteState` корректно хранит отдельно GCRS position,
GCRS velocity, WGS84 latitude/longitude/altitude и `visual_position_km`.
Однако браузер собирает один шестимерный state из Earth-fixed visual position
и GCRS velocity. Такой state не имеет единого frame и позволяет использовать
ground track как будто это замкнутая 3D-орбита.

Новый контракт должен сделать неправильную комбинацию заметной в структуре
данных: положение и скорость одной орбиты находятся в одном вложенном
coordinate set, а geodetic/visual ground-track данные — в другом.

## Выбранный подход

Используется постепенная совместимая миграция:

1. В Python добавляется модуль `orbiter/trajectory.py` с моделью и валидацией
   контракта версии 1.
2. `trajectory_to_json()` добавляет в текущий ответ новый объект `trajectory`.
3. Существующие root-поля `source`, `satellite`, `model_profile`,
   `element_parameters`, `metadata` и `samples` остаются без изменений.
4. Следующие этапы переводят frontend на `trajectory`; после миграции legacy
   поля можно удалить только отдельным намеренным изменением версии API.

Этот подход временно дублирует часть данных, но позволяет проверить контракт
до изменения Three.js-сцены и не объединяет несколько архитектурных этапов в
один рискованный rewrite.

## Контракт версии 1

API добавляет верхнеуровневое поле:

```json
{
  "trajectory": {
    "schema_version": 1,
    "id": "norad:25544",
    "name": "ISS (ZARYA)",
    "kind": "sgp4",
    "source": ".orbiter_cache/celestrak_catnr_25544.json",
    "time": {
      "scale": "UTC",
      "sample_field": "time_utc",
      "start_utc": "2026-08-21T15:00:00+00:00",
      "end_utc": "2026-08-21T18:00:00+00:00"
    },
    "model": {
      "force_model": "SGP4 general perturbations from GP/OMM mean elements.",
      "element_epoch_utc": "2026-08-21T12:00:00+00:00"
    },
    "coordinate_sets": {
      "orbit": {
        "frame": "GCRS",
        "position_unit": "km",
        "velocity_unit": "km/s"
      },
      "ground_track": {
        "frame": "WGS84 geodetic projected onto the static spherical Earth",
        "angle_unit": "degrees",
        "altitude_unit": "km",
        "visual_position_unit": "km"
      }
    },
    "samples": [
      {
        "time_utc": "2026-08-21T15:00:00+00:00",
        "orbit": {
          "position_km": [1.0, 2.0, 3.0],
          "velocity_km_s": [4.0, 5.0, 6.0]
        },
        "ground_track": {
          "latitude_deg": 10.0,
          "longitude_deg": 20.0,
          "altitude_km": 420.0,
          "visual_position_km": [7.0, 8.0, 9.0]
        },
        "quality": {
          "epoch_age_days": 0.25,
          "epoch_is_stale": false
        }
      }
    ]
  }
}
```

Пример показывает форму данных, а не физически согласованный набор чисел.

## Семантика полей

### Идентификация

- `schema_version` всегда равен целому числу `1` для этого контракта.
- `id` стабилен внутри источника. Для NORAD используется
  `norad:<NORAD_CAT_ID>`; будущие manual/import providers получают собственные
  namespace.
- `name` — отображаемое имя объекта.
- `kind` в первой версии поддерживает `sgp4`, `numerical` и `ephemeris`.
- `source` описывает фактический источник данных или локальный provider.

### Время

- SGP4 использует `scale = "UTC"`, `sample_field = "time_utc"` и timezone-aware
  ISO 8601 timestamps.
- Будущий manual/RK4 provider использует `scale = "MODEL_ELAPSED"`,
  `sample_field = "t_seconds"` и числа в секундах от `t = 0`.
- Сэмплы строго возрастают по выбранному полю времени.
- `start_utc` и `end_utc` обязательны только для UTC-траекторий и совпадают с
  первым и последним сэмплами.

### Модель

- `force_model` обязателен и не выводится из названия режима.
- `element_epoch_utc` обязателен для SGP4 и отсутствует для модели, у которой
  нет element epoch.
- Локальные `R_EARTH`, `MU`, `J2` и `J2_REFERENCE_RADIUS` не включаются в SGP4
  model как управляющие параметры.

### Coordinate sets

- `orbit` содержит position и velocity в одном указанном frame.
- `ground_track` содержит geodetic значения и отдельную
  `visual_position_km`, спроецированную на текущую статичную сферическую Землю.
- Наличие `ground_track` необязательно для generic ephemeris, но обязательно
  для текущего SGP4 payload.
- Consumer выбирает coordinate set явно. Он не должен собирать state из полей
  разных coordinate sets.

### Quality

- `epoch_age_days` — signed разность между sample UTC и element epoch.
- `epoch_is_stale` сохраняет текущий порог `14 days`.
- Статус кэша не добавляется на этом этапе: metadata загрузки и persistent
  backoff входят в этап 6 общей дорожной карты.

## Python API

Новый модуль `orbiter/trajectory.py` отвечает только за структуру контракта,
валидацию и JSON-compatible serialization. Он не знает о Skyfield, HTTP,
Three.js или кэше CelesTrak.

Публичный интерфейс этапа:

```python
TRAJECTORY_SCHEMA_VERSION = 1

class TrajectoryContractError(ValueError): ...

def build_trajectory_contract(
    *,
    trajectory_id: str,
    name: str,
    kind: str,
    source: str,
    time: dict[str, object],
    model: dict[str, object],
    coordinate_sets: dict[str, dict[str, object]],
    samples: list[dict[str, object]],
) -> dict[str, object]: ...

def validate_trajectory_contract(contract: dict[str, object]) -> None: ...
```

`build_trajectory_contract()` создаёт новый словарь, добавляет
`schema_version`, выполняет валидацию и возвращает JSON-compatible результат.
Входные словари вызывающего кода не изменяются.

## Валидация

Контракт отклоняется с `TrajectoryContractError`, если:

- обязательная строка пуста или `kind` не поддерживается;
- `schema_version` отличается от `1`;
- `samples` пуст или время не возрастает строго;
- UTC timestamp не содержит timezone;
- выбранное sample time field не соответствует time scale;
- position/velocity/visual position не являются тройками конечных чисел;
- latitude не входит в `[-90, 90]` или longitude в `[-180, 180]`;
- обязательный coordinate set или его units/frame отсутствуют;
- SGP4 contract не содержит `element_epoch_utc`, `orbit` или `ground_track`.

Сообщения ошибок называют путь проблемного поля, например
`samples[3].orbit.position_km`, чтобы тесты и API могли диагностировать источник
некорректных данных.

## Интеграция с real-time API

`orbiter.realtime.trajectory_to_json()` строит canonical contract из уже
рассчитанных `RealtimeSatelliteState`:

- `gcrs_position_km` и `gcrs_velocity_km_s` переходят в `sample.orbit`;
- latitude, longitude, altitude и `visual_position_km` переходят в
  `sample.ground_track`;
- epoch age/stale переходят в `sample.quality`;
- текущий legacy payload остаётся байт-в-байт совместим по существующим ключам,
  кроме добавления нового ключа `trajectory`.

`third.py` не меняет маршруты, clamps или HTTP status на этом этапе.

## Тестирование

Новый `tests/test_trajectory.py` покрывает:

- минимальный валидный SGP4 contract;
- отсутствие мутации входных данных;
- строгую сортировку UTC и model elapsed samples;
- timezone-aware UTC;
- конечность и размер координатных векторов;
- границы latitude/longitude;
- обязательность frame/units и SGP4 coordinate sets;
- понятный путь поля в сообщении ошибки.

`tests/test_realtime.py` дополнительно проверяет:

- `schema_version == 1`;
- `id == "norad:<catalog id>"`;
- соответствие nested orbit исходным GCRS position/velocity;
- соответствие nested ground track исходным geodetic/visual полям;
- сохранение всех текущих legacy root keys.

Полная проверка этапа:

```powershell
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
git diff --check
```

Браузерный smoke test подтверждает отсутствие регрессии текущего payload
consumer, но визуальное поведение намеренно не меняется.

## Документация

README получает краткое описание `trajectory.schema_version = 1`, nested
coordinate sets и периода совместимости legacy fields. `guide.md` остаётся
техническим источником для различия GCRS, Earth-fixed/WGS84 и time scales;
если формулировки расходятся с контрактом, они обновляются в этом же этапе.

## Не входит в этап

- перенос JavaScript из `orbiter_web.html`;
- перевод frontend на nested contract;
- изменение внешнего вида меню или линий;
- исправление playback/live/paused;
- адаптивное досэмплирование траектории;
- изменение кэша, backoff или HTTP validation;
- несколько спутников и импорт внешних файлов;
- полноценное вращение Земли или EOP/ITRF implementation.

## Критерии приёмки

- API содержит валидный additive contract версии 1.
- Orbit position и velocity находятся в одном явно указанном GCRS set.
- Ground-track projection отделена структурой данных от 3D-орбиты.
- Старый frontend продолжает работать без изменений.
- Тесты воспроизводимо отклоняют смешанные, несортированные и нечисловые
  данные.
- README, `guide.md`, код и тесты одинаково описывают frame, time scale, units
  и force model.
- Ruff, pytest и `git diff --check` проходят.
