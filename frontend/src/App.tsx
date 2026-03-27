import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Upload } from './pages/Upload';
import { TranscriptionDetail } from './pages/TranscriptionDetail';
import { Settings } from './pages/Settings';
import { Login } from './pages/Login';
import { AuthCallback } from './pages/AuthCallback';
import { RealtimeTranscription } from './pages/RealtimeTranscription';
import Integrations from './pages/Integrations';
import Teams from './pages/Teams';
import Vocabulary from './pages/Vocabulary';
import Developer from './pages/Developer';
import Translation from './pages/Translation';
import { PWAPrompt } from './components/PWAPrompt';
import { useAuthStore } from './stores/authStore';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { initialize, isAuthenticated, isLoading } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="upload" element={<Upload />} />
        <Route path="realtime" element={<RealtimeTranscription />} />
        <Route path="transcriptions/:id" element={<TranscriptionDetail />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="teams" element={<Teams />} />
        <Route path="vocabulary" element={<Vocabulary />} />
        <Route path="developer" element={<Developer />} />
        <Route path="translation" element={<Translation />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
        <PWAPrompt />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
