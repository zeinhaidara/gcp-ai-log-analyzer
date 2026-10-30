# API

## Dashboard

`GET /health`, `POST /logs`, `GET /logs`, `GET /logs/{id}`, `GET /logs/{id}/replay`, `GET|POST /logs/{id}/investigation`, `GET|POST /investigations/{id}`, `GET /analytics`, `GET /replay/demo/{name}`.

The dashboard is public and unauthenticated.

## Agent (IAM required)

- `GET /health`: liveness, no cloud calls.
- `GET /ready`: reads one Firestore document, the raw-log bucket's metadata and the incidents table's metadata, concurrently, 2 seconds each. Returns 200 `ready` or 503 `not_ready`, with only `ok` or `failed` per check.
- `POST /pubsub`: Pub/Sub push receiver.
