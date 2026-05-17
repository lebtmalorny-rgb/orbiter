# План реализации улучшения real-time отображения орбит

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ SUB-SKILL: используйте `superpowers:subagent-driven-development` (рекомендуется) или `superpowers:executing-plans`, чтобы выполнять этот план по задачам. Шаги используют checkbox (`- [ ]`) для отслеживания.

**Цель:** сгладить и прояснить текущее real-time отображение SGP4/UTC без большого архитектурного переписывания.

**Архитектура:** Skyfield/SGP4 propagation остается на серверной стороне в `orbiter/realtime.py`, браузер остается renderer. Real-time API samples считаются временным рядом по UTC; `orbiter_web.html` интерполирует visual state, а RK4/manual mode остается явно отдельным режимом.

**Технологии:** Python 3.9, Skyfield/SGP4, plain HTML/CSS/JavaScript, Three.js, pytest, ruff, Playwright MCP для browser verification.

---

## Структура файлов

- Изменить `orbiter_web.html`: добавить real-time interpolation helpers, подключить их к animation/HUD/trail rendering и улучшить поясняющий UI text.
- Изменить `README.md`: описать, что вариант A сохраняет текущую архитектуру, использует interpolation только для плавности отображения и не делает RK4 совпадающим с SGP4.
- Не менять `orbiter/realtime.py`, если реализация не обнаружит обработку некорректных данных, которую обязательно нужно перенести на сервер. Сохранить явный `FORMAT=JSON`, cache TTL, stale fallback и epoch metadata.
- Не создавать satellite catalog module в этом проходе.
- Не коммитить `.superpowers/`, screenshots, traces, cache files или Playwright artifacts.

## Задача 1: Базовая проверка и защита dirty worktree

**Файлы:**
- Только осмотреть: `orbiter_web.html`
- Только осмотреть: `README.md`
- Только осмотреть: `docs/superpowers/specs/2026-05-17-realtime-accuracy-display-design.md`

- [ ] **Шаг 1: Зафиксировать текущее состояние worktree**

Выполнить:

```powershell
git status --short
```

Ожидаемо: могут быть существующие несвязанные изменения. Не откатывать их.

- [ ] **Шаг 2: Запустить baseline verification**

Выполнить:

```powershell
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
```

Ожидаемо: ruff проходит, pytest показывает текущий проходящий счетчик тестов.
Если любая проверка падает до правок, остановиться и сообщить исходную ошибку.

- [ ] **Шаг 3: Подтвердить расположение real-time rendering code**

Выполнить:

```powershell
rg -n "applyRealtimeTrajectory|animate|nearestSampleIndex|updateSatellite|updateHud|trailDrawRange|updateRealtimeSummary" orbiter_web.html
```

Ожидаемо: все перечисленные функции существуют в `orbiter_web.html`.

## Задача 2: Добавить real-time interpolation helpers

**Файлы:**
- Изменить: `orbiter_web.html`

- [ ] **Шаг 1: Добавить globals для visual state**

В `orbiter_web.html`, рядом с текущим mutable state block:

```javascript
    let history = [];
    let times = [];
    let speeds = [];
    let sampleUtcTimes = [];
    let renderPositions = [];
```

добавить:

```javascript
    let activeVisualState = null;
    let realtimeCursorUtcMs = null;
```

- [ ] **Шаг 2: Добавить interpolation helper functions после `nearestSampleIndex()`**

Вставить этот блок сразу после существующей функции `nearestSampleIndex(targetUtcMs)`:

