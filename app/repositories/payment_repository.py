from sqlalchemy.orm import Session
from app.models.payment import Payment
from app.schemas.payment import PaymentCreate
from datetime import datetime
import pytz

class PaymentRepository:
    model = Payment
    
    def create(self, db: Session, payment: PaymentCreate) -> Payment:
        db_payment = Payment(**vars(payment), status="pending")
        db.add(db_payment)
        db.commit()
        db.refresh(db_payment)
        return db_payment

    def get_all(self, db: Session, doctor_id: int) -> list[Payment]:
        """Lista os pagamentos dos plantões do médico informado, do mais recente ao mais antigo."""
        from app.models.shift import Shift
        return (db.query(Payment).join(Shift, Payment.shift_id == Shift.id)
                .filter(Shift.doctor_id == doctor_id).order_by(Payment.id.desc()).all())

    def get_by_shift(self, db: Session, shift_id: int) -> Payment:
        return db.query(Payment).filter(Payment.shift_id == shift_id).first()

    def update_status(self, db: Session, payment: Payment, status: str) -> Payment:
        payment.status = status
        if status == "paid":
            brazil_tz = pytz.timezone('America/Sao_Paulo')
            payment.payment_date = datetime.now(brazil_tz).date()
        db.commit()
        db.refresh(payment)
        return payment