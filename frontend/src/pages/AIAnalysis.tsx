import { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Brain,
  FileText,
  Heart,
  Tag,
  MessageCircle,
  Loader2,
  CheckCircle,
  AlertCircle,
  Sparkles,
  Users,
  ListChecks,
  Target,
} from 'lucide-react';

interface MeetingMinutes {
  title: string;
  date: string;
  participants: string[];
  summary: string;
  key_points: string[];
  action_items: Array<{
    task: string;
    assignee?: string;
    deadline?: string;
  }>;
  decisions: string[];
  next_steps: string[];
}

interface SentimentResult {
  overall_sentiment: string;
  sentiment_score: number;
  segments: Array<{
    segment_id: string;
    text: string;
    sentiment: string;
    score: number;
  }>;
}

interface KeywordResult {
  keywords: Array<{
    word: string;
    frequency: number;
    importance: number;
  }>;
  topics: Array<{
    topic: string;
    keywords: string[];
  }>;
  entities: Array<{
    name: string;
    type: string;
    count: number;
  }>;
}

interface QAResult {
  question: string;
  answer: string;
  confidence: number;
  relevant_segments: Array<{
    text: string;
    start_time_ms: number;
  }>;
}

type AnalysisType = 'minutes' | 'sentiment' | 'keywords' | 'qa' | 'summary';

