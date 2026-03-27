"""請求・サブスクリプションサービス"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import stripe
from pydantic import BaseModel

from app.models.enterprise import (
    Organization,
    Subscription,
    SubscriptionPlan,
    UsageRecord,
    Invoice,
)
from app.core.config import get_settings

settings = get_settings()

# Stripe初期化
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)


class CreateSubscriptionRequest(BaseModel):
    """サブスクリプション作成リクエスト"""
    plan_id: UUID
    billing_cycle: str = "monthly"
    payment_method_id: Optional[str] = None


class BillingService:
    """請求サービス"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_plans(self, include_private: bool = False) -> list[SubscriptionPlan]:
        """プラン一覧を取得"""
        query = select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
        if not include_private:
            query = query.where(SubscriptionPlan.is_public == True)

        result = await self.db.execute(query.order_by(SubscriptionPlan.price_monthly))
        return list(result.scalars().all())

    async def get_subscription(
        self, organization_id: UUID
    ) -> Optional[Subscription]:
        """組織のサブスクリプションを取得"""
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def create_subscription(
        self,
        organization_id: UUID,
        request: CreateSubscriptionRequest,
    ) -> Subscription:
        """サブスクリプションを作成"""
        # 組織を取得
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise ValueError("Organization not found")

        # プランを取得
        result = await self.db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == request.plan_id)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            raise ValueError("Plan not found")

        # Stripeカスタマーを取得または作成
        if not org.stripe_customer_id:
            customer = stripe.Customer.create(
                metadata={"organization_id": str(organization_id)},
            )
            org.stripe_customer_id = customer.id
            await self.db.flush()

        # 支払い方法を設定
        if request.payment_method_id:
            stripe.PaymentMethod.attach(
                request.payment_method_id,
                customer=org.stripe_customer_id,
            )
            stripe.Customer.modify(
                org.stripe_customer_id,
                invoice_settings={"default_payment_method": request.payment_method_id},
            )

        # Stripeサブスクリプションを作成
        price_id = (
            plan.stripe_price_id_yearly
            if request.billing_cycle == "yearly"
            else plan.stripe_price_id_monthly
        )

        stripe_sub = stripe.Subscription.create(
            customer=org.stripe_customer_id,
            items=[{"price": price_id}],
            metadata={"organization_id": str(organization_id)},
        )

        # サブスクリプションを保存
        subscription = Subscription(
            organization_id=organization_id,
            plan_id=plan.id,
            stripe_subscription_id=stripe_sub.id,
            stripe_customer_id=org.stripe_customer_id,
            billing_cycle=request.billing_cycle,
            current_period_start=datetime.fromtimestamp(
                stripe_sub.current_period_start
            ),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
            status=stripe_sub.status,
        )

        self.db.add(subscription)

        # 組織のプランを更新
        org.plan = plan.slug
        org.stripe_subscription_id = stripe_sub.id
        org.max_users = plan.max_users
        org.max_storage_gb = plan.max_storage_gb
        org.max_transcription_hours = plan.max_transcription_hours_monthly

        await self.db.commit()
        await self.db.refresh(subscription)

        return subscription

    async def cancel_subscription(
        self,
        organization_id: UUID,
        at_period_end: bool = True,
    ) -> Subscription:
        """サブスクリプションをキャンセル"""
        subscription = await self.get_subscription(organization_id)
        if not subscription:
            raise ValueError("Subscription not found")

        if at_period_end:
            # 期間終了時にキャンセル
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True,
            )
            subscription.cancel_at_period_end = True
        else:
            # 即座にキャンセル
            stripe.Subscription.delete(subscription.stripe_subscription_id)
            subscription.status = "canceled"
            subscription.canceled_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(subscription)

        return subscription

    async def change_plan(
        self,
        organization_id: UUID,
        new_plan_id: UUID,
    ) -> Subscription:
        """プランを変更"""
        subscription = await self.get_subscription(organization_id)
        if not subscription:
            raise ValueError("Subscription not found")

        # 新しいプランを取得
        result = await self.db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == new_plan_id)
        )
        new_plan = result.scalar_one_or_none()
        if not new_plan:
            raise ValueError("New plan not found")

        # Stripeサブスクリプションを更新
        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
        price_id = (
            new_plan.stripe_price_id_yearly
            if subscription.billing_cycle == "yearly"
            else new_plan.stripe_price_id_monthly
        )

        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[
                {
                    "id": stripe_sub["items"]["data"][0].id,
                    "price": price_id,
                }
            ],
            proration_behavior="create_prorations",
        )

        subscription.plan_id = new_plan.id

        # 組織の制限を更新
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one()
        org.plan = new_plan.slug
        org.max_users = new_plan.max_users
        org.max_storage_gb = new_plan.max_storage_gb
        org.max_transcription_hours = new_plan.max_transcription_hours_monthly

        await self.db.commit()
        await self.db.refresh(subscription)

        return subscription

    async def record_usage(
        self,
        organization_id: UUID,
        usage_type: str,
        quantity: Decimal,
        unit: str,
    ) -> UsageRecord:
        """使用量を記録"""
        subscription = await self.get_subscription(organization_id)

        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)

        usage_record = UsageRecord(
            organization_id=organization_id,
            subscription_id=subscription.id if subscription else None,
            usage_type=usage_type,
            quantity=quantity,
            unit=unit,
            period_start=period_start,
            period_end=period_end,
        )

        self.db.add(usage_record)
        await self.db.commit()
        await self.db.refresh(usage_record)

        # Stripeに使用量を報告（従量課金の場合）
        if subscription and subscription.stripe_subscription_id:
            try:
                stripe.SubscriptionItem.create_usage_record(
                    subscription.stripe_subscription_id,
                    quantity=int(quantity),
                    timestamp=int(now.timestamp()),
                )
                usage_record.reported_to_stripe = True
                await self.db.commit()
            except Exception:
                pass  # 従量課金でない場合はエラーを無視

        return usage_record

    async def get_usage_summary(
        self,
        organization_id: UUID,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> dict:
        """使用量サマリーを取得"""
        if not period_start:
            now = datetime.utcnow()
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not period_end:
            period_end = datetime.utcnow()

        result = await self.db.execute(
            select(UsageRecord)
            .where(UsageRecord.organization_id == organization_id)
            .where(UsageRecord.period_start >= period_start)
            .where(UsageRecord.period_end <= period_end)
        )
        records = result.scalars().all()

        # 使用量を集計
        summary = {
            "transcription_seconds": Decimal(0),
            "storage_bytes": Decimal(0),
            "api_calls": Decimal(0),
        }

        for record in records:
            if record.usage_type == "transcription":
                summary["transcription_seconds"] += record.quantity
            elif record.usage_type == "storage":
                summary["storage_bytes"] += record.quantity
            elif record.usage_type == "api_calls":
                summary["api_calls"] += record.quantity

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "transcription_hours": float(summary["transcription_seconds"] / 3600),
            "storage_gb": float(summary["storage_bytes"] / (1024**3)),
            "api_calls": int(summary["api_calls"]),
        }

    async def get_invoices(
        self,
        organization_id: UUID,
        limit: int = 10,
    ) -> list[Invoice]:
        """請求書一覧を取得"""
        result = await self.db.execute(
            select(Invoice)
            .where(Invoice.organization_id == organization_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def sync_invoices_from_stripe(
        self,
        organization_id: UUID,
    ) -> list[Invoice]:
        """Stripeから請求書を同期"""
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()

        if not org or not org.stripe_customer_id:
            return []

        stripe_invoices = stripe.Invoice.list(
            customer=org.stripe_customer_id,
            limit=20,
        )

        invoices = []
        for stripe_inv in stripe_invoices.data:
            # 既存の請求書を確認
            result = await self.db.execute(
                select(Invoice).where(Invoice.stripe_invoice_id == stripe_inv.id)
            )
            invoice = result.scalar_one_or_none()

            if not invoice:
                invoice = Invoice(
                    organization_id=organization_id,
                    stripe_invoice_id=stripe_inv.id,
                )
                self.db.add(invoice)

            # 更新
            invoice.subtotal = Decimal(stripe_inv.subtotal) / 100
            invoice.tax = Decimal(stripe_inv.tax or 0) / 100
            invoice.total = Decimal(stripe_inv.total) / 100
            invoice.currency = stripe_inv.currency.upper()
            invoice.status = stripe_inv.status
            invoice.invoice_pdf_url = stripe_inv.invoice_pdf

            if stripe_inv.period_start:
                invoice.period_start = datetime.fromtimestamp(stripe_inv.period_start)
            if stripe_inv.period_end:
                invoice.period_end = datetime.fromtimestamp(stripe_inv.period_end)
            if stripe_inv.due_date:
                invoice.due_date = datetime.fromtimestamp(stripe_inv.due_date)
            if stripe_inv.status == "paid":
                invoice.paid_at = datetime.fromtimestamp(
                    stripe_inv.status_transitions.paid_at
                )

            invoices.append(invoice)

        await self.db.commit()
        return invoices
