import string
import random
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from app import mongo
from app.utils import parse_json
from datetime import datetime

rooms_bp = Blueprint('rooms', __name__)

def generate_room_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not mongo.db.rooms.find_one({"code": code}):
            return code

@rooms_bp.route('/me', methods=['GET'])
@jwt_required()
def get_my_rooms():
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    memberships = list(mongo.db.room_members.find({"user_id": user_id_obj, "status": "Approved"}))
    return jsonify(parse_json(memberships)), 200

@rooms_bp.route('/', methods=['POST'])
@jwt_required()
def create_room():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"error": "Room name is required"}), 400

    current_user_id = get_jwt_identity()
    
    room_code = generate_room_code()
    
    new_room = {
        "name": data['name'],
        "code": room_code,
        "admin_id": ObjectId(current_user_id),
        "created_at": datetime.utcnow(),
        "settings": data.get('settings', {})
    }
    
    result = mongo.db.rooms.insert_one(new_room)
    room_id = result.inserted_id
    
    # Add creator as Admin in room_members
    member_record = {
        "room_id": room_id,
        "user_id": ObjectId(current_user_id),
        "role": "Admin",
        "status": "Approved",
        "joined_at": datetime.utcnow()
    }
    mongo.db.room_members.insert_one(member_record)
    
    return jsonify({
        "message": "Room created successfully",
        "room": parse_json(new_room)
    }), 201

@rooms_bp.route('/join', methods=['POST'])
@jwt_required()
def join_room():
    data = request.get_json()
    if not data or not data.get('code'):
        return jsonify({"error": "Room code is required"}), 400

    room = mongo.db.rooms.find_one({"code": data['code'].upper()})
    if not room:
        return jsonify({"error": "Invalid room code"}), 404
        
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    
    # Check if already requested or member
    existing_member = mongo.db.room_members.find_one({
        "room_id": room['_id'],
        "user_id": user_id_obj
    })
    
    if existing_member:
        return jsonify({"error": "Already a member or request pending"}), 409
        
    member_record = {
        "room_id": room['_id'],
        "user_id": user_id_obj,
        "role": "Member",
        "status": "Pending",
        "requested_at": datetime.utcnow()
    }
    mongo.db.room_members.insert_one(member_record)
    
    return jsonify({"message": "Join request sent to admin"}), 200

@rooms_bp.route('/<room_id>', methods=['GET'])
@jwt_required()
def get_room(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    # Verify membership
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    room = mongo.db.rooms.find_one({"_id": room_id_obj})
    return jsonify(parse_json(room)), 200

@rooms_bp.route('/<room_id>/members', methods=['GET'])
@jwt_required()
def get_room_members(room_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    
    # Verify membership
    member = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "status": "Approved"})
    if not member:
        return jsonify({"error": "Access denied"}), 403
        
    # Aggregate members with user details
    pipeline = [
        {"$match": {"room_id": room_id_obj}},
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "_id",
            "as": "user_info"
        }},
        {"$unwind": "$user_info"},
        {"$project": {
            "user_info.password_hash": 0 # exclude password hash
        }}
    ]
    
    members = list(mongo.db.room_members.aggregate(pipeline))
    return jsonify(parse_json(members)), 200

@rooms_bp.route('/<room_id>/members/<target_user_id>/approve', methods=['PUT'])
@jwt_required()
def approve_member(room_id, target_user_id):
    current_user_id = get_jwt_identity()
    user_id_obj = ObjectId(current_user_id)
    room_id_obj = ObjectId(room_id)
    target_user_obj = ObjectId(target_user_id)
    
    # Verify admin status
    admin = mongo.db.room_members.find_one({"room_id": room_id_obj, "user_id": user_id_obj, "role": "Admin", "status": "Approved"})
    if not admin:
        return jsonify({"error": "Only admins can approve members"}), 403
        
    result = mongo.db.room_members.update_one(
        {"room_id": room_id_obj, "user_id": target_user_obj, "status": "Pending"},
        {"$set": {"status": "Approved", "joined_at": datetime.utcnow()}}
    )
    
    if result.modified_count == 0:
        return jsonify({"error": "Pending request not found"}), 404
        
    return jsonify({"message": "Member approved successfully"}), 200
