import { test, expect } from '@playwright/test';

test.describe('Team Management', () => {
  test.beforeEach(async ({ page }) => {
    // ログイン
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword123');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
  });

  test('should create a new team', async ({ page }) => {
    await page.goto('/teams');

    // 新規チーム作成ボタンをクリック
    await page.click('[data-testid="create-team-button"]');

    // チーム情報を入力
    await page.fill('[data-testid="team-name-input"]', '新規テストチーム');
    await page.fill('[data-testid="team-description-input"]', 'テスト用のチームです');

    // 作成ボタンをクリック
    await page.click('[data-testid="submit-team-button"]');

    // 成功メッセージを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });

  test('should display team list', async ({ page }) => {
    await page.goto('/teams');

    // チームリストが表示されることを確認
    await expect(page.locator('[data-testid="team-list"]')).toBeVisible();
  });

  test('should view team details', async ({ page }) => {
    await page.goto('/teams');

    // チームをクリック
    await page.click('[data-testid="team-item"]:first-child');

    // 詳細画面が表示されることを確認
    await expect(page.locator('[data-testid="team-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="member-list"]')).toBeVisible();
  });

  test('should invite member to team', async ({ page }) => {
    await page.goto('/teams');
    await page.click('[data-testid="team-item"]:first-child');

    // 招待ボタンをクリック
    await page.click('[data-testid="invite-member-button"]');

    // メールアドレスを入力
    await page.fill('[data-testid="invite-email-input"]', 'newmember@example.com');

    // 役割を選択
    await page.selectOption('[data-testid="role-select"]', 'member');

    // 招待を送信
    await page.click('[data-testid="send-invite-button"]');

    // 成功メッセージを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });

  test('should update team settings', async ({ page }) => {
    await page.goto('/teams');
    await page.click('[data-testid="team-item"]:first-child');

    // 設定タブをクリック
    await page.click('[data-testid="settings-tab"]');

    // チーム名を変更
    await page.fill('[data-testid="team-name-input"]', '更新されたチーム名');
    await page.click('[data-testid="save-settings-button"]');

    // 更新が反映されることを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });

  test('should remove member from team', async ({ page }) => {
    await page.goto('/teams');
    await page.click('[data-testid="team-item"]:first-child');

    // メンバーの削除ボタンをクリック
    await page.click('[data-testid="member-item"]:last-child [data-testid="remove-member-button"]');

    // 確認ダイアログ
    await page.click('[data-testid="confirm-remove"]');

    // 削除されたことを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });
});

test.describe('Team Collaboration', () => {
  test('should share transcription with team', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // 共有ボタンをクリック
    await page.click('[data-testid="share-button"]');

    // チームを選択
    await page.selectOption('[data-testid="team-select"]', { index: 1 });

    // 権限を選択
    await page.selectOption('[data-testid="permission-select"]', 'edit');

    // 共有を実行
    await page.click('[data-testid="share-submit-button"]');

    // 成功メッセージを確認
    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });

  test('should add comment to transcription', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');

    // コメントタブを選択
    await page.click('[data-testid="comments-tab"]');

    // コメントを入力
    await page.fill('[data-testid="comment-input"]', 'これは重要なポイントです');

    // コメントを送信
    await page.click('[data-testid="submit-comment-button"]');

    // コメントが表示されることを確認
    await expect(page.locator('[data-testid="comment-item"]')).toBeVisible();
  });

  test('should reply to comment', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');
    await page.click('[data-testid="comments-tab"]');

    // 返信ボタンをクリック
    await page.click('[data-testid="comment-item"]:first-child [data-testid="reply-button"]');

    // 返信を入力
    await page.fill('[data-testid="reply-input"]', '返信コメントです');
    await page.click('[data-testid="submit-reply-button"]');

    // 返信が表示されることを確認
    await expect(page.locator('[data-testid="reply-item"]')).toBeVisible();
  });

  test('should resolve comment', async ({ page }) => {
    await page.goto('/transcriptions');
    await page.click('[data-testid="transcription-item"]:first-child');
    await page.click('[data-testid="comments-tab"]');

    // 解決ボタンをクリック
    await page.click('[data-testid="comment-item"]:first-child [data-testid="resolve-button"]');

    // コメントが解決済みになることを確認
    await expect(page.locator('[data-testid="comment-item"]:first-child')).toHaveClass(/resolved/);
  });
});
