# 🧪 Tests

Test suites for all project modules.

## Structure

| Directory      | Description                    |
|----------------|--------------------------------|
| frontend/      | React component & page tests   |
| backend/       | FastAPI endpoint & service tests|
| integration/   | End-to-end integration tests   |
| ai/            | AI service accuracy tests      |
| performance/   | Load & performance tests       |

## Running Tests

```bash
# All tests
./scripts/run-tests.sh

# Backend only
cd backend && pytest

# Frontend only
cd frontend && npm test
```
