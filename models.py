from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Numeric, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

def now():
    return datetime.now(timezone.utc)

class OrderStatus(str, Enum):
    CREATED = "CREATED"
    AWAITING_AMOUNT = "AWAITING_AMOUNT"
    AWAITING_ASSET = "AWAITING_ASSET"
    AWAITING_NETWORK = "AWAITING_NETWORK"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PROOF_SUBMITTED = "PROOF_SUBMITTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ASSIGNED = "ASSIGNED"
    AWAITING_PAYOUT_DETAILS = "AWAITING_PAYOUT_DETAILS"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    referrer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Network(Base):
    __tablename__ = "networks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class AssetNetwork(Base):
    __tablename__ = "asset_networks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    network_id: Mapped[int] = mapped_column(ForeignKey("networks.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("asset_id", "network_id"),)

class WalletAddress(Base):
    __tablename__ = "wallet_addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    network_id: Mapped[int] = mapped_column(ForeignKey("networks.id"))
    address: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("asset_id", "network_id"),)

class RateTier(Base):
    __tablename__ = "rate_tiers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_method: Mapped[str] = mapped_column(String(32), index=True)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Operator(Base):
    __tablename__ = "operators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class OperatorPermission(Base):
    __tablename__ = "operator_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"))
    payment_method: Mapped[str] = mapped_column(String(32))
    min_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    max_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))

class SavedPayout(Base):
    __tablename__ = "saved_payouts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payment_method: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("user_id", "payment_method"),)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payment_method: Mapped[str] = mapped_column(String(32))
    asset: Mapped[str | None] = mapped_column(String(32))
    network: Mapped[str | None] = mapped_column(String(32))
    crypto_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    inr_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    wallet_address: Mapped[str | None] = mapped_column(Text)
    tx_hash: Mapped[str | None] = mapped_column(Text)
    proof_file_id: Mapped[str | None] = mapped_column(Text)
    payout_proof_file_id: Mapped[str | None] = mapped_column(Text)
    payout_details: Mapped[str | None] = mapped_column(Text)
    assigned_operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"))
    status: Mapped[str] = mapped_column(String(40), default=OrderStatus.CREATED.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class OrderHistory(Base):
    __tablename__ = "order_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str] = mapped_column(String(40))
    actor_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
