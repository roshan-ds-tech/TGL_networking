# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Running on a new machine

1. **Frontend** — `cp .env.example .env.local`, then `npm install && npm run dev` (http://localhost:5173).
2. **Backend** — follow `backend/README.md`: create the venv, `pip install -r requirements.txt`,
   copy `backend/.env.example` to `backend/.env` (set `SECRET_KEY`; `RESEND_API_KEY` is optional locally),
   run `create_admin.py`, then start uvicorn on port 8000.
3. **Admin dashboard** — `cd admin-dashboard && npm install && npm run build` (see backend README).

Secrets (`backend/.env`), the local database (`backend/var/`) and virtualenvs are intentionally not in git.