```javascript
    function realtimeSegment(targetUtcMs) {
      if (!sampleUtcTimes.length) {
        return { before: 0, after: 0, ratio: 0 };
      }
      if (targetUtcMs <= sampleUtcTimes[0]) {
        return { before: 0, after: 0, ratio: 0 };
      }
      const lastIndex = sampleUtcTimes.length - 1;
      if (targetUtcMs >= sampleUtcTimes[lastIndex]) {
        return { before: lastIndex, after: lastIndex, ratio: 0 };
      }

      let low = 0;
      let high = lastIndex;
      while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (sampleUtcTimes[mid] < targetUtcMs) {
          low = mid + 1;
        } else {
          high = mid - 1;
        }
      }

      const before = Math.max(0, low - 1);
      const after = Math.min(lastIndex, low);
      const spanMs = Math.max(1, sampleUtcTimes[after] - sampleUtcTimes[before]);
      const ratio = before === after ? 0 : clamp((targetUtcMs - sampleUtcTimes[before]) / spanMs, 0, 1);
      return { before, after, ratio };
    }

    function interpolateNumber(a, b, ratio) {
      return a + (b - a) * ratio;
    }

    function interpolateArray(a, b, ratio) {
      return a.map((value, index) => interpolateNumber(value, b[index], ratio));
    }

    function stateAtSample(index) {
      const safeIndex = clamp(Math.trunc(index), 0, Math.max(0, history.length - 1));
      const state = history[safeIndex] || history[0] || [0, 0, 0, 0, 0, 0];
      const sample = activeTrajectory.samples?.[safeIndex] || activeTrajectory.samples?.[0] || {};
      return {
        index: safeIndex,
        sample,
        utcMs: sampleUtcTimes[safeIndex] || null,
        position: state.slice(0, 3),
        velocity: state.slice(3, 6),
        speed: speeds[safeIndex] || norm(state.slice(3, 6))
      };
    }

    function interpolatedRealtimeState(targetUtcMs) {
      if (activeTrajectory.type !== 'realtime' || !sampleUtcTimes.length || !history.length) {
        return stateAtSample(frameIndex);
      }

      const segment = realtimeSegment(targetUtcMs);
      const beforeState = stateAtSample(segment.before);
      const afterState = stateAtSample(segment.after);
      const nearestIndex = nearestSampleIndex(targetUtcMs);
      const nearestState = stateAtSample(nearestIndex);

      if (segment.before === segment.after) {
        return nearestState;
      }

      const position = interpolateArray(beforeState.position, afterState.position, segment.ratio);
      const velocity = interpolateArray(beforeState.velocity, afterState.velocity, segment.ratio);
      return {
        index: nearestIndex,
        sample: nearestState.sample,
        utcMs: targetUtcMs,
        position,
        velocity,
        speed: norm(velocity)
      };
    }

    function currentVisualState() {
      if (activeTrajectory.type === 'realtime' && activeVisualState) {
        return activeVisualState;
      }
      return stateAtSample(frameIndex);
    }
```

- [ ] **Шаг 3: Учесть, что ruff не проверяет JavaScript**

Не запускать ruff как проверку JavaScript syntax. Сохранить файл и полагаться
на browser verification в задаче 5 для parse errors.

## Задача 3: Подключить interpolation к animation, satellite, HUD и trail

**Файлы:**
- Изменить: `orbiter_web.html`

- [ ] **Шаг 1: Инициализировать visual state в `applyRealtimeTrajectory()`**

Внутри `applyRealtimeTrajectory(payload, stepSeconds, options = {})`, заменить:

```javascript
      frameIndex = nearestSampleIndex(Date.now());
      simulationClock = times[frameIndex] || 0;
      playing = true;
```

на:

```javascript
      realtimeCursorUtcMs = Date.now();
      frameIndex = nearestSampleIndex(realtimeCursorUtcMs);
      activeVisualState = interpolatedRealtimeState(realtimeCursorUtcMs);
      simulationClock = times[frameIndex] || 0;
      playing = true;
```

- [ ] **Шаг 2: Сбрасывать visual state для model mode**

В `runSimulation()`, сразу после:

```javascript
        activeTrajectory = { type: 'model' };
        sampleUtcTimes = [];
```

добавить:

```javascript
        activeVisualState = null;
        realtimeCursorUtcMs = null;
```

- [ ] **Шаг 3: Обновить `resetToStart()`**

Заменить текущее тело `resetToStart()` на:

```javascript
    function resetToStart() {
      playing = false;
      frameIndex = 0;
      simulationClock = 0;
      realtimeCursorUtcMs = sampleUtcTimes[0] || null;
      activeVisualState = activeTrajectory.type === 'realtime'
        ? interpolatedRealtimeState(realtimeCursorUtcMs || Date.now())
        : null;
      updateTrail();
      updateSatellite();
      updateHud();
    }
```

- [ ] **Шаг 4: Обновить `animate()`, чтобы real-time рисовался каждый кадр**

Заменить существующий блок `if (playing && history.length > 1) { ... }` внутри
`animate(timestamp)` на:

