"""Alert rules, alert history and the in-app notification inbox."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from .. import serializers as ser
from ..db import get_db, utcnow
from ..deps import CurrentUser, get_current_user, get_owned
from ..models import AlertEvent, AlertRule, Notification
from ..schemas import AlertRuleIn
from ..services import alerts, notifications
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts/metrics")
def metrics():
    return [m.public() for m in alerts.METRICS.values()]


@router.get("/alerts/rules")
def list_rules(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.scalars(select(AlertRule).where(AlertRule.user_id == current.id).order_by(AlertRule.created_at)).all()
    return [ser.alert_rule(r) for r in rules]


def _apply(db: Session, current: CurrentUser, rule: AlertRule, body: AlertRuleIn) -> None:
    problem = alerts.validate_rule(db, current.id, body.metric, body.params, body.operator, body.threshold, body.cooldown_policy)
    if problem:
        raise HTTPException(422, problem)
    metric = alerts.METRICS[body.metric]
    if body.cooldown_policy == "cooldown" and body.cooldown_minutes < 1:
        raise HTTPException(422, "Set cooldown minutes for the cooldown policy")
    changed_condition = (rule.metric, rule.params, rule.operator, rule.threshold) != (body.metric, body.params, body.operator, body.threshold)
    rule.name, rule.metric, rule.params = body.name, body.metric, {k: v for k, v in body.params.items() if k in metric.params and v not in (None, "")}
    rule.operator = body.operator if not metric.boolean else ">="
    rule.threshold = body.threshold if body.threshold is not None else metric.default_threshold
    rule.channels, rule.cooldown_policy, rule.cooldown_minutes, rule.enabled = body.channels, body.cooldown_policy, body.cooldown_minutes, body.enabled
    if changed_condition:
        rule.state = {}  # a new condition starts with a clean firing history


@router.post("/alerts/rules", status_code=201)
def create_rule(body: AlertRuleIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = AlertRule(user_id=current.id, state={})
    _apply(db, current, rule, body)
    db.add(rule)
    db.flush()
    fired = alerts.evaluate_state_rules(db, ctx_of(current), {rule.metric}) if alerts.METRICS[rule.metric].kind == "state" else []
    db.commit()
    return {**ser.alert_rule(rule), "fired_now": [e.title for e in fired if e.rule_id == rule.id]}


@router.put("/alerts/rules/{rule_id}")
def update_rule(rule_id: int, body: AlertRuleIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = get_owned(db, AlertRule, rule_id, current, "Alert rule")
    _apply(db, current, rule, body)
    db.commit()
    return ser.alert_rule(rule)


@router.delete("/alerts/rules/{rule_id}")
def delete_rule(rule_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, AlertRule, rule_id, current, "Alert rule"))
    db.commit()
    return {"deleted": True}


@router.post("/alerts/rules/{rule_id}/test")
def test_rule(rule_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Evaluate a rule now and report the current values (dry run – nothing is sent)."""
    rule = get_owned(db, AlertRule, rule_id, current, "Alert rule")
    metric = alerts.METRICS.get(rule.metric)
    if metric is None:
        raise HTTPException(422, "Unknown metric")
    if metric.kind != "state":
        return {"kind": "event", "message": "Event rules fire when a matching transaction is added; there is no current value to test."}
    ctx = ctx_of(current)
    observations = alerts.STATE_EVALUATORS[rule.metric](db, ctx, rule)
    return {"kind": "state", "observations": [
        {"entity": o.entity, "value": str(o.value), "condition_met": alerts.condition_met(rule, metric, o), "message": o.message} for o in observations if o.title
    ]}


@router.post("/alerts/evaluate")
def evaluate_now(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    fired = alerts.evaluate_state_rules(db, ctx_of(current))
    db.commit()
    return {"fired": [ser.alert_event(e) for e in fired]}


@router.get("/alerts/events")
def events(limit: int = 100, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AlertEvent).where(AlertEvent.user_id == current.id).order_by(AlertEvent.triggered_at.desc()).limit(min(limit, 500))
        .options(selectinload(AlertEvent.deliveries))
    ).all()
    return [ser.alert_event(e) for e in rows]


@router.post("/alerts/test-notification")
def test_notification(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Send a real test message through every enabled channel to verify configuration."""
    ctx = ctx_of(current)
    obs = alerts.Observation(entity=f"test:{utcnow().isoformat()}", value=Decimal(0), period_key="-", title="Test notification",
                             message="This is a test notification. If you can read this, the channel works.", severity="info", link="/settings")
    event = AlertEvent(user_id=current.id, rule_id=None, metric="test", category="system", dedupe_key=f"test:{utcnow().isoformat()}",
                       title=obs.title, message=obs.message, severity="info", context={"link": obs.link})
    db.add(event)
    db.flush()
    channels = [c for c in ("in_app", "email", "sms", "whatsapp", "push") if notifications.channel_enabled(current.settings, c)]
    deliveries = notifications.dispatch(db, current.user, current.settings, event, channels)
    db.commit()
    return {"channels": channels, "deliveries": [ser.delivery(d) for d in deliveries]}


# --- Notifications inbox ------------------------------------------------------------------------

@router.get("/notifications")
def list_notifications(unread_only: bool = False, limit: int = 50, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == current.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(min(limit, 200))).all()
    return {"items": [ser.notification(n) for n in rows], "unread": notifications.unread_count(db, current.id)}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    n = get_owned(db, Notification, notification_id, current, "Notification")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return ser.notification(n)


@router.post("/notifications/read-all")
def mark_all_read(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(update(Notification).where(Notification.user_id == current.id, Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return {"updated": result.rowcount}


@router.delete("/notifications/{notification_id}")
def delete_notification(notification_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Notification, notification_id, current, "Notification"))
    db.commit()
    return {"deleted": True}


@router.get("/notifications/unread-count")
def unread(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": int(db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == current.id, Notification.read_at.is_(None))) or 0)}
