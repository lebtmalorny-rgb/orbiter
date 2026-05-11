# Стандарты и методы расчёта траекторий спутников

## 1. Краткое резюме

Для real-time визуализации спутников Земли практичный стек выглядит так: получать актуальные GP-данные из CelesTrak или Space-Track, желательно в OMM-совместимом CSV/JSON/XML/KVN-формате, создавать из них объект SGP4, локально пересчитывать положение спутника с нужной частотой отрисовки и преобразовывать координаты из TEME в Earth-fixed / WGS84 для карты. CelesTrak прямо описывает GP-запросы через `CATNR`, `INTDES`, `GROUP`, `NAME`, `SPECIAL` и форматы `TLE/3LE`, `2LE`, `XML`, `KVN`, `JSON`, `CSV`; с 2026-05-09 формат по умолчанию — CSV. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

TLE всё ещё широко используется, но это legacy fixed-width формат. Его элементы не являются обычными кеплеровыми элементами для произвольного propagator: они являются mean elements, согласованными с моделью SGP4/SDP4. CelesTrak отдельно предупреждает, что простая конвертация TLE в другой формат элементов и распространение другой моделью может давать непредсказуемые ошибки. ([celestrak.org](https://celestrak.org/columns/v04n05/))

Для нового приложения лучше использовать OMM-compatible GP data, особенно CSV/JSON для прототипов и XML/KVN для более строгой совместимости со стандартом. Эти форматы снимают часть проблем TLE: 5-значный catalog number, двухзначный год, жёсткие fixed-width поля и ограниченную самодокументируемость. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

SGP4 возвращает координаты в TEME. Для 2D-карты обычно нужен pipeline `TEME → ITRS/ECEF → geodetic WGS84 latitude/longitude/altitude`. В Python этот pipeline удобно делать через Skyfield или Astropy, а в браузере — через `satellite.js` и его функции преобразования координат. ([pypi.org](https://pypi.org/project/sgp4/))

---

## 2. Основные понятия

### NORAD Catalog Number / NORAD_CAT_ID

`NORAD_CAT_ID` — это уникальный номер объекта в каталоге космических объектов, присваиваемый системой Space-Track / U.S. Space Force. Он отличается от `International Designator` / `COSPAR ID`, который кодирует год запуска, порядковый номер запуска в году и часть запуска. Например, один идентификатор отвечает на вопрос “что это за объект в каталоге”, а другой — “к какому запуску и фрагменту запуска он относится”. ([celestrak.org](https://celestrak.org/columns/v04n03/))

Legacy TLE имеет 5-значное поле catalog number. Space-Track описывает Alpha-5 как временный способ расширить legacy TLE, но также рекомендует переходить к расширяемым форматам XML/KVN/JSON. CelesTrak указывает, что OMM-compatible форматы поддерживают 9-значные catalog numbers и решают проблему двухзначного года через ISO 8601 epoch. ([space-track.org](https://www.space-track.org/documentation))

### Mean elements vs osculating orbit

TLE/OMM GP data содержат mean elements, подобранные для конкретной теории распространения, прежде всего SGP4. Они не равны мгновенной физической оскулирующей орбите. Это важно: нельзя безопасно взять TLE, преобразовать его в “классические кеплеровы элементы” и использовать произвольный численный интегратор без корректной процедуры преобразования и уточнения состояния. ([celestrak.org](https://celestrak.org/columns/v04n05/))

### Propagation vs ephemeris

Есть два разных подхода:

1. **Elements + propagator**: получить элементы орбиты, например TLE/OMM, и рассчитывать положение через SGP4.
2. **Ephemeris**: получить готовые координаты/скорости на наборе эпох, например OEM, и интерполировать между ними.

CCSDS ODM разделяет эти типы сообщений: OPM описывает состояние на эпоху, OMM — mean elements для аналитических или полуаналитических моделей, OEM — координаты/скорости на множестве эпох, OCM — более комплексное сообщение, которое может объединять разные типы данных. ([ccsds.org](https://ccsds.org/Pubs/502x0b3e1.pdf))

---

## 3. Источники данных NORAD / Space-Track / CelesTrak

## 3.1 CelesTrak

CelesTrak — удобный публичный источник GP-данных без обязательной авторизации. Основной endpoint для GP data:

```text
https://celestrak.org/NORAD/elements/gp.php?{QUERY}=VALUE[&FORMAT=VALUE]
```

Поддерживаемые типы query:

```text
CATNR   — NORAD Catalog Number
INTDES  — International Designator
GROUP   — группа спутников
NAME    — имя объекта или маска имени
SPECIAL — специальные наборы, например GPZ, GPZ-PLUS, DECAYING
```

Поддерживаемые форматы:

```text
TLE / 3LE
2LE
XML
KVN
JSON
JSON-PRETTY
CSV
```

CelesTrak указывает, что `{QUERY}` должен быть в верхнем регистре, а формат по умолчанию с 2026-05-09 — CSV. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

Примеры запросов:

```text
# ISS by NORAD Catalog Number, CSV / OMM-compatible
https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV

# ISS by NORAD Catalog Number, TLE
https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE

# Space stations group
https://celestrak.org/NORAD/elements/gp.php?GROUP=STATIONS&FORMAT=JSON

# Starlink group
https://celestrak.org/NORAD/elements/gp.php?GROUP=STARLINK&FORMAT=CSV

# GPS operational
https://celestrak.org/NORAD/elements/gp.php?GROUP=GPS-OPS&FORMAT=CSV
```

CelesTrak просит не скачивать данные слишком часто: он проверяет обновления GP примерно раз в 2 часа, рекомендует использовать локально сохранённые данные, если они свежие, и обрабатывать HTTP `403`, `404`, `301`, `500`. Для больших наборов, таких как Active или Starlink, CelesTrak ограничивает повторные скачивания и может блокировать чрезмерные запросы. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 3.2 Space-Track.org

Space-Track — официальный источник Basic SSA data, требующий аккаунт. В документации описаны REST-style запросы и ограничения API: менее 30 запросов в минуту и менее 300 запросов в час. Для GP data указан лимит получения “current” GP примерно 1 раз в час, а `GP_History` следует использовать для исторических данных, не для постоянного получения текущих элементов. ([space-track.org](https://www.space-track.org/documentation))

Основные классы для задачи:

```text
gp          — текущий newest elset для объектов
gp_history  — исторические element sets
satcat      — каталог объектов
```

Space-Track описывает GP и GP_History как OMM-based данные. Форматы `XML`, `KVN`, `JSON`, `CSV`, `HTML` используют OMM keywords. Legacy TLE/3LE остаются, но Space-Track рекомендует использовать OMM XML или другие расширяемые форматы, потому что TLE не поддерживает каталоговые номера выше 99,999 без workaround. ([space-track.org](https://www.space-track.org/documentation))

Примеры запросов Space-Track:

```text
# Текущий GP для ISS в TLE
/basicspacedata/query/class/gp/norad_cat_id/25544/format/tle

# Текущий GP для нескольких объектов в KVN
/basicspacedata/query/class/gp/norad_cat_id/25544,48274,43013/format/kvn

# История GP для ISS за последние 30 дней
/basicspacedata/query/class/gp_history/norad_cat_id/25544/CREATION_DATE/>now-30/format/json
```

Для авторизации нужен отдельный пользовательский аккаунт, собственные логин и пароль, согласие с user agreement и валидный email. Для Python есть клиент `spacetrack`, который автоматически аутентифицируется при запросе и позволяет вызывать, например, `st.gp(norad_cat_id=[...], format='tle')`. ([space-track.org](https://www.space-track.org/documentation))

---

## 4. Форматы данных

## 4.1 TLE / 2LE / 3LE

TLE — Two-Line Element Set. Классический TLE состоит из двух строк по 69 символов. Иногда добавляется строка 0 с именем объекта; такой вариант часто называют 3LE. ([celestrak.org](https://celestrak.org/columns/v04n03/))

Пример структуры:

```text
ISS (ZARYA)
1 25544U 98067A   26131.12345678  .00012345  00000+0  12345-3 0  9991
2 25544  51.6416 123.4567 0001234  12.3456 234.5678 15.50000000123456
```

### Line 0

```text
ISS (ZARYA)
```

Содержит имя объекта. Это не обязательная часть классического 2LE, но часто используется в 3LE.

### Line 1

Основные поля:

```text
Line number
Satellite catalog number
Classification
International Designator
Epoch year
Epoch day of year
First derivative of mean motion
Second derivative of mean motion
BSTAR drag term
Ephemeris type
Element set number
Checksum
```

Space-Track и CelesTrak описывают двухзначный epoch year так: `57–99` трактуется как `1957–1999`, а `00–56` — как `2000–2056`. Это legacy-ограничение и одна из причин перехода на OMM-compatible форматы. ([celestrak.org](https://celestrak.org/columns/v04n03/))

### Line 2

Основные поля:

```text
Line number
Satellite catalog number
Inclination
RAAN / Right Ascension of Ascending Node
Eccentricity
Argument of perigee
Mean anomaly
Mean motion
Revolution number at epoch
Checksum
```

Checksum считается по модулю 10; цифры учитываются как свои значения, знак минус считается как `1`, остальные символы — как `0`. ([celestrak.org](https://celestrak.org/columns/v04n03/))

### Важное ограничение TLE

TLE должен использоваться с SGP4/SDP4. Это не универсальный формат “кеплеровых элементов”. CelesTrak подчёркивает, что TLE mean elements получены под конкретную модель, поэтому простая конвертация в другой формат элементов не делает их пригодными для произвольного propagator. ([celestrak.org](https://celestrak.org/columns/v04n05/))

---

## 4.2 GP data / General Perturbations

GP data — это данные, которые используются с General Perturbations theory, в практическом контексте публичных каталогов чаще всего с SGP4. CelesTrak описывает GP data как данные, полученные фитированием наблюдений Space Surveillance Network к mean elements Brouwer с использованием SGP4. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

Раньше GP data почти всегда воспринимались как TLE. Сейчас те же данные могут распространяться в OMM-compatible форматах: XML, KVN, JSON, CSV. Для нового приложения это предпочтительнее, потому что поля явно названы, формат легче парсить, нет жёсткого fixed-width parsing и меньше legacy-ограничений. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 4.3 OMM / Orbit Mean-Elements Message

OMM — Orbit Mean-Elements Message, часть стандарта CCSDS Orbit Data Messages. OMM содержит mean Keplerian elements на эпоху для аналитических или полуаналитических моделей. CCSDS прямо описывает, что OMM включает mean motion, eccentricity, inclination, RAAN, argument of pericenter и mean anomaly, а также может включать поля, нужные для создания TLE. ([ccsds.org](https://ccsds.org/Pubs/502x0b3e1.pdf))

Типичные OMM-поля, нужные для SGP4:

```text
OBJECT_NAME
OBJECT_ID
NORAD_CAT_ID
CLASSIFICATION_TYPE
EPOCH
MEAN_MOTION
ECCENTRICITY
INCLINATION
RA_OF_ASC_NODE
ARG_OF_PERICENTER
MEAN_ANOMALY
EPHEMERIS_TYPE
ELEMENT_SET_NO
REV_AT_EPOCH
BSTAR
MEAN_MOTION_DOT
MEAN_MOTION_DDOT
MEAN_ELEMENT_THEORY
CENTER_NAME
REF_FRAME
TIME_SYSTEM
```

Для GP/SGP4 часто используются значения:

```text
CENTER_NAME = EARTH
REF_FRAME = TEME
TIME_SYSTEM = UTC
MEAN_ELEMENT_THEORY = SGP4
```

CelesTrak указывает, что в JSON/CSV некоторые обязательные поля OMM могут опускаться как избыточные, если они имеют ожидаемые значения, например `CENTER_NAME=EARTH`, `REF_FRAME=TEME`, `TIME_SYSTEM=UTC`, `MEAN_ELEMENT_THEORY=SGP4`. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 4.4 OPM / OEM / OCM

CCSDS ODM включает несколько типов сообщений:

| Формат | Что содержит | Когда использовать |
|---|---|---|
| `OPM` | Положение и скорость одного объекта на одной эпохе; опционально оскулирующие кеплеровы элементы, ковариация, манёвры, параметры drag/SRP | Когда нужно передать состояние объекта на одну эпоху и явно указать метод дальнейшего propagation |
| `OMM` | Mean elements на эпоху для аналитических или полуаналитических моделей | Когда нужно передать элементы, например для SGP4 |
| `OEM` | Положение и скорость на множестве эпох | Когда поставщик даёт готовую эфемериду, а потребитель интерполирует |
| `OCM` | Комплексное сообщение, объединяющее возможности OPM/OEM/OMM и дополнительные метаданные | Когда нужна более полная передача состояния, моделей, ковариаций, манёвров, EOP, leap seconds и других данных |

CCSDS указывает, что OEM предназначен для более высокой точности за счёт передачи координат и скоростей на множестве эпох, а OCM может включать расширенные данные, такие как EOP, leap seconds, drag/SRP area, covariance, maneuvers, perturbation models и OD metrics. ([ccsds.org](https://ccsds.org/Pubs/502x0b3e1.pdf))

---

## 5. Сравнение форматов данных

| Формат | Назначение | Плюсы | Минусы | Рекомендация |
|---|---|---|---|---|
| `TLE / 3LE` | Legacy GP data для SGP4/SDP4 | Максимальная совместимость, много библиотек, компактность | Fixed-width parsing, 5-значный catalog number, двухзначный год, слабая самодокументируемость | Подходит для быстрых прототипов и совместимости |
| `2LE` | Только две TLE-строки без имени | Очень компактно | Нет имени объекта, те же legacy-проблемы | Использовать только если нужна совместимость |
| `OMM XML` | Стандартизованное CCSDS-представление mean elements | Наиболее строгий и self-describing формат | Больше размер, сложнее парсинг | Лучший выбор для систем, где важна совместимость со стандартом |
| `OMM KVN` | CCSDS key-value notation | Читабельно, стандартизовано | Менее удобно для браузерного JSON-first стека | Хорошо для инженерных систем и логов |
| `OMM JSON` | OMM-compatible поля в JSON | Удобно для веб-приложений | Может быть больше CSV | Хороший выбор для frontend/backend приложений |
| `OMM CSV` | OMM-compatible поля в CSV | Компактно, быстро парсится, default у CelesTrak с 2026-05-09 | Нужно аккуратно валидировать колонки | Рекомендуемый формат для массовой загрузки групп |
| `OEM` | Эфемериды position/velocity на множестве эпох | Не требует самостоятельного propagation модели элементов | Нужна интерполяция, зависит от поставщика и интервала | Использовать, когда нужны готовые высокоточные эфемериды |

Эта таблица основана на описаниях CelesTrak GP data, Space-Track GP/GP_History и CCSDS ODM. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 6. Методы расчёта орбит

| Метод | Входные данные | Выходные данные | Точность и ограничения | Real-time применимость |
|---|---|---|---|---|
| `SGP4 / SDP4` | TLE или OMM GP data | Положение и скорость в TEME | Хорошо подходит для публичных каталоговых GP-данных; ошибка зависит от объекта, возраста элементов, drag, манёвров и качества fit | Отлично подходит: быстрый расчёт локально много раз в секунду |
| Численное интегрирование | Начальное состояние, force model, gravity model, drag, SRP, EOP, манёвры | Состояние в выбранной системе координат | Может быть точнее, если есть качественные исходные данные и модели; TLE напрямую для этого не подходит | Подходит, но тяжелее и сложнее |
| Аналитические / полуаналитические методы | Mean elements и параметры модели | Состояние или элементы во времени | Быстрее численных методов, но зависят от области применимости модели | Хорошо подходят для массовых расчётов |
| Эфемериды / OEM | Position/velocity на сетке эпох | Интерполированное положение/скорость | Точность зависит от поставщика, интервала и метода интерполяции | Подходит, если есть актуальные эфемериды и правильная интерполяция |

Python-пакет `sgp4`, основанный на Vallado / Revisiting Spacetrack Report #3, указывает, что SGP4/SDP4 выбираются по периоду орбиты, а типичная расходимость реального спутника с идеальной TLE-орбитой может составлять порядка 1–3 км в день, хотя это не универсальная гарантия точности. ([pypi.org](https://pypi.org/project/sgp4/))

---

## 7. Системы координат и преобразования

### TEME

SGP4 возвращает положение и скорость в `TEME` — True Equator, Mean Equinox. Это Earth-centered inertial frame, но не то же самое, что стандартные современные `GCRS/ICRS` или Earth-fixed frames. ([pypi.org](https://pypi.org/project/sgp4/))

### ECI vs ECEF / ITRS / ITRF

Для 3D-сцены можно использовать инерциальные координаты, если Земля в сцене вращается. Для карты или Earth-fixed глобуса обычно нужны Earth-fixed координаты: `ECEF`, `ITRS` или реализация через `ITRF`. IERS описывает, что ITRS реализуется через ITRF, а связь небесных и земных систем требует Earth Orientation Parameters. ([iers.org](https://www.iers.org/IERS/EN/DataProducts/ITRS/itrs))

### WGS84 latitude / longitude / altitude

Для отображения на 2D-карте нужен geodetic результат:

```text
latitude
longitude
altitude above WGS84 ellipsoid
```

Astropy показывает типовой путь: получить TEME position/velocity из SGP4, создать TEME frame с `obstime`, преобразовать в `ITRS`, затем получить geodetic latitude/longitude/height. Skyfield предоставляет более прямой high-level API через `wgs84.latlon_of()` и `wgs84.height_of()`. ([docs.astropy.org](https://docs.astropy.org/en/latest/coordinates/satellites.html))

### Earth Orientation Parameters

Для точных преобразований между небесными и земными системами нужны `UT1-UTC`, polar motion и другие EOP. Astropy использует IERS-таблицы для интерполяции `UT1-UTC` и polar motion; пользователи отвечают за оценку точности, если расчёт зависит от предсказательных EOP. ([docs.astropy.org](https://docs.astropy.org/en/stable/utils/iers.html))

---

## 8. Pipeline расчёта положения спутника

Типовой pipeline для real-time visualizer:

```text
1. Получить GP data из CelesTrak или Space-Track.
2. Выбрать формат: CSV/JSON/KVN/XML OMM или legacy TLE.
3. Распарсить элементы.
4. Создать satellite record / Satrec / EarthSatellite.
5. Для текущего времени t вызвать SGP4.
6. Получить position/velocity в TEME.
7. Преобразовать TEME → ITRS/ECEF.
8. Преобразовать ECEF/ITRS → WGS84 latitude/longitude/altitude.
9. Отобразить:
   - текущую позицию;
   - ground track;
   - будущую траекторию;
   - прошедшую траекторию;
   - 3D-орбиту.
10. Пересчитывать положение локально 1–60 раз в секунду.
11. Обновлять элементы не каждый кадр, а по расписанию и с кешированием.
```

Для CelesTrak разумная базовая политика кеширования — не чаще одного запроса к одному набору примерно раз в 2 часа, потому что CelesTrak сам проверяет обновления GP data примерно с таким интервалом и ограничивает чрезмерные загрузки. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 9. Архитектура приложения real-time visualizer

Рекомендуемая структура проекта:

```text
satellite-tracker/
  src/
    data/
      providers/
        celestrak.ts
        spacetrack.ts
      parsers/
        tle.ts
        omm.ts
      cache/
        elementCache.ts
    orbit/
      sgp4.ts
      frames.ts
      propagation.ts
      visibility.ts
    visualization/
      map2d.ts
      globe3d.ts
      groundTrack.ts
      footprint.ts
    workers/
      propagationWorker.ts
    app/
      index.ts
  docs/
    standards.md
    data-formats.md
    architecture.md
  tests/
    tle.test.ts
    omm.test.ts
    propagation.test.ts
```

### Модули

| Модуль | Ответственность |
|---|---|
| `data/providers/celestrak.ts` | Запросы к CelesTrak, обработка `CATNR`, `GROUP`, `NAME`, `INTDES`, `SPECIAL`, кеширование |
| `data/providers/spacetrack.ts` | Авторизация Space-Track, запросы `gp`, `gp_history`, `satcat`, соблюдение rate limits |
| `data/parsers/tle.ts` | Парсинг TLE/2LE/3LE, checksum, epoch, валидация |
| `data/parsers/omm.ts` | Парсинг OMM CSV/JSON/KVN/XML, маппинг полей |
| `orbit/sgp4.ts` | Создание satrec и вызов SGP4 |
| `orbit/frames.ts` | TEME/ECEF/WGS84 преобразования |
| `orbit/propagation.ts` | Расчёт позиции на текущий момент и на интервал времени |
| `orbit/visibility.ts` | Azimuth/elevation/range, пролёты над точкой наблюдателя |
| `visualization/map2d.ts` | Отображение ground track на Leaflet/MapLibre |
| `visualization/globe3d.ts` | Cesium/Three.js глобус |
| `workers/propagationWorker.ts` | Расчёты в Web Worker, чтобы не блокировать UI |

### Рекомендуемый TypeScript-стек

Для браузерного приложения:

```text
satellite.js  — SGP4/SDP4 и базовые coordinate transforms
MapLibre GL   — 2D-карта
CesiumJS      — 3D-глобус и орбитальная визуализация
Web Workers   — массовый propagation без блокировки UI
IndexedDB     — кеш GP data
```

`satellite.js` поддерживает TLE и OMM, SGP4/SDP4 и преобразования `ECI → ECF`, `ECI → geodetic`, `ECF → look angles`, что делает его удобным для веб-визуализации. ([github.com](https://github.com/shashwatak/satellite-js))

---

## 10. Минимальный Python-прототип

Прототип ниже:

- получает ISS по `CATNR=25544` из CelesTrak в CSV / OMM-compatible формате;
- кеширует ответ на 2 часа;
- создаёт объект спутника через Skyfield;
- считает текущие latitude, longitude, altitude, velocity;
- строит ground track на ближайшие 90 минут;
- сохраняет картинку `ground_track_iss.png`.

### Установка

```bash
python -m venv .venv
source .venv/bin/activate

pip install skyfield numpy matplotlib
python iss_groundtrack.py
```

### `iss_groundtrack.py`

```python
from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
from skyfield.api import EarthSatellite, load, wgs84


CELESTRAK_ISS_CSV = (
    "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV"
)

CACHE_FILE = Path(".cache/iss_25544_omm.csv")
CACHE_TTL_SECONDS = 2 * 60 * 60


def read_or_download(url: str, cache_path: Path, ttl_seconds: int) -> str:
    """
    Downloads OMM-compatible CSV from CelesTrak, but avoids repeated requests.
    If the cache is fresh, use it. If network fails and cache exists, use cache.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        age = datetime.now(timezone.utc).timestamp() - cache_path.stat().st_mtime
        if age < ttl_seconds:
            return cache_path.read_text(encoding="utf-8")

    request = Request(
        url,
        headers={
            "User-Agent": (
                "satellite-tracker-prototype/0.1 "
                "(educational; contact=local; cache=2h)"
            )
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {status}")

            text = response.read().decode("utf-8")

            if not text.strip():
                raise RuntimeError("Empty response from CelesTrak")

            cache_path.write_text(text, encoding="utf-8")
            return text

    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        if cache_path.exists():
            print(f"Network error, using cached data: {exc}")
            return cache_path.read_text(encoding="utf-8")
        raise


def load_satellite_from_omm_csv(text: str) -> tuple:
    """
    Parses CelesTrak CSV/OMM-compatible data and creates a Skyfield satellite.
    """
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("No rows found in OMM CSV")

    row = rows[0]
    timescale = load.timescale()

    # Skyfield maps OMM fields into an SGP4-compatible EarthSatellite object.
    satellite = EarthSatellite.from_omm(timescale, row)
    return timescale, satellite, row


def split_dateline(lons: np.ndarray, lats: np.ndarray) -> list[tuple[list[float], list[float]]]:
    """
    Splits a longitude/latitude track into segments to avoid drawing
    artificial lines across the map when crossing ±180 degrees.
    """
    if len(lons) == 0:
        return []

    segments: list[tuple[list[float], list[float]]] = []
    current_lons = [float(lons[0])]
    current_lats = [float(lats[0])]

    for i in range(1, len(lons)):
        prev_lon = float(lons[i - 1])
        lon = float(lons[i])
        lat = float(lats[i])

        if abs(lon - prev_lon) > 180:
            segments.append((current_lons, current_lats))
            current_lons = [lon]
            current_lats = [lat]
        else:
            current_lons.append(lon)
            current_lats.append(lat)

    segments.append((current_lons, current_lats))
    return segments


def main() -> None:
    text = read_or_download(
        CELESTRAK_ISS_CSV,
        CACHE_FILE,
        CACHE_TTL_SECONDS,
    )

    ts, satellite, omm = load_satellite_from_omm_csv(text)

    now_utc = datetime.now(timezone.utc)
    t_now = ts.from_datetime(now_utc)

    # SGP4 propagation. Skyfield wraps the frame handling and exposes WGS84 helpers.
    geocentric = satellite.at(t_now)

    lat, lon = wgs84.latlon_of(geocentric)
    height = wgs84.height_of(geocentric)

    velocity_km_s = float(np.linalg.norm(geocentric.velocity.km_per_s))

    print("Satellite:", omm.get("OBJECT_NAME", "UNKNOWN"))
    print("NORAD_CAT_ID:", omm.get("NORAD_CAT_ID", "UNKNOWN"))
    print("Timestamp UTC:", now_utc.isoformat())
    print(f"Latitude deg:  {lat.degrees:.6f}")
    print(f"Longitude deg: {lon.degrees:.6f}")
    print(f"Altitude km:   {height.km:.3f}")
    print(f"Velocity km/s: {velocity_km_s:.6f}")

    # Ground track for the next 90 minutes.
    minutes = np.linspace(0, 90, 181)
    future_datetimes = [
        now_utc + timedelta(minutes=float(minute))
        for minute in minutes
    ]

    t_track = ts.from_datetimes(future_datetimes)
    track = satellite.at(t_track)

    track_lat, track_lon = wgs84.latlon_of(track)

    lats = np.asarray(track_lat.degrees)
    lons = np.asarray(track_lon.degrees)

    # Normalize longitude to [-180, 180].
    lons = ((lons + 180.0) % 360.0) - 180.0

    fig, ax = plt.subplots(figsize=(11, 5))

    for segment_lons, segment_lats in split_dateline(lons, lats):
        ax.plot(segment_lons, segment_lats, linewidth=1)

    ax.scatter([lon.degrees], [lat.degrees], marker="o", label="current position")

    ax.set_title("ISS ground track, next 90 minutes")
    ax.set_xlabel("Longitude, degrees")
    ax.set_ylabel("Latitude, degrees")
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.grid(True)
    ax.legend(loc="upper right")

    output_path = Path("ground_track_iss.png")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)

    print(f"Saved plot: {output_path.resolve()}")


if __name__ == "__main__":
    main()
```

Skyfield поддерживает загрузку OMM CSV/JSON через `EarthSatellite.from_omm()` и предоставляет helpers для получения WGS84 latitude/longitude/height, поэтому он удобен для прототипа и проверки pipeline перед переносом в TypeScript. ([rhodesmill.org](https://rhodesmill.org/skyfield/earth-satellites.html))

---

## 11. TypeScript-скелет для браузерной версии

### Установка

```bash
npm install satellite.js
```

### Пример propagation через `satellite.js`

```ts
import * as satellite from "satellite.js";

const tleLine1 =
  "1 25544U 98067A   26131.12345678  .00012345  00000+0  12345-3 0  9991";
const tleLine2 =
  "2 25544  51.6416 123.4567 0001234  12.3456 234.5678 15.50000000123456";

const satrec = satellite.twoline2satrec(tleLine1, tleLine2);

const now = new Date();
const positionAndVelocity = satellite.propagate(satrec, now);

if (!positionAndVelocity.position || !positionAndVelocity.velocity) {
  throw new Error("SGP4 propagation failed");
}

const gmst = satellite.gstime(now);

const positionEci = positionAndVelocity.position;
const positionGd = satellite.eciToGeodetic(positionEci, gmst);

const longitude = satellite.degreesLong(positionGd.longitude);
const latitude = satellite.degreesLat(positionGd.latitude);
const altitudeKm = positionGd.height;

console.log({
  timestampUtc: now.toISOString(),
  latitude,
  longitude,
  altitudeKm,
});
```

`satellite.js` документация показывает тот же общий путь: создать `satrec`, вызвать `propagate`/`sgp4`, вычислить `GMST`, затем преобразовать ECI-position в ECF/geodetic/look angles. ([github.com](https://github.com/shashwatak/satellite-js))

---

## 12. Тесты и проверка корректности

### Unit tests для TLE

Проверить:

```text
- line 1 начинается с "1"
- line 2 начинается с "2"
- обе строки имеют ожидаемую длину 69 символов
- catalog number совпадает в line 1 и line 2
- checksum корректен
- epoch year/day корректно парсится
- eccentricity восстанавливается как 0.xxxxxxx
```

### Unit tests для OMM

Проверить:

```text
- есть NORAD_CAT_ID
- есть EPOCH
- есть MEAN_MOTION
- есть ECCENTRICITY
- есть INCLINATION
- есть RA_OF_ASC_NODE
- есть ARG_OF_PERICENTER
- есть MEAN_ANOMALY
- если REF_FRAME отсутствует в CSV/JSON, используется TEME как expected default для CelesTrak GP
```

### Tests для propagation

Проверить:

```text
- SGP4 не возвращает ошибку
- latitude находится в диапазоне [-90, 90]
- longitude находится в диапазоне [-180, 180] или [0, 360] до нормализации
- altitude > 0 для LEO-спутников вроде ISS
- ground track не рисует линию через всю карту при пересечении ±180 longitude
```

### Integration tests

Проверить:

```text
- CelesTrak provider использует cache TTL
- HTTP 403/404/500 не приводят к бесконечному retry loop
- при network error используется последний валидный cache
- batch-запрос группы не разбивается на сотни одиночных запросов
```

Space-Track прямо просит не отправлять сотни индивидуальных запросов и объединять запросы по нескольким объектам через comma-separated lists. ([space-track.org](https://www.space-track.org/documentation))

---

## 13. Ограничения и риски

1. **TLE/SGP4 не предназначены для высокоточного управления спутником.** Space-Track указывает, что публичные TLE не должны использоваться для conjunction assessment; операторам следует обращаться за соответствующими данными и анализом через 18 SDS. ([space-track.org](https://www.space-track.org/documentation))

2. **Ошибка растёт с удалением от epoch.** Точность зависит от орбиты, возраста элементов, drag, манёвров, качества наблюдений и fit. CelesTrak указывает, что вопрос “как часто обновлять TLE” зависит от конкретного объекта и задачи. ([celestrak.org](https://celestrak.org/columns/v04n05/))

3. **Маневрирующие спутники быстро устаревают.** После манёвра старый TLE/OMM может давать заметно неверную позицию.

4. **BSTAR — параметр модели, а не универсальный физический коэффициент сопротивления.** В TLE он используется внутри SGP4-модели и не должен трактоваться как прямой физический drag coefficient без контекста. CelesTrak описывает BSTAR как drag term в рамках TLE/SGP4. ([celestrak.org](https://celestrak.org/columns/v04n03/))

5. **Нельзя механически конвертировать TLE в другой propagator.** TLE mean elements согласованы с SGP4/SDP4; простая конвертация может давать непредсказуемые ошибки. ([celestrak.org](https://celestrak.org/columns/v04n05/))

6. **Координатные преобразования важны.** Для карты нужны WGS84 latitude/longitude/altitude, а не TEME или “ECI-like” координаты напрямую. SGP4 возвращает TEME, а точные преобразования к земной системе зависят от времени и EOP. ([pypi.org](https://pypi.org/project/sgp4/))

7. **Нельзя скачивать элементы каждый кадр.** Положение пересчитывается локально, а элементы обновляются периодически. Для CelesTrak разумная политика — кешировать и не запрашивать один и тот же набор чаще, чем примерно раз в 2 часа. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))

---

## 14. Рекомендации по выбору формата и библиотеки

### Для нового production-like приложения

Рекомендуемый выбор:

```text
Data source:
  CelesTrak GP CSV/JSON для публичных данных
  Space-Track GP/GP_History при наличии аккаунта и необходимости истории

Format:
  CSV для массовых групп
  JSON для web API
  XML/KVN OMM для строгой совместимости со стандартом
  TLE только для совместимости с legacy-библиотеками

Propagation:
  SGP4 для GP/TLE/OMM mean elements

Frontend:
  satellite.js + Web Worker
  MapLibre/Leaflet для 2D
  CesiumJS для 3D-глобуса

Backend:
  cache layer
  rate-limit protection
  batch requests
  historical data storage if needed
```

### Для исследовательского прототипа

```text
Python:
  skyfield
  sgp4
  astropy
  numpy
  matplotlib / plotly
```

Skyfield удобен для быстрого прототипа, потому что умеет работать с OMM CSV/JSON и предоставляет WGS84 helpers; Astropy удобен, когда нужно явно контролировать frame transformations и IERS/EOP. ([rhodesmill.org](https://rhodesmill.org/skyfield/earth-satellites.html))

---

## 15. Официальные и полезные источники

- CelesTrak GP Data Formats: описание `gp.php`, `CATNR`, `INTDES`, `GROUP`, `NAME`, `SPECIAL`, форматов TLE/2LE/XML/KVN/JSON/CSV, default CSV и рекомендаций по кешированию. ([celestrak.org](https://celestrak.org/NORAD/documentation/gp-data-formats.php))
- CelesTrak Current GP Element Sets: актуальные категории и группы спутников. ([celestrak.org](https://celestrak.org/NORAD/elements/))
- CelesTrak TLE FAQ: структура TLE, 69-символьные строки, поля line 1/line 2, checksum, epoch. ([celestrak.org](https://celestrak.org/columns/v04n03/))
- CelesTrak More FAQs: предупреждение о mean elements и TEME output. ([celestrak.org](https://celestrak.org/columns/v04n05/))
- Space-Track Documentation: API, GP/GP_History, rate limits, OMM-compatible форматы, legacy TLE limitations. ([space-track.org](https://www.space-track.org/documentation))
- CCSDS Orbit Data Messages 502.0-B-3: OPM, OMM, OEM, OCM. ([ccsds.org](https://ccsds.org/publications/allpubs/entry/3073/))
- Python `sgp4`: Vallado implementation, TEME output, TLE/OMM support. ([pypi.org](https://pypi.org/project/sgp4/))
- Skyfield Earth Satellites: OMM JSON/CSV, WGS84 helpers, observer calculations. ([rhodesmill.org](https://rhodesmill.org/skyfield/earth-satellites.html))
- Astropy satellite/TEME docs: TEME frame, transformation to ITRS and geodetic coordinates. ([docs.astropy.org](https://docs.astropy.org/en/latest/coordinates/satellites.html))
- IERS / Astropy IERS: Earth Orientation Parameters, `UT1-UTC`, polar motion. ([docs.astropy.org](https://docs.astropy.org/en/stable/utils/iers.html))
- `satellite.js`: JavaScript SGP4/SDP4, TLE/OMM, coordinate transforms for browser apps. ([github.com](https://github.com/shashwatak/satellite-js))