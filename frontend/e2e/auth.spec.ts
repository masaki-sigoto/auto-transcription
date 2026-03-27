import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should display login page', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="email-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="password-input"]')).toBeVisible();
  });

  test('should show validation errors for empty form', async ({ page }) => {
    await page.goto('/login');

    await page.click('[data-testid="login-button"]');

    await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="password-error"]')).toBeVisible();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email-input"]', 'invalid@example.com');
    await page.fill('[data-testid="password-input"]', 'wrongpassword');
    await page.click('[data-testid="login-button"]');

    await expect(page.locator('[data-testid="login-error"]')).toBeVisible();
  });

  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword123');
    await page.click('[data-testid="login-button"]');

    await page.waitForURL('/dashboard');
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
  });

  test('should logout successfully', async ({ page }) => {
    // ログイン
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword123');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');

    // ログアウト
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-button"]');

    await page.waitForURL('/login');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
  });

  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/dashboard');

    await page.waitForURL('/login');
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
  });
});

test.describe('Registration', () => {
  test('should display registration page', async ({ page }) => {
    await page.goto('/register');

    await expect(page.locator('[data-testid="register-form"]')).toBeVisible();
  });

  test('should show validation errors for invalid input', async ({ page }) => {
    await page.goto('/register');

    await page.fill('[data-testid="email-input"]', 'invalid-email');
    await page.fill('[data-testid="password-input"]', '123');
    await page.click('[data-testid="register-button"]');

    await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="password-error"]')).toBeVisible();
  });

  test('should register successfully with valid input', async ({ page }) => {
    await page.goto('/register');

    const randomEmail = `test${Date.now()}@example.com`;

    await page.fill('[data-testid="name-input"]', 'テストユーザー');
    await page.fill('[data-testid="email-input"]', randomEmail);
    await page.fill('[data-testid="password-input"]', 'SecurePassword123!');
    await page.fill('[data-testid="confirm-password-input"]', 'SecurePassword123!');
    await page.click('[data-testid="register-button"]');

    // 登録成功後、ダッシュボードにリダイレクト
    await page.waitForURL('/dashboard');
  });

  test('should show error for password mismatch', async ({ page }) => {
    await page.goto('/register');

    await page.fill('[data-testid="name-input"]', 'テストユーザー');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'Password123!');
    await page.fill('[data-testid="confirm-password-input"]', 'DifferentPassword123!');
    await page.click('[data-testid="register-button"]');

    await expect(page.locator('[data-testid="password-mismatch-error"]')).toBeVisible();
  });
});

test.describe('Password Reset', () => {
  test('should display password reset page', async ({ page }) => {
    await page.goto('/forgot-password');

    await expect(page.locator('[data-testid="forgot-password-form"]')).toBeVisible();
  });

  test('should send password reset email', async ({ page }) => {
    await page.goto('/forgot-password');

    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.click('[data-testid="send-reset-button"]');

    await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
  });

  test('should show error for non-existent email', async ({ page }) => {
    await page.goto('/forgot-password');

    await page.fill('[data-testid="email-input"]', 'nonexistent@example.com');
    await page.click('[data-testid="send-reset-button"]');

    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
  });
});

test.describe('Profile Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword123');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
  });

  test('should display profile page', async ({ page }) => {
    await page.goto('/settings/profile');

    await expect(page.locator('[data-testid="profile-form"]')).toBeVisible();
  });

  test('should update profile information', async ({ page }) => {
    await page.goto('/settings/profile');

    await page.fill('[data-testid="name-input"]', '更新された名前');
    await page.click('[data-testid="save-profile-button"]');

    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });

  test('should change password', async ({ page }) => {
    await page.goto('/settings/security');

    await page.fill('[data-testid="current-password-input"]', 'testpassword123');
    await page.fill('[data-testid="new-password-input"]', 'NewPassword123!');
    await page.fill('[data-testid="confirm-new-password-input"]', 'NewPassword123!');
    await page.click('[data-testid="change-password-button"]');

    await expect(page.locator('[data-testid="success-toast"]')).toBeVisible();
  });
});