```javascript
      if (playing && history.length > 1) {
        if (activeTrajectory.type === 'realtime' && sampleUtcTimes.length) {
          realtimeCursorUtcMs = Date.now();
          activeVisualState = interpolatedRealtimeState(realtimeCursorUtcMs);
          frameIndex = activeVisualState.index;
          updateTrail();
          updateSatellite();
          updateHud();
        } else {
          const nextIndex = nextModelFrameIndex(deltaMs);
          if (nextIndex !== frameIndex) {
            frameIndex = nextIndex;
            updateTrail();
            updateSatellite();
            updateHud();
          }
        }
      }
```

- [ ] **Шаг 5: Обновить `updateSatellite()` для interpolated state**

Заменить:

```javascript
      const state = history[frameIndex];
      const position = new THREE.Vector3(state[0], state[1], state[2]);
```

на:

```javascript
      const visualState = currentVisualState();
      const position = new THREE.Vector3(
        visualState.position[0],
        visualState.position[1],
        visualState.position[2]
      );
```

- [ ] **Шаг 6: Обновить `updateHud()` для interpolated state**

Заменить строки altitude/time/speed в `updateHud()`:

```javascript
      const altitude = norm(history[frameIndex].slice(0, 3)) - R_EARTH;
      const timeLabel = activeTrajectory.type === 'realtime' && sampleUtcTimes[frameIndex]
        ? `UTC = ${formatUtc(sampleUtcTimes[frameIndex])}`
        : `t = ${(times[frameIndex] / 60).toFixed(1)} мин`;
      el.hud.innerHTML = `${timeLabel}<br>h = ${altitude.toFixed(1)} км<br>V = ${speeds[frameIndex].toFixed(3)} км/с`;
```

на:

```javascript
      const visualState = currentVisualState();
      const altitude = norm(visualState.position) - R_EARTH;
      const timeLabel = activeTrajectory.type === 'realtime' && visualState.utcMs
        ? `UTC = ${formatUtc(visualState.utcMs)}`
        : `t = ${(times[frameIndex] / 60).toFixed(1)} мин`;
      el.hud.innerHTML = `${timeLabel}<br>h = ${altitude.toFixed(1)} км<br>V = ${visualState.speed.toFixed(3)} км/с`;
```

- [ ] **Шаг 7: Обновить выбор sample для NORAD panel**

В `updateNoradPanel()`, заменить:

```javascript
      const sample = activeTrajectory.samples?.[frameIndex] || activeTrajectory.samples?.[0] || {};
```

на:

```javascript
      const sample = currentVisualState().sample || activeTrajectory.samples?.[0] || {};
```

- [ ] **Шаг 8: Обновить расчет trail index**

Заменить `currentRenderPointIndex()` на:

```javascript
    function currentRenderPointIndex() {
      const sourceIndex = activeTrajectory.type === 'realtime' && activeVisualState
        ? activeVisualState.index
        : frameIndex;
      if (sourceIndex >= history.length - 1) {
        return Math.max(0, renderPositions.length - 1);
      }
      return Math.min(renderPositions.length - 1, Math.max(0, Math.floor(sourceIndex / renderStride)));
    }
```

- [ ] **Шаг 9: Запустить static text sanity check**

Выполнить:

```powershell
rg -n "activeVisualState|realtimeCursorUtcMs|interpolatedRealtimeState|currentVisualState" orbiter_web.html
```

Ожидаемо: все четыре имени встречаются в файле.

## Задача 4: Улучшить поясняющий real-time text

**Файлы:**
- Изменить: `orbiter_web.html`
- Изменить: `README.md`

- [ ] **Шаг 1: Обновить real-time preset info text**

В `applyRealtimeTrajectory()`, заменить:

```javascript
      el['preset-info'].textContent = 'Траектория получена из GP/OMM и распространена SGP4.';
```

на:

```javascript
      el['preset-info'].textContent = 'SGP4/UTC из CelesTrak GP/OMM. Это не тот же расчет, что учебная RK4-орбита по умолчанию.';
```

- [ ] **Шаг 2: Добавить различие в real-time summary**

В `updateRealtimeSummary()`, после:

```javascript
        `Earth home: ${EARTH_HOME_POINT}`,
        '',
```

добавить:

```javascript
        'Real-time display: satellite position is interpolated between SGP4 UTC samples for smooth rendering.',
        'RK4 presets are educational local trajectories and are not expected to match GP/OMM SGP4 motion.',
        '',
```

