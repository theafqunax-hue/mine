from decimal import Decimal
from sqlalchemy import select
from models import Order, OrderHistory, OrderStatus, Operator, OperatorPermission

async def set_status(session, order, new_status, actor=None):
    old = order.status
    order.status = new_status.value if hasattr(new_status, "value") else str(new_status)
    await session.flush()
    session.add(OrderHistory(
        order_id=order.id,
        old_status=old,
        new_status=order.status,
        actor_telegram_id=actor,
    ))

async def operator_can_accept(session, operator_id, method, amount):
    op = await session.scalar(select(Operator).where(
        Operator.telegram_id == operator_id,
        Operator.enabled == True,
    ))
    if not op:
        return False
    perm = await session.scalar(select(OperatorPermission).where(
        OperatorPermission.operator_id == op.id,
        OperatorPermission.payment_method == method,
        OperatorPermission.min_amount <= amount,
        OperatorPermission.max_amount >= amount,
    ))
    return perm is not None

async def atomic_assign(session, order_id, operator_telegram_id, method, amount, owner_admin_id=None):
    # SQLite/PostgreSQL-friendly conditional update: only PENDING_REVIEW orders
    # can be claimed. The caller commits the transaction.
    # Owner is a super-operator and can claim any pending order regardless of
    # the normal method/amount permissions configured for operators.
    allowed = (
        owner_admin_id is not None and operator_telegram_id == owner_admin_id
    ) or await operator_can_accept(session, operator_telegram_id, method, amount)
    if not allowed:
        return False, None
    op = await session.scalar(select(Operator).where(
        Operator.telegram_id == operator_telegram_id,
        Operator.enabled == True,
    ))
    # Keep the owner in the same assignment model as normal operators so the
    # Payment Sent button in the work group is locked to the actual assignee.
    if op is None and owner_admin_id is not None and operator_telegram_id == owner_admin_id:
        op = Operator(telegram_id=operator_telegram_id, enabled=True)
        session.add(op)
        await session.flush()
    order = await session.scalar(select(Order).where(Order.id == order_id))
    if not order or order.status != OrderStatus.PENDING_REVIEW.value or order.assigned_operator_id:
        return False, None
    # Owner does not need an Operator row, but normal operators do.
    if op is None:
        return False, None
    order.assigned_operator_id = op.id
    order.status = OrderStatus.ASSIGNED.value
    session.add(OrderHistory(
        order_id=order.id,
        old_status=OrderStatus.PENDING_REVIEW.value,
        new_status=OrderStatus.ASSIGNED.value,
        actor_telegram_id=operator_telegram_id,
    ))
    await session.flush()
    return True, order
