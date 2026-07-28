# 🖥️ Frontend — AI-Based Chartered Accountant

## Overview

The frontend application built with **React 18**, **TypeScript**, **Vite**, **Tailwind CSS**, and **shadcn/ui**. Provides a modern, responsive interface for accounting, GST, tax, audit, and AI-powered financial advisory.

## Directory Structure

```
frontend/
├── src/
│   ├── assets/              → Static assets (images, icons, fonts)
│   ├── components/          → Reusable UI components
│   │   ├── common/          → Shared components (Button, Input, etc.)
│   │   ├── layout/          → Layout components (Header, Sidebar, Footer)
│   │   ├── dashboard/       → Dashboard-specific components
│   │   ├── workspace/       → Workspace management components
│   │   ├── client/          → Client management components
│   │   ├── accounting/      → Accounting module components
│   │   ├── gst/             → GST filing & tracking components
│   │   ├── tax/             → Income tax components
│   │   ├── audit/           → Auditing components
│   │   ├── reports/         → Report generation components
│   │   ├── government/      → Government updates components
│   │   ├── chatbot/         → AI chatbot interface components
│   │   ├── ocr/             → OCR scanner components
│   │   ├── translation/     → Translation components
│   │   ├── forms/           → Form components
│   │   ├── tables/          → Data table components
│   │   ├── charts/          → Chart & visualization components
│   │   ├── modals/          → Modal/dialog components
│   │   └── ui/              → shadcn/ui base components
│   ├── pages/               → Route-level page components
│   ├── hooks/               → Custom React hooks
│   ├── contexts/            → React context providers
│   ├── services/            → API service layer
│   │   └── api/             → Axios API client & interceptors
│   ├── types/               → TypeScript type definitions
│   ├── routes/              → React Router configuration
│   ├── utils/               → Utility functions
│   ├── constants/           → App constants & enums
│   └── styles/              → Global styles & Tailwind config
├── public/                  → Public static files
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
└── Dockerfile
```

## Getting Started

```bash
cd frontend
npm install
npm run dev
```

## Available Scripts

| Command          | Description               |
|------------------|---------------------------|
| `npm run dev`    | Start development server  |
| `npm run build`  | Production build          |
| `npm run preview`| Preview production build  |
| `npm run lint`   | Run ESLint                |
| `npm test`       | Run tests                 |

## Developer Guidelines

- Follow component-per-file pattern
- Use TypeScript strict mode
- Colocate tests with components
- Use Zustand for global state
- Use React Hook Form + Zod for all forms
- Follow shadcn/ui patterns for UI components