- [ ] **Шаг 3: Обновить README real-time section**

В `README.md`, в секции `## Реальное время` после абзаца, который объясняет
поля ответа API, добавить:

```markdown
В браузере real-time движение сглаживается интерполяцией между соседними
UTC-сэмплами SGP4. Это улучшает визуальную плавность, но не меняет источник
истины: координаты по-прежнему приходят из Skyfield/SGP4, а точность зависит от
эпохи GP/OMM элементов и применимости SGP4 к выбранному объекту. Учебные RK4
пресеты не должны совпадать с real-time траекторией без явного начального
состояния из того же момента UTC и без согласованной force model.
```

- [ ] **Шаг 4: Найти потенциально вводящие в заблуждение формулировки**

Выполнить:

```powershell
rg -n "точн|совпад|RK4|SGP4|interpol" README.md orbiter_web.html
```

Ожидаемо: формулировки различают interpolation/display smoothing и physical
propagation accuracy.

## Задача 5: Браузерная проверка с локальным сервером

**Файлы:**
- Изменения source files не ожидаются.

- [ ] **Шаг 1: Запустить локальный app server**

Выполнить:

```powershell
venv\Scripts\python.exe third.py --no-browser --port 8770
```

Ожидаемо: сервер печатает URL вроде `http://127.0.0.1:8770/orbiter_web.html` и
продолжает работать.

- [ ] **Шаг 2: Выполнить desktop verification через Playwright MCP**

Открыть `http://127.0.0.1:8770/orbiter_web.html` через Playwright.

Проверить:

```text
- Нет console syntax errors.
- Canvas/WebGL scene видима и не пустая.
- Manual default orbit все еще рисуется.
- Real-time mode загружается с cached data, если `.orbiter_cache/` содержит valid payload.
- Если cache/network недоступны, UI показывает ошибку и не ломает manual scene.
```

- [ ] **Шаг 3: Выполнить mobile verification через Playwright MCP**

Поставить mobile viewport, например `390x844`.

Проверить:

```text
- Controls не перекрывают HUD/NORAD panel.
- Scene остается видимой в первом viewport.
- Real-time explanatory text не выходит за контейнер.
```

- [ ] **Шаг 4: Остановить локальный сервер**

Остановить процесс `third.py` через `Ctrl+C` в его terminal session.

Ожидаемо: не остается обязательных процессов проекта.

## Задача 6: Финальная проверка и commit

**Файлы:**
- Проверить все измененные source/doc files.

- [ ] **Шаг 1: Запустить lint и tests**

Выполнить:

```powershell
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
git diff --check
```

Ожидаемо:

```text
All checks passed!
15 passed
git diff --check exits 0
```

Если счетчик pytest изменится из-за добавленных тестов, сообщить новый счетчик
прошедших тестов.

- [ ] **Шаг 2: Проверить diff**

Выполнить:

```powershell
git diff -- orbiter_web.html README.md
```

Ожидаемо: diff содержит только interpolation/rendering/text changes из этого
плана.

- [ ] **Шаг 3: Закоммитить только implementation files**

Выполнить:

```powershell
git add orbiter_web.html README.md
git commit -m "fix: smooth realtime orbit display"
```

Если в `README.md` есть несвязанные pre-existing changes, stage только hunks
этой реализации через interactive или patch-based workflow и не stage
несвязанную работу пользователя.

## Самопроверка

Покрытие spec:

- Плавное real-time движение: задачи 2 и 3.
- Лучшая отрисовка orbit/trail: задача 3, особенно `currentRenderPointIndex()`
  и visual-state wiring.
- Четкое различие RK4 и SGP4: задача 4.
- Сохранение текущей архитектуры: структура файлов и все задачи не добавляют
  новые modules/dependencies.
- Сохранение CelesTrak cache behavior: server-side CelesTrak code не меняется.
- Проверка: задачи 5 и 6.

Проверка placeholders:

- Нет placeholder markers или undefined future module.
- Snippets определяют все новые function names до использования.

Согласованность типов:

- `activeVisualState` shape: `{ index, sample, utcMs, position, velocity, speed }`.
- `currentVisualState()`, `updateSatellite()`, `updateHud()`,
  `updateNoradPanel()` и `currentRenderPointIndex()` используют одинаковые
  property names.
