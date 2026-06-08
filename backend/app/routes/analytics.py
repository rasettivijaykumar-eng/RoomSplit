from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from app import mongo
from app.utils import parse_json
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/<room_id>/dashboard', methods=['GET'])
@jwt_required()
def get_dashboard_stats(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    total_expenses = 0
    expenses = list(mongo.db.expenses.find({"room_id": room_id_obj}))
    for exp in expenses:
        total_expenses += exp.get('total_amount', 0)
        
    total_collected = 0
    payments = list(mongo.db.payments.find({"room_id": room_id_obj, "type": "expense_payment"}))
    for p in payments:
        total_collected += p.get('amount', 0)
        
    my_paid = 0
    my_payments = [p for p in payments if str(p['paid_by']) == current_user_id]
    for p in my_payments:
        my_paid += p.get('amount', 0)
        
    my_due = 0
    my_splits = list(mongo.db.expense_splits.find({"room_id": room_id_obj, "user_id": user_id_obj}))
    for s in my_splits:
        my_due += s.get('amount_owed', 0)
        
    my_settlements_paid = list(mongo.db.payments.find({"room_id": room_id_obj, "type": "settlement", "paid_by": user_id_obj}))
    my_settlements_received = list(mongo.db.payments.find({"room_id": room_id_obj, "type": "settlement", "paid_to": user_id_obj}))
    
    for s in my_settlements_paid:
        my_paid += s.get('amount', 0)
    for s in my_settlements_received:
        my_paid -= s.get('amount', 0)
        
    my_balance = my_paid - my_due
    
    active_members = mongo.db.room_members.count_documents({"room_id": room_id_obj, "status": "Approved"})
    
    return jsonify({
        "total_expenses": total_expenses,
        "total_collected": total_collected,
        "total_pending": total_expenses - total_collected,
        "active_members": active_members,
        "my_paid": my_paid,
        "my_due": my_due,
        "my_balance": my_balance
    }), 200

@analytics_bp.route('/<room_id>/charts', methods=['GET'])
@jwt_required()
def get_charts(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    pipeline = [
        {"$match": {"room_id": room_id_obj}},
        {"$group": {"_id": "$category", "total": {"$sum": "$total_amount"}}}
    ]
    categories = list(mongo.db.expenses.aggregate(pipeline))
    category_labels = [c['_id'] for c in categories]
    category_data = [c['total'] for c in categories]
    
    trend_pipeline = [
        {"$match": {"room_id": room_id_obj}},
        {"$group": {
            "_id": {"$substr": ["$date", 0, 7]},
            "total": {"$sum": "$total_amount"}
        }},
        {"$sort": {"_id": 1}}
    ]
    trends = list(mongo.db.expenses.aggregate(trend_pipeline))
    trend_labels = [t['_id'] for t in trends]
    trend_data = [t['total'] for t in trends]
    
    return jsonify({
        "categories": {
            "labels": category_labels,
            "data": category_data
        },
        "trends": {
            "labels": trend_labels,
            "data": trend_data
        }
    }), 200
