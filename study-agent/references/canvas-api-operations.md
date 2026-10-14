# Canvas API operations

The workflow uses a personal Canvas access token and only read endpoints. The base URL is the institution-hosted Canvas root, such as `https://canvas.example.edu`; API paths are appended beneath `/api/v1`.

## Required environment

- `CANVAS_BASE_URL`: Canvas root URL, no trailing slash.
- `CANVAS_API_TOKEN`: personal access token with permission to read the student's courses and calendar. Keep it in the shell or a secret manager, never in source control or a snapshot.

The helper sends the token as `Authorization: Bearer <token>`. A 401/403 generally means the token is invalid, expired, or lacks access. Stop and have the student check the institution's Canvas token settings; do not ask them to paste the token into chat.

## Endpoints collected

| Endpoint | Purpose |
| --- | --- |
| `GET /users/self/courses` | Current courses and basic course metadata. |
| `GET /courses/:course_id/assignments` | Assignments, due dates, submission state, and points. |
| `GET /courses/:course_id/modules` | Published module structure and items. |
| `GET /calendar_events` | Dated calendar items inside the selected range. |

Canvas paginates responses through RFC-style `Link` headers. Follow `rel="next"` until none remains. Course/module visibility varies by institution and enrollment; absent data is not evidence that the work does not exist.

## Date behavior

Canvas returns timestamps in ISO 8601. The helper requests calendar events over an inclusive `--start` / `--end` range and retains assignments that are due within that range plus overdue, unsubmitted assignments. `--start` and `--end` use `YYYY-MM-DD`; an omitted range defaults to today through seven days later according to the machine's local date.

## Planning interpretation

- An overdue, unsubmitted assignment is urgent regardless of the requested date window.
- Due dates organize work; `points_possible` is only a rough signal of importance, not an estimate of study time.
- Module item URLs identify structure but should not be fetched indiscriminately. Fetch their contents only if the student asks for a specific course item or it is needed to clarify a scheduled task.
- Preserve uncertainty: mark missing due dates, unpublished material, and unavailable courses explicitly.
