import { test, expect } from '@playwright/test';

test.describe('Transcription Flow', () => {
  test.beforeEach(async ({ page }) => {
    // ログイン
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword123');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
  });

  test('should display transcription list', async ({ page }) => {
    await page.goto('/transcriptions');

    // リストが表示されることを確認
    await expect(page.locator('[data-testid="transcription-list"]')).toBeVisible();
  });

  test('should upload audio file and start transcription', async ({ page }) => {
    await page.goto('/transcriptions/new');

    // ファイルをアップロード
    const fileInput = page.locator('[data-testid="audio-file-input"]');
    await fileInput.setInputFiles({
      name: 'test-audio.mp3',
      mimeType: 'audio/mpeg',
      buffer: Buffer.from('mock audio content'),
    });

    // タイトルを入力
    await page.fill('[data-testid="title-input"]', 'テスト文字起こし');

    // 文字起こしを開始
    await page.click('[data-testid="start-transcription-button"]');

    // 処理中の表示を確認
    await expect(page.locator('[data-testid="processing-indicator"]')).toBeVisible();
  });

  test('should view transcription details', async ({ page }) => {
    // 既存の文字起こしがある前提
    await page.goto('/transcriptions');

    // 最初の項目をクリック
    await page.click('[data-testid="transcription-item"]:first-child');

    // 詳細画面に遷移
    await expect(page.locator('[data-testid="transcription-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="segment-list"]')).toBeVisible();
  });

  test('should edit transcription title', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // 編集ボタンをクリック
    await page.click('[data-testid="edit-button"]');

    // タイトルを変更
    await page.fill('[data-testid="title-input"]', '更新されたタイトル');
    await page.click('[data-testid="save-button"]');

    // 更新が反映されることを確認
    await expect(page.locator('[data-testid="transcription-title"]')).toHaveText('更新されたタイトル');
  });

  test('should export transcription as SRT', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // エクスポートメニューを開く
    await page.click('[data-testid="export-button"]');

    // SRT形式を選択
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.click('[data-testid="export-srt"]'),
    ]);

    // ダウンロードされたファイルを確認
    expect(download.suggestedFilename()).toMatch(/\.srt$/);
  });

  test('should search within transcription', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // 検索ボックスに入力
    await page.fill('[data-testid="search-input"]', 'よろしく');

    // 検索結果がハイライトされることを確認
    await expect(page.locator('.search-highlight')).toBeVisible();
  });

  test('should delete transcription', async ({ page }) => {
    await page.goto('/transcriptions');

    // 削除ボタンをクリック
    await page.click('[data-testid="transcription-item"]:first-child [data-testid="delete-button"]');

    // 確認ダイアログ
    await page.click('[data-testid="confirm-delete"]');

    // 削除されたことを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });
});

test.describe('Audio Player', () => {
  test('should play and pause audio', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // 再生ボタンをクリック
    await page.click('[data-testid="play-button"]');
    await expect(page.locator('[data-testid="pause-button"]')).toBeVisible();

    // 一時停止ボタンをクリック
    await page.click('[data-testid="pause-button"]');
    await expect(page.locator('[data-testid="play-button"]')).toBeVisible();
  });

  test('should seek to segment on click', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // セグメントをクリック
    await page.click('[data-testid="segment-item"]:nth-child(2)');

    // プレイヤーの位置が変わることを確認
    const currentTime = await page.locator('[data-testid="current-time"]').textContent();
    expect(currentTime).not.toBe('00:00');
  });
});
