import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileAudio, X, AlertCircle } from 'lucide-react';
import { cn, formatFileSize, getFileExtension } from '../../lib/utils';
import { Button } from '../ui/Button';

interface DropzoneProps {
  onFileSelect: (file: File) => void;
  isUploading?: boolean;
  uploadProgress?: number;
  error?: string | null;
  maxSize?: number; // bytes
  acceptedFormats?: string[];
}

const DEFAULT_ACCEPTED_FORMATS = ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'webm'];
const DEFAULT_MAX_SIZE = 500 * 1024 * 1024; // 500MB

export function Dropzone({
  onFileSelect,
  isUploading = false,
  uploadProgress = 0,
  error = null,
  maxSize = DEFAULT_MAX_SIZE,
  acceptedFormats = DEFAULT_ACCEPTED_FORMATS,
}: DropzoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      setValidationError(null);
      const file = acceptedFiles[0];

      if (!file) return;

      // ファイル形式チェック
      const ext = getFileExtension(file.name);
      if (!acceptedFormats.includes(ext)) {
        setValidationError(
          `対応していないファイル形式です。対応形式: ${acceptedFormats.join(', ')}`
        );
        return;
      }

      // ファイルサイズチェック
      if (file.size > maxSize) {
        setValidationError(
          `ファイルサイズが大きすぎます。最大: ${formatFileSize(maxSize)}`
        );
        return;
      }

      setSelectedFile(file);
    },
    [acceptedFormats, maxSize]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'audio/*': acceptedFormats.map((f) => `.${f}`),
    },
    maxFiles: 1,
    disabled: isUploading,
  });

  const handleClear = () => {
    setSelectedFile(null);
    setValidationError(null);
  };

  const handleUpload = () => {
    if (selectedFile) {
      onFileSelect(selectedFile);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {!selectedFile ? (
        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors',
            isDragActive
              ? 'border-primary-500 bg-primary-50'
              : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50',
            isUploading && 'opacity-50 cursor-not-allowed'
          )}
        >
          <input {...getInputProps()} />
          <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
          <p className="text-lg font-medium text-gray-700 mb-2">
            {isDragActive
              ? 'ファイルをドロップしてください'
              : '音声ファイルをドラッグ＆ドロップ'}
          </p>
          <p className="text-sm text-gray-500 mb-4">
            または<span className="text-primary-600 font-medium">クリック</span>
            してファイルを選択
          </p>
          <p className="text-xs text-gray-400">
            対応形式: {acceptedFormats.join(', ').toUpperCase()} / 最大{' '}
            {formatFileSize(maxSize)}
          </p>
        </div>
      ) : (
        <div className="border rounded-xl p-6 bg-white">
          <div className="flex items-center gap-4">
            <div className="flex-shrink-0 w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center">
              <FileAudio className="w-6 h-6 text-primary-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-gray-900 truncate">{selectedFile.name}</p>
              <p className="text-sm text-gray-500">{formatFileSize(selectedFile.size)}</p>
            </div>
            {!isUploading && (
              <button
                onClick={handleClear}
                className="p-2 text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>

          {isUploading && (
            <div className="mt-4">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">アップロード中...</span>
                <span className="text-gray-600">{uploadProgress}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {!isUploading && (
            <div className="mt-4 flex gap-3">
              <Button onClick={handleUpload} className="flex-1">
                文字起こしを開始
              </Button>
              <Button variant="secondary" onClick={handleClear}>
                キャンセル
              </Button>
            </div>
          )}
        </div>
      )}

      {(validationError || error) && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-600">{validationError || error}</p>
        </div>
      )}
    </div>
  );
}
