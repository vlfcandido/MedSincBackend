from flask import Blueprint, request, jsonify
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentCreate
from app.database import db
from app.utils.auth import token_required

payment_bp = Blueprint('payment', __name__)
payment_repository = PaymentRepository()

@payment_bp.route('/', methods=['GET'])
@token_required
def get_payments(current_user):
    # Antes chamava get_all sem existir (HTTP 500); agora lista só os pagamentos do médico logado.
    payments = payment_repository.get_all(db.session, current_user.id)
    return jsonify([payment.to_dict() for payment in payments])

@payment_bp.route('/', methods=['POST'])
@token_required
def create_payment(current_user):
    data = request.get_json()
    payment_data = PaymentCreate(**data)
    payment_repository.create(db.session, payment_data)
    return {'message': 'Criado com sucesso!'}