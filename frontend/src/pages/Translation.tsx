import { useState, useEffect } from 'react';
import {
  Globe,
  ArrowRight,
  Copy,
  Check,
  Languages,
  Loader2,
  RefreshCw,
} from 'lucide-react';

interface Language {
  code: string;
  name: string;
}

interface TranslationResult {
  original_text: string;
  translated_text: string;
  source_language: string;
  target_language: string;
}

export default function Translation() {
  const [languages, setLanguages] = useState<Language[]>([]);
  const [sourceText, setSourceText] = useState('');
  const [translatedText, setTranslatedText] = useState('');
  const [sourceLanguage, setSourceLanguage] = useState<string>('auto');
  const [targetLanguage, setTargetLanguage] = useState<string>('en');
  const [isTranslating, setIsTranslating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [suggestedLanguages, setSuggestedLanguages] = useState<Language[]>([]);

  useEffect(() => {
    fetchLanguages();
  }, []);

  useEffect(() => {
    if (sourceLanguage !== 'auto') {
      fetchSuggestions(sourceLanguage);
    }
  }, [sourceLanguage]);

  const fetchLanguages = async () => {
    try {
      const response = await fetch('/api/v1/translation/languages');
      const data = await response.json();
      setLanguages(data);
    } catch (error) {
      console.error('Failed to fetch languages:', error);
    }
  };

  const fetchSuggestions = async (lang: string) => {
    try {
      const response = await fetch(
        `/api/v1/translation/suggest?source_language=${lang}`
      );
      const data = await response.json();
      setSuggestedLanguages(data.suggested_languages);
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    }
  };

  const handleTranslate = async () => {
    if (!sourceText.trim()) return;

    setIsTranslating(true);
    try {
      const response = await fetch('/api/v1/translation/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: sourceText,
          target_language: targetLanguage,
          source_language: sourceLanguage === 'auto' ? null : sourceLanguage,
        }),
      });

      const data: TranslationResult = await response.json();
      setTranslatedText(data.translated_text);

      // 自動検出の場合、検出された言語を設定
      if (sourceLanguage === 'auto' && data.source_language !== 'auto') {
        setSourceLanguage(data.source_language);
      }
    } catch (error) {
      console.error('Translation failed:', error);
    } finally {
      setIsTranslating(false);
    }
  };

  const handleDetectLanguage = async () => {
    if (!sourceText.trim()) return;

    try {
      const response = await fetch('/api/v1/translation/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sourceText }),
      });

      const data = await response.json();
      setSourceLanguage(data.language);
    } catch (error) {
      console.error('Language detection failed:', error);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(translatedText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSwapLanguages = () => {
    if (sourceLanguage !== 'auto') {
      const temp = sourceLanguage;
      setSourceLanguage(targetLanguage);
      setTargetLanguage(temp);
      setSourceText(translatedText);
      setTranslatedText(sourceText);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="p-3 bg-purple-100 rounded-lg">
            <Globe className="w-6 h-6 text-purple-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">翻訳</h1>
            <p className="text-gray-500">テキストや文字起こしを翻訳</p>
          </div>
        </div>

        {/* Language Selector */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              翻訳元
            </label>
            <select
              value={sourceLanguage}
              onChange={(e) => setSourceLanguage(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              <option value="auto">自動検出</option>
              {languages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleSwapLanguages}
            disabled={sourceLanguage === 'auto'}
            className="mt-6 p-2 hover:bg-gray-100 rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className="w-5 h-5 text-gray-600" />
          </button>

          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              翻訳先
            </label>
            <select
              value={targetLanguage}
              onChange={(e) => setTargetLanguage(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              {languages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Suggested Languages */}
        {suggestedLanguages.length > 0 && (
          <div className="mb-4">
            <p className="text-sm text-gray-500 mb-2">おすすめの翻訳先:</p>
            <div className="flex gap-2">
              {suggestedLanguages.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => setTargetLanguage(lang.code)}
                  className={`px-3 py-1 rounded-full text-sm ${
                    targetLanguage === lang.code
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {lang.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Translation Box */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Source Text */}
          <div className="relative">
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="翻訳するテキストを入力..."
              className="w-full h-64 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
            />
            <div className="absolute bottom-3 right-3 flex gap-2">
              <button
                onClick={handleDetectLanguage}
                className="p-2 text-gray-400 hover:text-gray-600"
                title="言語を検出"
              >
                <Languages className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Translated Text */}
          <div className="relative">
            <div className="w-full h-64 p-4 bg-gray-50 border border-gray-300 rounded-lg overflow-auto">
              {isTranslating ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-purple-600" />
                </div>
              ) : translatedText ? (
                <p className="text-gray-900 whitespace-pre-wrap">
                  {translatedText}
                </p>
              ) : (
                <p className="text-gray-400">翻訳結果がここに表示されます</p>
              )}
            </div>
            {translatedText && (
              <button
                onClick={handleCopy}
                className="absolute bottom-3 right-3 p-2 text-gray-400 hover:text-gray-600"
                title="コピー"
              >
                {copied ? (
                  <Check className="w-5 h-5 text-green-600" />
                ) : (
                  <Copy className="w-5 h-5" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Translate Button */}
        <div className="mt-6 flex justify-center">
          <button
            onClick={handleTranslate}
            disabled={!sourceText.trim() || isTranslating}
            className="flex items-center gap-2 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isTranslating ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                翻訳中...
              </>
            ) : (
              <>
                <ArrowRight className="w-5 h-5" />
                翻訳
              </>
            )}
          </button>
        </div>

        {/* Translation Tips */}
        <div className="mt-8 p-4 bg-blue-50 rounded-lg">
          <h3 className="font-medium text-blue-900 mb-2">翻訳のヒント</h3>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>
              • 文字起こしの翻訳は、詳細ページの「翻訳」ボタンから行えます
            </li>
            <li>
              • リアルタイム翻訳は、文字起こし中に自動で翻訳を表示します
            </li>
            <li>• 翻訳した字幕は SRT/VTT 形式でダウンロードできます</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
