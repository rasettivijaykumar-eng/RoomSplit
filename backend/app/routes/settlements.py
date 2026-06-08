from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from app import mongo
from app.utils import parse_json
from datetime import datetime
from collections import defaultdict

settlements_bp = Blueprint('settlements', __name__)

@settlements_bp.route('/<room_id>', methods=['GET'])
@jwt_required()
def get_settlements(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    balances = defaultdict(float)
    
    payments = mongo.db.payments.find({"room_id": room_id_obj, "type": "expense_payment"})
    for p in payments:
        balances[str(p['paid_by'])] += p['amount']
        
    splits = mongo.db.expense_splits.find({"room_id": room_id_obj})
    for s in splits:
        balances[str(s['user_id'])] -= s['amount_owed']
        
    settlements = mongo.db.payments.find({"room_id": room_id_obj, "type": "settlement"})
    for s in settlements:
        balances[str(s['paid_by'])] += s['amount']
        balances[str(s['paid_to'])] -= s['amount']
        
    debtors = []
    creditors = []
    
    for uid, bal in balances.items():
        if bal < -0.01:
            debtors.append({"user_id": uid, "amount": -bal})
        elif bal > 0.01:
            creditors.append({"user_id": uid, "amount": bal})
            
    debtors.sort(key=lambda x: x['amount'], reverse=True)
    creditors.sort(key=lambda x: x['amount'], reverse=True)
    
    transactions = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debt = debtors[i]['amount']
        credit = creditors[j]['amount']
        
        min_amount = min(debt, credit)
        
        transactions.append({
            "from": debtors[i]['user_id'],
            "to": creditors[j]['user_id'],
            "amount": min_amount
        })
        
        debtors[i]['amount'] -= min_amount
        creditors[j]['amount'] -= min_amount
        
        if debtors[i]['amount'] < 0.01:
            i += 1
        if creditors[j]['amount'] < 0.01:
            j += 1
            
    for txn in transactions:
        u_from = mongo.db.users.find_one({"_id": ObjectId(txn['from'])})
        u_to = mongo.db.users.find_one({"_id": ObjectId(txn['to'])})
        txn['from_name'] = u_from['name'] if u_from else "Unknown"
        txn['to_name'] = u_to['name'] if u_to else "Unknown"
        
    return jsonify({
        "balances": [{"user_id": k, "balance": v} for k, v in balances.items()],
        "transactions": transactions
    }), 200

@settlements_bp.route('/<room_id>/payments', methods=['POST'])
@jwt_required()
def record_payment(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    data = request.get_json()
    if not data or not data.get('paid_to') or not data.get('amount'):
        return jsonify({"error": "Missing required fields"}), 400
        
    payment = {
        "room_id": room_id_obj,
        "paid_by": user_id_obj,
        "paid_to": ObjectId(data['paid_to']),
        "amount": float(data['amount']),
        "method": data.get('method', 'Cash'),
        "type": "settlement",
        "date": datetime.utcnow()
    }
    
    result = mongo.db.payments.insert_one(payment)
    
    return jsonify({
        "message": "Payment recorded successfully",
        "payment_id": str(result.inserted_id)
    }), 201
