from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from app import mongo
from app.utils import parse_json
from datetime import datetime

expenses_bp = Blueprint('expenses', __name__)

@expenses_bp.route('/<room_id>', methods=['POST'])
@jwt_required()
def add_expense(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    member = mongo.db.room_members.find_one({
        "room_id": room_id_obj, 
        "user_id": user_id_obj,
        "role": "Admin",
        "status": "Approved"
    })
    
    if not member:
        return jsonify({"error": "Only admins can add expenses"}), 403
        
    data = request.get_json()
    required_fields = ['title', 'category', 'total_amount', 'paid_by', 'splits']
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
        
    expense = {
        "room_id": room_id_obj,
        "title": data['title'],
        "category": data['category'],
        "total_amount": float(data['total_amount']),
        "date": data.get('date', datetime.utcnow().isoformat()),
        "description": data.get('description', ''),
        "added_by": user_id_obj,
        "created_at": datetime.utcnow()
    }
    
    result = mongo.db.expenses.insert_one(expense)
    expense_id = result.inserted_id
    
    for payer in data['paid_by']:
        payment_record = {
            "expense_id": expense_id,
            "room_id": room_id_obj,
            "paid_by": ObjectId(payer['user_id']),
            "amount": float(payer['amount']),
            "type": "expense_payment",
            "date": datetime.utcnow()
        }
        mongo.db.payments.insert_one(payment_record)
        
    for split in data['splits']:
        split_record = {
            "expense_id": expense_id,
            "room_id": room_id_obj,
            "user_id": ObjectId(split['user_id']),
            "amount_owed": float(split['amount_owed'])
        }
        mongo.db.expense_splits.insert_one(split_record)
        
    return jsonify({
        "message": "Expense added successfully",
        "expense_id": str(expense_id)
    }), 201

@expenses_bp.route('/<room_id>', methods=['GET'])
@jwt_required()
def get_expenses(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    expenses = list(mongo.db.expenses.find({"room_id": room_id_obj}).sort("created_at", -1))
    
    for exp in expenses:
        exp['splits'] = list(mongo.db.expense_splits.find({"expense_id": exp['_id']}))
        exp['paid_by'] = list(mongo.db.payments.find({"expense_id": exp['_id'], "type": "expense_payment"}))
        
    return jsonify(parse_json(expenses)), 200
