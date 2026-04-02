import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './App';
import { OrgProvider } from './context/OrgContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import '@/styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <OrgProvider>
          <RouterProvider router={router} />
        </OrgProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