export default function AIAnalysis() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<AnalysisType>('minutes');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [minutes, setMinutes] = useState<MeetingMinutes | null>(null);
  const [sentiment, setSentiment] = useState<SentimentResult | null>(null);
  const [keywords, setKeywords] = useState<KeywordResult | null>(null);
  const [qaResult, setQaResult] = useState<QAResult | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [question, setQuestion] = useState('');

  const runAnalysis = async (type: AnalysisType) => {
    setLoading(true);
    setError(null);

    try {
      let endpoint = '';
      let method = 'POST';
      let body: any = undefined;

      switch (type) {
        case 'minutes':
          endpoint = `/api/v1/ai/transcriptions/${id}/minutes`;
          break;
        case 'sentiment':
          endpoint = `/api/v1/ai/transcriptions/${id}/sentiment`;
          break;
        case 'keywords':
          endpoint = `/api/v1/ai/transcriptions/${id}/keywords`;
          break;
        case 'qa':
          endpoint = `/api/v1/ai/transcriptions/${id}/question`;
          body = JSON.stringify({ question });
          break;
        case 'summary':
          endpoint = `/api/v1/ai/transcriptions/${id}/summary`;
          body = JSON.stringify({ style: 'detailed' });
          break;
      }

      const response = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body,
      });

      if (!response.ok) throw new Error('Analysis failed');

      const data = await response.json();

      switch (type) {
        case 'minutes':
          setMinutes(data);
          break;
        case 'sentiment':
          setSentiment(data);
          break;
        case 'keywords':
          setKeywords(data);
          break;
        case 'qa':
          setQaResult(data);
          break;
        case 'summary':
          setSummary(data.summary);
          break;
      }
    } catch (err) {
      setError('分析に失敗しました。再度お試しください。');
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'positive':
        return 'text-green-600 bg-green-100';
      case 'negative':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const tabs = [
    { id: 'minutes', label: '議事録', icon: FileText },
    { id: 'sentiment', label: '感情分析', icon: Heart },
    { id: 'keywords', label: 'キーワード', icon: Tag },
    { id: 'qa', label: '質問応答', icon: MessageCircle },
    { id: 'summary', label: '要約', icon: Sparkles },
  ];

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="p-3 bg-indigo-100 rounded-lg">
            <Brain className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">AI分析</h1>
            <p className="text-gray-500">AIによる高度な文字起こし分析</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as AnalysisType)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600" />
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {/* Content */}
        <div className="bg-white rounded-lg shadow-sm border p-6">
          {/* Minutes Tab */}
          {activeTab === 'minutes' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-semibold">議事録自動生成</h2>
                <button
                  onClick={() => runAnalysis('minutes')}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4" />
                  )}
                  生成
                </button>
              </div>

              {minutes && (
                <div className="space-y-6">
                  <div>
                    <h3 className="font-medium text-gray-900 mb-2">
                      {minutes.title}
                    </h3>
                    <p className="text-sm text-gray-500">{minutes.date}</p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                      <Sparkles className="w-4 h-4" />
                      要約
                    </h4>
                    <p className="text-gray-600">{minutes.summary}</p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                      <Target className="w-4 h-4" />
                      重要ポイント
                    </h4>
                    <ul className="list-disc list-inside space-y-1">
                      {minutes.key_points.map((point, i) => (
                        <li key={i} className="text-gray-600">
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                      <ListChecks className="w-4 h-4" />
                      アクションアイテム
                    </h4>
                    <div className="space-y-2">
                      {minutes.action_items.map((item, i) => (
                        <div
                          key={i}
                          className="p-3 bg-gray-50 rounded-lg flex items-start gap-3"
                        >
                          <CheckCircle className="w-5 h-5 text-green-600 mt-0.5" />
                          <div>
                            <p className="text-gray-900">{item.task}</p>
                            {item.assignee && (
                              <p className="text-sm text-gray-500">
                                担当: {item.assignee}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2">決定事項</h4>
                    <ul className="list-disc list-inside space-y-1">
                      {minutes.decisions.map((decision, i) => (
                        <li key={i} className="text-gray-600">
                          {decision}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Sentiment Tab */}
          {activeTab === 'sentiment' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-semibold">感情分析</h2>
                <button
                  onClick={() => runAnalysis('sentiment')}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Heart className="w-4 h-4" />
                  )}
                  分析
                </button>
              </div>

              {sentiment && (
                <div className="space-y-6">
                  <div className="flex items-center gap-4">
                    <div
                      className={`px-4 py-2 rounded-full ${getSentimentColor(sentiment.overall_sentiment)}`}
                    >
                      {sentiment.overall_sentiment === 'positive'
                        ? 'ポジティブ'
                        : sentiment.overall_sentiment === 'negative'
                        ? 'ネガティブ'
                        : '中立'}
                    </div>
                    <div className="text-gray-600">
                      スコア: {sentiment.sentiment_score.toFixed(2)}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2">
                      セグメントごとの感情
                    </h4>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {sentiment.segments.map((seg, i) => (
                        <div key={i} className="flex items-center gap-3 p-2 border-b">
                          <span
                            className={`px-2 py-1 rounded text-xs ${getSentimentColor(seg.sentiment)}`}
                          >
                            {seg.sentiment}
                          </span>
                          <span className="text-gray-600 text-sm truncate">
                            {seg.text}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Keywords Tab */}
          {activeTab === 'keywords' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-semibold">キーワード抽出</h2>
                <button
                  onClick={() => runAnalysis('keywords')}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Tag className="w-4 h-4" />
                  )}
                  抽出
                </button>
              </div>

              {keywords && (
                <div className="space-y-6">
                  <div>
                    <h4 className="font-medium text-gray-700 mb-3">
                      重要キーワード
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {keywords.keywords.map((kw, i) => (
                        <span
                          key={i}
                          className="px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm"
                          style={{
                            opacity: 0.5 + kw.importance * 0.5,
                          }}
                        >
                          {kw.word}
                          <span className="ml-1 text-indigo-400">
                            ({kw.frequency})
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-3">トピック</h4>
                    <div className="space-y-3">
                      {keywords.topics.map((topic, i) => (
                        <div key={i} className="p-3 bg-gray-50 rounded-lg">
                          <p className="font-medium text-gray-900">
                            {topic.topic}
                          </p>
                          <p className="text-sm text-gray-500 mt-1">
                            {topic.keywords.join(', ')}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-3">固有表現</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {keywords.entities.map((entity, i) => (
                        <div
                          key={i}
                          className="flex justify-between p-2 bg-gray-50 rounded"
                        >
                          <span className="text-gray-900">{entity.name}</span>
                          <span className="text-xs text-gray-500">
                            {entity.type} ({entity.count})
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* QA Tab */}
          {activeTab === 'qa' && (
            <div>
              <h2 className="text-lg font-semibold mb-6">質問応答</h2>

              <div className="space-y-4">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="文字起こしについて質問..."
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && question) {
                        runAnalysis('qa');
                      }
                    }}
                  />
                  <button
                    onClick={() => runAnalysis('qa')}
                    disabled={loading || !question}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {loading ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                      <MessageCircle className="w-5 h-5" />
                    )}
                  </button>
                </div>

                {qaResult && (
                  <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                    <p className="font-medium text-gray-900 mb-2">
                      Q: {qaResult.question}
                    </p>
                    <p className="text-gray-700 mb-4">A: {qaResult.answer}</p>
                    <div className="text-sm text-gray-500">
                      信頼度: {(qaResult.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Summary Tab */}
          {activeTab === 'summary' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-semibold">要約生成</h2>
                <button
                  onClick={() => runAnalysis('summary')}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  生成
                </button>
              </div>

              {summary && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-gray-700 whitespace-pre-wrap">{summary}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
