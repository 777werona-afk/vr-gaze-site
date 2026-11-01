# ERD: VR-музей, стабилизация взгляда

Диаграмма на Mermaid (на GitHub отображается автоматически). Схема создаётся и меняется только
миграциями Alembic: `migrations/versions/c3f81d2a9b64_vr_gaze_domain.py`.

```mermaid
erDiagram
    PARTICIPANT_GROUPS ||--o{ PARTICIPANTS : "1:N"
    PARTICIPANTS ||--o{ GAZE_SESSIONS : "1:N"
    GAZE_SESSIONS ||--o{ GAZE_SAMPLES : "1:N"
    GAZE_SESSIONS ||--o{ EXHIBIT_VIEWS : "N:M"
    EXHIBITS ||--o{ EXHIBIT_VIEWS : "N:M"

    PARTICIPANT_GROUPS {
        int id PK
        string name UK "NOT NULL"
        text description
        bool is_control "NOT NULL, default false"
        timestamptz created_at
    }
    PARTICIPANTS {
        int id PK
        string code UK "NOT NULL, CHECK length > 0"
        int group_id FK "NOT NULL, ON DELETE RESTRICT"
        timestamptz created_at
    }
    EXHIBITS {
        int id PK
        string title UK "NOT NULL"
        string hall
        int dwell_threshold_ms "CHECK > 0, default 1000"
    }
    GAZE_SESSIONS {
        int id PK
        int participant_id FK "NOT NULL, ON DELETE RESTRICT"
        string status "CHECK IN (created, recorded, checked, in_dataset, rejected)"
        string source_file
        string source_sha256 UK "идемпотентность ETL"
        timestamptz recorded_at
        int total_rows "CHECK valid_rows <= total_rows"
        int valid_rows
        float valid_pct "CHECK 0..100"
        float fs_hz
        float duration_s
        float tremor_rms_deg "RMS в полосе 4-12 Гц"
        bool destabilized "итог: да / нет / не оценено"
        string reject_reason
    }
    GAZE_SAMPLES {
        bigint id PK
        int session_id FK "ON DELETE CASCADE"
        float t_s "UNIQUE (session_id, t_s)"
        float x
        float y
        float z
        float pupil
        float openness
    }
    EXHIBIT_VIEWS {
        int session_id PK, FK "ON DELETE CASCADE"
        int exhibit_id PK, FK "ON DELETE CASCADE"
        int dwell_ms "CHECK > 0"
        int views_count "CHECK >= 1"
    }
```

## Сущности

| Таблица | Назначение | Связи |
|---|---|---|
| `participant_groups` | группа участников (с нарушениями моторики, контрольная) | 1 : N участников |
| `participants` | участник записи, только код без персональных данных | 1 : N сессий |
| `gaze_sessions` | сессия записи взгляда, её качество и итог «дестабилизация: да/нет» | 1 : N отсчётов |
| `gaze_samples` | один отсчёт лога взгляда (строка CSV после очистки) | принадлежит сессии |
| `exhibits` | экспонат музея с порогом dwell-click | N : M с сессиями |
| `exhibit_views` | ассоциативная таблица: сколько взгляд удерживался на экспонате в сессии | связывает сессии и экспонаты |

## Индексы

- уникальные индексы по `participant_groups.name`, `participants.code`, `exhibits.title`;
- `participants.group_id`, `gaze_sessions.participant_id`, `gaze_sessions.status`: фильтрация списков;
- `exhibit_views.exhibit_id`: аналитика по экспонатам; `gaze_samples (session_id, t_s)` уникален и
  одновременно служит индексом для выборки отсчётов сессии по порядку времени.
