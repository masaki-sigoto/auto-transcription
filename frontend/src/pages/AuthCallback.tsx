import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FileAudio, AlertCircle } from 'lucide-react';
import { handleOAuthCallback } from '../stores/authStore';

export function AuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const processCallback = async () => {
      const accessToken = searchParams.get('access_token');
      const refreshToken = searchParams.get('refresh_token');
      const errorParam = searchParams.get('error');

      if (errorParam) {
        setError(decodeURIComponent(errorParam));
        return;
      }

      if (!accessToken || !refreshToken) {
        setError('認証情報が見つかりません');
        return;
      }

      try {
        await handleOAuthCallback(accessToken, refreshToken);
        navigate('/', { replace: true });
      } catch (err: any) {
        setError(err.message || '認証処理中にエラーが発生しました');
      }
    };

    processCallback();
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="flex justify-center">
            <div className="w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center">
              <AlertCircle className="w-7 h-7 text-red-600" />
            </div>
          </div>
          <h2 className="mt-6 text-center text-2xl font-bold text-gray-900">
            認証エラー
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {error}
          </p>
          <div className="mt-6 text-center">
            <button
              onClick={() => navigate('/login')}
              className="text-primary-600 hover:text-primary-500 font-medium"
            >
              ログインページに戻る
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <div className="w-12 h-12 bg-primary-600 rounded-xl flex items-center justify-center">
            <FileAudio className="w-7 h-7 text-white" />
          </div>
        </div>
        <h2 className="mt-6 text-center text-2xl font-bold text-gray-900">
          認証処理中...
        </h2>
        <div className="mt-6 flex justify-center">
          <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full" />
        </div>
        <p className="mt-4 text-center text-sm text-gray-600">
          しばらくお待ちください
        </p>
      </div>
    </div>
  );
}
